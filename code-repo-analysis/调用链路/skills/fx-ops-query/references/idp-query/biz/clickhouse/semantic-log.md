# semantic-log

**方言**: `clickhouse`
**说明**: 语义层日志库（catalog 登记 `fssemdblog`）
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

> 2026-08-08 `foneshare` 实测：`show tables` 返回 **0 表**（`dbName=fssemdblog`，config 源）。勿假设有固定表；以实测为准。

**查询入口**: `fx-ops idp query semantic-log`

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables semantic-log -j
# 若 total>0：
fx-ops idp --profile <profile> show columns semantic-log <table> -j
fx-ops idp --profile <profile> query semantic-log --sql "SELECT * FROM <table> LIMIT 20" -j
```

## 相关

- 有表的语义评估：`semantic-eval`（[semantic-eval.md](./semantic-eval.md)）
- 系统侧：`semantic-system`（[semantic-system.md](./semantic-system.md)）
