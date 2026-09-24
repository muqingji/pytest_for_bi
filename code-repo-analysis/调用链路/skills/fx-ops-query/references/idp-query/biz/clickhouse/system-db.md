# ClickHouse `system` 库（sql-query 元数据路径）

> 能力来源：fs-developer-platform MR !981（已合并）。  
> 已接入的 ClickHouse 数据源在 **sql-query 元数据路径**上默认开放 `system` 库。本文只写 Agent 怎么用这条能力，**不**在 bug-finder 里复刻 IDP 服务端逻辑。

运维排查（库/表是否存在、正在跑的查询、query_log）**优先走 `system` 库**，不要把 `system` 当成不可访问。本能力只作用于 ClickHouse dialect；MySQL / PostgreSQL / MongoDB 不受影响。不改 endpoint allowlist、不新增 permission key。

适用 biz：任意已接入的 ClickHouse 数据源（`biz-app-log`、`crm-audit-log`、`bi --dialect clickhouse` 等）。下面示例用 `biz-app-log`。

## 何时用

| 意图 | 走哪条 SQL | 不要 |
| --- | --- | --- |
| 当前数据源能看到哪些库 | `SHOW DATABASES` / `EXISTS DATABASE system` | 假设 `system` 不在结果里 |
| 列出 `system` 表 | `SHOW TABLES FROM system` | 用 `SHOW TABLES FROM <业务库>` 去找 system 表 |
| 表/引擎/列元数据 | 无库过滤的 `SELECT … FROM system.tables` / `system.columns` | `system.users` / `system.settings` 等黑名单表 |
| 卡住的查询、当前进程 | `system.processes` | 把空结果当成「system 不可查」 |
| 还原近期 SQL 文本 | `system.query_log`（带时间窗 + `LIMIT`） | 无时间窗拉全量 `query_log` |

业务日志明细（CEP / error / app_log）仍走各单表文档，不经过 `system`。

## 可复制命令

```bash
# 1. SHOW DATABASES：本地结果包含 system（不打 ClickHouse）
fx-ops idp --profile <profile> query biz-app-log --sql "SHOW DATABASES" -j

# 2. 确认 system 库存在：本地返回 1
fx-ops idp --profile <profile> query biz-app-log --sql "EXISTS DATABASE system" -j

# 3. SHOW TABLES FROM system：只注入 system，不串其它租户业务库
fx-ops idp --profile <profile> query biz-app-log --sql "SHOW TABLES FROM system" -j

# 4. 无库过滤 SELECT FROM system.*：注入 database IN (<业务库>, 'system')，合并结果保留 system 行
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT database, name, engine FROM system.tables LIMIT 50" -j

# 5. 当前进程（current_database 过滤，见下方可见性）
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT elapsed, current_database, memory_usage, query FROM system.processes LIMIT 50" -j

# 6. 近期 query_log（必须带时间窗 + LIMIT；含完整 SQL 文本）
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT event_time, current_database, query_duration_ms, query FROM system.query_log WHERE event_time > now() - INTERVAL 15 MINUTE ORDER BY event_time DESC LIMIT 50" -j
```

`bi` 双方言必须声明 dialect：

```bash
fx-ops idp --profile <profile> query bi --dialect clickhouse --sql "SHOW DATABASES" -j
```

`idp show tables` / `show columns` 仍用于业务表发现。`SHOW COLUMNS FROM <table>` 写在 `--sql` 里会 `sql_query.invalid_request`（见 [idp-query-clickhouse.md](../../../idp-query-clickhouse.md) §6）。system 列元数据用 `SELECT … FROM system.columns`。

## 允许 / 拒绝边界（对齐 MR !981）

| SQL | 行为 |
| --- | --- |
| `SHOW DATABASES` / `EXISTS DATABASE system` | 本地结果含 `system` |
| 无库过滤的 `SELECT FROM system.*` | 注入 `database IN (<业务库>, 'system')`，合并结果保留 `system` 行 |
| `SHOW TABLES FROM system` | 只注入 `system`，不串其它租户业务库 |
| 指定业务库，如 `SHOW TABLES FROM logger` | **不**追加 `system` |
| 未配置 / 范围外的库 | 仍拒绝（`invalid_request` / outside cluster scope） |
| `system.users` / `system.settings` 等黑名单表 | 仍拒绝，不调用 ClickHouse |
| 其它 dialect | 不受影响 |

拒绝示例（预期 `sql_query.invalid_request`，不要改成业务表重试）：

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM system.users" -j
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM system.settings" -j
fx-ops idp --profile <profile> query biz-app-log --sql "SHOW TABLES FROM outside_db" -j
```

黑名单表（高危或无法按业务库收窄，与 IDP `CLICKHOUSE_SYSTEM_REJECTED_TABLES` 一致）：

`system.users`、`system.settings`、`system.grants`、`system.roles`、`system.clusters`、`system.disks`、`system.macros`、`system.dictionaries`、`system.functions`、`system.storage_policies`、`system.error_log`、`system.metric_log`、`system.query_views_log`、`system.text_log`、`system.trace_log`

未列入允许分类、也无法按 `database` / `current_database` 收窄的其它 `system.*` 表同样拒绝。

指定业务库、确认不串 `system`：

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SHOW TABLES FROM logger" -j
```

## `query_log` / `processes` / `query_thread_log` 可见性

这三张表走 **`current_database` 过滤**，不是 `database` 列。

默认开放 `system` 后，无库过滤查询会注入：

```text
current_database IN (<业务库>, 'system')
```

因此会放行所有以 `system` 为默认库的会话行（**含完整 SQL 文本**）。这是「开放 system 库」的固有面，不是越权泄漏。

实际可见性仍受 **ClickHouse 账号 grants** 约束：网关放行 ≠ 账号一定能读到行。空结果先核对 grants / 时间窗 / `LIMIT`，不要回退成「system 不可查」。

`query_log` / `query_thread_log` 必须带时间窗（建议 ≤15 分钟）和 `LIMIT`；`processes` 是当前快照，仍加 `LIMIT`。

## 相关文档

- [idp-query-clickhouse.md](../../../idp-query-clickhouse.md) — ClickHouse 查询规则（业务日志表时间窗、§6 SHOW COLUMNS）
- [clickhouse.md](../clickhouse.md) — ClickHouse biz 总览
- [index.md](./index.md) — 单表文档索引
