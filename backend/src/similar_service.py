from sqlalchemy import select
from .models import (Complaint,NoiseEvent,Agreement,Remedy,Closure,
    ReferenceAuthorization,SimilarCaseBatch,SimilarCaseRecommendation)
from .common import require,lock_case,get,record,dump
from .constants import REFERENCE_METRIC,REFERENCE_MIN_SIMILARITY,REFERENCE_SOURCE_MIN_SAMPLES,REFERENCE_TARGET_MIN_SAMPLES,REFERENCE_LIMIT
from . import similarity

def latest_authorization(db,complaint_id):
    return db.scalar(select(ReferenceAuthorization).where(ReferenceAuthorization.complaint_id==complaint_id).order_by(ReferenceAuthorization.id.desc()).limit(1))

def latest_closure(db,complaint_id):
    return db.scalar(select(Closure).where(Closure.complaint_id==complaint_id).order_by(Closure.closed_at.desc(),Closure.id.desc()).limit(1))

def samples(db,complaint_id):
    return [e.energies for e in db.scalars(select(NoiseEvent).where(NoiseEvent.complaint_id==complaint_id).order_by(NoiseEvent.id))]

def invalidate(db,source_id,reason):
    """把指向某个结案卷的推荐标为失效，保留历史与原因。"""
    rows=db.scalars(select(SimilarCaseRecommendation).where(SimilarCaseRecommendation.source_complaint_id==source_id,SimilarCaseRecommendation.state=='valid')).all()
    for row in rows:
        row.state='invalid';row.invalid_reason=reason[:200]
    return len(rows)

def revoke_on_reopen(db,user,case):
    """重开使原引用授权和所有旧推荐一并失效；再次结案后须重新授权。"""
    last=latest_authorization(db,case.id)
    if last and last.granted:
        db.add(ReferenceAuthorization(complaint_id=case.id,granted=False,note='卷宗重开，原引用授权失效',actor=user.username))
        db.flush()
    return invalidate(db,case.id,'结案卷已重开，旧引用失效')

def authorization(db,complaint_id):
    case=get(db,Complaint,complaint_id)
    rows=db.scalars(select(ReferenceAuthorization).where(ReferenceAuthorization.complaint_id==complaint_id).order_by(ReferenceAuthorization.id.desc())).all()
    return {'complaint_id':complaint_id,'case_status':case.status,'granted':bool(rows and rows[0].granted),'current':dump(rows[0]) if rows else None,'history':[dump(r) for r in rows]}

def authorize(db,user,complaint_id,data):
    # 先锁投诉根行：与推荐重算/打开串行，避免撤回与推荐同时提交时互相覆盖。
    case=lock_case(db,complaint_id)
    require(case.status=='closed','仅已匿名结案的卷宗可单独授权作为相似样例')
    last=latest_authorization(db,complaint_id)
    current=bool(last and last.granted)
    require(current!=data.granted,'引用授权状态未变化')
    require(data.granted or last is not None,'尚未授权，无需撤回')
    db.add(ReferenceAuthorization(complaint_id=complaint_id,granted=data.granted,note=data.note,actor=user.username))
    db.flush()
    count=invalidate(db,complaint_id,'结案样例引用授权已撤回') if not data.granted else 0
    record(db,user,'reference.authorize' if data.granted else 'reference.withdraw',complaint_id,data.note)
    db.commit()
    return {'complaint_id':complaint_id,'granted':data.granted,'invalidated':count}

def _candidate(db,cid):
    """资格以调用时最新授权、最新结案及其有效采样为准；不合格者直接不参与排名。"""
    case=db.get(Complaint,cid)
    if not case or case.status!='closed':return None,'尚未结案、已重开或不存在'
    auth=latest_authorization(db,cid)
    if not auth or not auth.granted:return None,'未另行授权引用'
    closure=latest_closure(db,cid)
    if not closure:return None,'缺少结案记录'
    rows=samples(db,cid)
    profile=similarity.profile(rows,REFERENCE_SOURCE_MIN_SAMPLES)
    if profile is None:return None,f'有效采样不足{REFERENCE_SOURCE_MIN_SAMPLES}条'
    return {'id':cid,'profile':profile,'sample_count':len(rows),'closure_id':closure.id},None

