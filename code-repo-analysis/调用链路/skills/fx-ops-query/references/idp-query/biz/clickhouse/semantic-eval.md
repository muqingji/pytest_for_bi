# semantic-eval

**方言**: `clickhouse`
**说明**: 语义层评估库：BI 指标/维度/分析视图语义定义，以及评估用例运行与 trace 明细
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

> 2026-08-08 `foneshare` 实测：`dbName` 空（config 源），**7 表**。拼 SQL 前务必 `show columns`。

**查询入口**: `fx-ops idp query semantic-eval`（ClickHouse 规则见 ../../../idp-query-clickhouse.md）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables semantic-eval -j
fx-ops idp --profile <profile> show columns semantic-eval <table> -j
fx-ops idp --profile <profile> query semantic-eval --sql "SELECT * FROM <table> LIMIT 20" -j
```

## 表清单（实测）

| 表名 | 用途（据命名） |
| --- | --- |
| `bi_metric_semantic` | BI 指标语义 |
| `bi_dimension_semantic` | BI 维度语义 |
| `bi_analytics_view_semantic` | BI 分析视图语义 |
| `semantic_eval_case_runs` | 评估用例运行 |
| `semantic_eval_trace_messages` | 评估 trace 消息 |
| `semantic_eval_trace_operations` | 评估 trace 操作 |
| `semantic_eval_results` | 评估结果 |

## 相关

- 同 dialect 其它 semantic biz：`semantic-system`、`semantic-log`（表可能为空，先 `show tables`）
- 数仓 BI 业务查询：`bi --dialect clickhouse`（[bi.md](./bi.md)）
