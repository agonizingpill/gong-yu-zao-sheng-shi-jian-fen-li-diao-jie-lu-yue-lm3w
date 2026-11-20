ROLES=('operator','supervisor','viewer')
CASE_STATES=('monitoring','mediation','remedy','observation','closed')
SOURCE_TYPES=('equipment','impact','speech','undetermined')
SOURCE_LABELS={'equipment':'低频设备','impact':'冲击声','speech':'人声频带','undetermined':'待核实'}
BANDS=('63Hz','125Hz','250Hz','500Hz','1kHz','2kHz','4kHz','8kHz')
# 相似结案样例：每条采样先归一化为频带占比，再对卷内多次采样取均值。
# 余弦相似度只比较分布形状，整体音量放大/缩小不会改变相似度与排名。
REFERENCE_METRIC='cosine'
REFERENCE_MIN_SIMILARITY=0.90
REFERENCE_SOURCE_MIN_SAMPLES=2
REFERENCE_TARGET_MIN_SAMPLES=2
REFERENCE_LIMIT=3
