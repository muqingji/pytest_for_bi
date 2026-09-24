# semantic-system

**方言**: `clickhouse`
**说明**: 语义层系统库（catalog 已登记；表清单以运行时为准）
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

> 2026-08-08 `foneshare` 实测：`show tables` 返回 **0 表**（config 源）。勿死记表名；先 `show tables`。

**查询入口**: `fx-ops idp query semantic-system`

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables semantic-system -j
# 若 total>0：
fx-ops idp --profile <profile> show columns semantic-system <table> -j
fx-ops idp --profile <profile> query semantic-system --sql "SELECT * FROM <table> LIMIT 20" -j
```

## 相关

- 评估侧（当前有表）：`semantic-eval`（[semantic-eval.md](./semantic-eval.md)）
- 日志侧：`semantic-log`（[semantic-log.md](./semantic-log.md)）