def _supersede(db,complaint_id):
    rows=db.scalars(select(SimilarCaseBatch).where(SimilarCaseBatch.complaint_id==complaint_id,SimilarCaseBatch.state=='current').with_for_update()).all()
    for row in rows:row.state='superseded'
    return len(rows)

def recompute(db,user,complaint_id,data):
    get(db,Complaint,complaint_id)
    closed_ids=list(db.scalars(select(Complaint.id).where(Complaint.id!=complaint_id,Complaint.status=='closed').order_by(Complaint.id)))
    # 固定升序锁住目标卷和全部结案候选，和授权撤回、重开、其他重算串行。
    for cid in sorted(set(closed_ids+[complaint_id])):lock_case(db,cid)
    limit=int(data.limit);minimum=float(data.min_similarity)
    target_rows=samples(db,complaint_id)
    target=similarity.profile(target_rows,REFERENCE_TARGET_MIN_SAMPLES)
    candidates=[];excluded={}
    if target is not None:
        for cid in closed_ids:
            item,why=_candidate(db,cid)
            if item:candidates.append(item)
            else:excluded[why]=excluded.get(why,0)+1
    ranked=similarity.rank(target,candidates,minimum*100,limit) if target is not None else []
    _supersede(db,complaint_id)
    if target is None:
        reason=f'本卷有效频带采样不足{REFERENCE_TARGET_MIN_SAMPLES}条，尚无稳定的成分分布，推荐位置留空'
    elif not ranked:
        reason=f'没有达到相似度阈值 {minimum:.2f} 的合格结案样例，推荐位置留空'
    else:
        reason=''
    batch=SimilarCaseBatch(complaint_id=complaint_id,method=REFERENCE_METRIC,min_similarity=minimum,slot_limit=limit,
        target_composition=target,target_sample_count=len(target_rows),reason=reason,state='current',actor=user.username)
    db.add(batch);db.flush()
    for rank,item in enumerate(ranked,1):
        db.add(SimilarCaseRecommendation(batch_id=batch.id,source_complaint_id=item['id'],rank=rank,
            similarity=round(item['similarity'],4),target_sample_count=len(target_rows),source_sample_count=item['sample_count'],
            target_composition=target,source_composition=item['profile'],state='valid'))
    record(db,user,'reference.recompute',complaint_id,f'batch={batch.id};samples={len(target_rows)};matches={len(ranked)}/{limit}')
    db.commit()
    view=_batch_view(db,batch)
    view['excluded']=[{'reason':why,'count':n} for why,n in excluded.items()]
    return view

def _live_available(db,rec):
    if rec.state!='valid':return False
    case=db.get(Complaint,rec.source_complaint_id)
    if not case or case.status!='closed':return False
    auth=latest_authorization(db,rec.source_complaint_id)
    return bool(auth and auth.granted)

def _public_rec(db,rec):
    return {'recommendation_ref':rec.id,'rank':rec.rank,'label':f'样例{chr(64+rec.rank)}','similarity':rec.similarity,
        'target_sample_count':rec.target_sample_count,'source_sample_count':rec.source_sample_count,
        'target_composition':rec.target_composition,'source_composition':rec.source_composition,
        'state':rec.state,'invalid_reason':rec.invalid_reason,'practices_available':_live_available(db,rec)}

