from datetime import datetime,timedelta
from sqlalchemy import select,func
from src.database import Base,engine,Session
from src.models import User,DemoClock,Complaint,NoiseEvent,Separation,Attribution,Agreement,Remedy,Closure,ReferenceAuthorization
from src.auth import password_hash

def seed():
    Base.metadata.create_all(engine)
    with Session() as db:
        for role in ('operator','supervisor','viewer'):
            if not db.scalar(select(User).where(User.username==role)):
                db.add(User(username=role,role=role,password_hash=password_hash('Quiet2026!')))
        if not db.get(DemoClock,1):db.add(DemoClock(id=1,at=datetime(2026,11,18,16,0)))
        items=[('QT031','访客青叶','3栋北侧','22:30设备低频持续，申请协调减振时段',True),('QT032','访客杉木','6栋东侧','午间装修冲击频带，尚未授权监测',False),('QT033','访客白榆','1栋走廊','晚间人声频带事件，希望双方协调安静时段',True)]
        for code,alias,building,summary,consent in items:
            if not db.scalar(select(Complaint).where(Complaint.code==code)):
                c=Complaint(code=code,alias=alias,building=building,summary=summary,consent=consent,consent_note='书面授权QTC-031' if consent else '待取得授权');db.add(c);db.flush()
                if consent:
                    for j in range(6):
                        energy=[8+j*.1,6,1.6,.5,.3,.2,.1,.05] if code=='QT031' else [.2,.3,.8,3,6+j*.1,7,4,1]
                        db.add(NoiseEvent(complaint_id=c.id,measured_at=datetime(2026,11,17,22,30)+timedelta(minutes=j*5),position='窗台测点A',duration_s=60,energies=energy,total=sum(energy),note='合成频带示例，无录音及真实住户信息'))
        seed_archive(db)
        db.commit()
        counts={m.__tablename__:db.scalar(select(func.count()).select_from(m)) for m in (User,Complaint,NoiseEvent,DemoClock)}
        print(counts)
        return counts

def seed_archive(db):
    """一卷已结案的历史样例，用于演示相似推荐、匿名整改做法与授权/撤回。

    仅补充缺少的卷宗；已有库不会覆盖人工修改。默认不授权，须主管在结案页另行授权后
    才会进入推荐候选。"""
    code='QT029'
    case=db.scalar(select(Complaint).where(Complaint.code==code))
    if case:return
    case=Complaint(code=code,alias='访客旧档',building='5栋西侧',summary='历史归档：设备低频夜间持续，已整改并完成观察',consent=True,consent_note='历史书面授权QTC-029',status='closed')
    db.add(case);db.flush()
    for j in range(4):
        energy=[8.2+j*.05,6.1,1.7,.52,.31,.21,.11,.06]
        db.add(NoiseEvent(complaint_id=case.id,measured_at=datetime(2026,10,2,22,40)+timedelta(minutes=j*10),position='窗台测点B',duration_s=60,energies=energy,total=sum(energy),note='历史合成频带样例，无录音及真实住户信息'))
    db.flush()
    job=Separation(complaint_id=case.id,state='done',event_ids=[e.id for e in db.scalars(select(NoiseEvent).where(NoiseEvent.complaint_id==case.id).order_by(NoiseEvent.id))],result={'seed':1040,'note':'历史样例占位结果，仅用于演示'})
    db.add(job);db.flush()
    attr=Attribution(complaint_id=case.id,separation_id=job.id,source='equipment',evidence='历史档案：现场核对设备启停与减振连接件，未作住户身份推断',reviewer='supervisor')
    db.add(attr);db.flush()
    a=Agreement(complaint_id=case.id,attribution_id=attr.id,party_a='住户方',party_b='设备值班方',quiet_from=1320,quiet_to=420,threshold=10,observation_days=2,state='fulfilled',activated_at=datetime(2026,10,5,10,0),observation_from=datetime(2026,10,8,10,0),observation_until=datetime(2026,10,10,10,0))
    db.add(a);db.flush()
    db.add(Remedy(agreement_id=a.id,instruction='更换设备减振垫并重新固定连接件',responsible='设备值班方',state='completed',receipt='历史收据QTR-029',completed_at=datetime(2026,10,7,14,0)))
    db.add(Closure(complaint_id=case.id,agreement_id=a.id,note='历史样例：整改、复验与观察记录已核对并匿名归档',closed_at=datetime(2026,10,10,11,0)))
    db.add(ReferenceAuthorization(complaint_id=case.id,granted=False,note='历史样例默认不对外引用，需主管另行授权',actor='supervisor'))

if __name__=='__main__':seed()
