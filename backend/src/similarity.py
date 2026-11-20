"""相似结案样例的纯计算。

每条采样先换算为8频带的占比（L1归一），再对卷内多次采样取均值。
余弦只比较分布形状，因此整体音量按同一比例放大或缩小不会改变相似度与排名。
"""

def normalized(sample):
    total=sum(float(x) for x in sample)
    if total<=0:raise ValueError('频带总能量须大于0')
    return [float(x)/total for x in sample]

def profile(samples,minimum=2):
    """返回卷内多次采样的平均占比；不足 minimum 条返回 None。"""
    samples=list(samples)
    if len(samples)<minimum:return None
    acc=[0.0]*8
    for sample in samples:
        for i,v in enumerate(normalized(sample)):acc[i]+=v
    return normalized(acc)

def cosine(a,b):
    dot=sum(x*y for x,y in zip(a,b))
    na=sum(x*x for x in a)**.5;nb=sum(x*x for x in b)**.5
    if na==0 or nb==0:return 0.0
    return max(0.0,min(1.0,dot/(na*nb)))

def score(a,b):return cosine(a,b)*100

def rank(target,candidates,minimum,limit):
    """只在达到阈值者中排名；不足 limit 的名额留空，差太远不补位。"""
    scored=[]
    for item in candidates:
        value=score(target,item['profile'])
        if value+1e-9<minimum:continue
        scored.append({**item,'similarity':value})
    scored.sort(key=lambda x:(-x['similarity'],-x.get('sample_count',0),x['id']))
    return scored[:limit]