def _batch_view(db,batch):
    recs=db.scalars(select(SimilarCaseRecommendation).where(SimilarCaseRecommendation.batch_id==batch.id).order_by(SimilarCaseRecommendation.rank)).all()
    slots=[None]*batch.slot_limit
    for rec in recs:
        if 1<=rec.rank<=batch.slot_limit:slots[rec.rank-1]=_public_rec(db,rec)
    return {'batch':{'id':batch.id,'state':batch.state,'method':batch.method,'min_similarity':batch.min_similarity,'slot_limit':batch.slot_limit,
        'target_composition':batch.target_composition,'target_sample_count':batch.target_sample_count,'reason':batch.reason,
        'actor':batch.actor,'created_at':batch.created_at},'slots':slots,
        'basis':{'method':batch.method,'note':'每条采样先归一化为8频带占比，再取卷内多次采样均值；余弦相似度只比较分布形状，整体音量升降不改变相似度与排名。','min_samples':REFERENCE_TARGET_MIN_SAMPLES,'source_min_samples':REFERENCE_SOURCE_MIN_SAMPLES}}

def current(db,complaint_id):
    get(db,Complaint,complaint_id)
    batch=db.scalar(select(SimilarCaseBatch).where(SimilarCaseBatch.complaint_id==complaint_id,SimilarCaseBatch.state=='current').order_by(SimilarCaseBatch.id.desc()).limit(1))
    if not batch:return {'batch':None,'slots':[],'basis':{'method':REFERENCE_METRIC,'note':'尚未重算；重算时仅使用另行授权且仍处于结案状态的卷宗。','min_samples':REFERENCE_TARGET_MIN_SAMPLES,'source_min_samples':REFERENCE_SOURCE_MIN_SAMPLES}}
    return _batch_view(db,batch)

def _redact(text,terms):
    out=text or ''
    for term in sorted({t for t in terms if t and len(t)>=2},key=len,reverse=True):out=out.replace(term,'〔已匿名〕')
    return out

def practices(db,user,recommendation_ref):
    rec=get(db,SimilarCaseRecommendation,recommendation_ref)
    # 锁来源卷宗根行：撤回/重开若已提交，随后刷新即可看到最新状态。
    case=lock_case(db,rec.source_complaint_id)
    db.refresh(rec)
    batch=db.scalar(select(SimilarCaseBatch).where(SimilarCaseBatch.id==rec.batch_id).execution_options(populate_existing=True))
    require(batch is not None and batch.state=='current','推荐已由新一轮重算替代，请查看当前推荐')
    require(rec.state=='valid','该结案样例的引用授权已撤回或卷宗已重开，旧推荐不可再打开')
    require(case.status=='closed','该结案样例已重开，旧推荐不可再打开')
    auth=latest_authorization(db,case.id)
    require(auth is not None and auth.granted,'该结案样例的引用授权已撤回，旧推荐不可再打开')
    closure=latest_closure(db,case.id)
    require(closure is not None,'结案记录不存在，旧推荐不可再打开')
    agreement=get(db,Agreement,closure.agreement_id)
    rows=db.scalars(select(Remedy).where(Remedy.agreement_id==agreement.id).order_by(Remedy.id)).all()
    terms=[case.code,case.alias,case.building,agreement.party_a,agreement.party_b]
    def responsible_name(name):
        if name==agreement.party_a:return '甲方'
        if name==agreement.party_b:return '乙方'
        return '责任方'
    items=[{'index':i,'instruction':_redact(row.instruction,terms),'responsibility':responsible_name(row.responsible),'delivered':row.state=='completed'} for i,row in enumerate(rows,1)]
    record(db,user,'reference.open',rec.id,f'source={case.id}')
    db.commit()
    return {'recommendation_ref':rec.id,'label':f'样例{chr(64+rec.rank)}','similarity':rec.similarity,
        'target_composition':rec.target_composition,'source_composition':rec.source_composition,
        'target_sample_count':rec.target_sample_count,'source_sample_count':rec.source_sample_count,
        'observation_days':agreement.observation_days,'practices':items,
        'note':'仅展示匿名整改做法；不返回结案卷编号、别名、楼栋、参与方与收据原文。'}
