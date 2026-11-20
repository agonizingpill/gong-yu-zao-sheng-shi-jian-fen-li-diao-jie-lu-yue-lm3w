# 002 相似结案样例推荐

新增三张表，不改动既有列。`create_all` 只建缺失表，生产库若已有旧表结构，请显式执行：

```sql
CREATE TABLE reference_authorizations (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  complaint_id INT NOT NULL,
  granted TINYINT(1) NOT NULL,
  note VARCHAR(300) NOT NULL,
  actor VARCHAR(60) NOT NULL,
  created_at DATETIME NOT NULL,
  INDEX ix_reference_authorizations_complaint_id (complaint_id),
  CONSTRAINT fk_reference_authorizations_complaint FOREIGN KEY (complaint_id) REFERENCES complaints (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE similar_case_batches (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  complaint_id INT NOT NULL,
  method VARCHAR(60) NOT NULL,
  min_similarity FLOAT NOT NULL,
  slot_limit INT NOT NULL,
  target_composition JSON NULL,
  target_sample_count INT NOT NULL,
  reason VARCHAR(200) NOT NULL,
  state VARCHAR(20) NOT NULL,
  actor VARCHAR(60) NOT NULL,
  created_at DATETIME NOT NULL,
  INDEX ix_similar_case_batches_complaint_id (complaint_id),
  CONSTRAINT fk_similar_case_batches_complaint FOREIGN KEY (complaint_id) REFERENCES complaints (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE similar_case_recommendations (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  batch_id INT NOT NULL,
  source_complaint_id INT NOT NULL,
  rank INT NOT NULL,
  similarity FLOAT NOT NULL,
  target_sample_count INT NOT NULL,
  source_sample_count INT NOT NULL,
  target_composition JSON NOT NULL,
  source_composition JSON NOT NULL,
  state VARCHAR(20) NOT NULL,
  invalid_reason VARCHAR(200) NOT NULL,
  UNIQUE KEY one_recommendation_rank (batch_id, rank),
  UNIQUE KEY one_recommendation_source (batch_id, source_complaint_id),
  INDEX ix_similar_case_recommendations_batch_id (batch_id),
  INDEX ix_similar_case_recommendations_source_complaint_id (source_complaint_id),
  CONSTRAINT fk_similar_case_recommendations_batch FOREIGN KEY (batch_id) REFERENCES similar_case_batches (id),
  CONSTRAINT fk_similar_case_recommendations_source FOREIGN KEY (source_complaint_id) REFERENCES complaints (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

语义：

- `reference_authorizations` 追加留痕，最新一条为当前引用授权；仅已结案卷可授权，重开会自动追加一条撤回记录。
- `similar_case_batches` 每次重算新增一批；同卷只保留一条 `state='current'`，旧批转 `superseded`，旧链接打开做法时返回 409。
- `similar_case_recommendations` 同一批内 rank 与来源卷唯一；撤回授权或重开时把指向该来源卷的有效推荐改为 `invalid` 并记录原因，重算时由其他合格卷补位，不足的位置留空。
