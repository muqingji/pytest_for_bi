---
name: fx-ops-query
description: 数据库与日志直查基础能力（无故障语境可直达）。当用户要查 MySQL/PostgreSQL/MongoDB/ClickHouse 表数据或表结构、执行 SQL/Mongo filter/CK 直查、查 ClickHouse 日志表（CEP/错误/慢SQL/Tomcat/RPC 等，统一走 biz-app-log 数据源）、查 ClickHouse system 库（SHOW DATABASES / SHOW TABLES FROM system / query_log / processes）、发现 biz 数据源（idp show datasources）、对账对象 PG/Elasticsearch 数据、查 APL 自定义函数定义/版本/执行日志、查 Dubbo provider/consumer、SOQL 函数速查，或需按 CEP 错误码/reqId 反查 traceId（log_cep_dist has(reqId,…)）时使用。触发词：「查表」「查数据」「帮我跑条 SQL」「对比 PG 和 Elasticsearch」「不知道 biz 名」「dubbo」「互联网盘」「互联公告」「医院主数据」「EIP 同步」「system 库」「SHOW DATABASES」；天/周/月/趋势统计必须走聚合表。
---

# fx-ops-query — 数据与日志诊断器

> Windows/PowerShell 调用约定、高频表误用列名与访问类大表 URI 过滤见 `references/idp-query-clickhouse.md` 避坑指南（§7–§9：cmd /c 禁用、重定向用法、路径过滤先排序键再 uri2/`position`）。

主控编排下：CEP reqId/trace 锚点、TEN/KNO/ONC 由 fx-ops **`references/fx-ops-cli-capabilities.md`** 约定 CLI 完成时，本 skill **不重复** `has(reqId,…)` traceIdLookup 或静态负责人/值班落盘。大结果须经摘要 JSON 再进模型（见 fx-ops `cost-optimization.md`）。

## 快速定位

| 你要查什么 | biz 参数 | 查询入口 |
|-----------|----------|----------|
| ClickHouse 日志表（CEP/错误/慢SQL/APL函数/Tomcat/RPC等） | `biz-app-log` | `fx-ops idp query biz-app-log --sql "SELECT ... FROM <表名> ..."` |
| ClickHouse `system` 库（库/表元数据、进程、query_log） | 已接入的 CH 数据源（常用 `biz-app-log`） | 先读 `references/idp-query/biz/clickhouse/system-db.md`；`SHOW DATABASES` / `SHOW TABLES FROM system` / `SELECT FROM system.*` |
| CRM 审计日志（对象操作、`update_layout`） | `crm-audit-log` | 先读 `references/idp-query/biz/clickhouse/crm-audit-log.md`，确认逻辑表和字段口径 |
| MySQL 业务库 | `paas-crm-biz` / `open-sail` / `open-yunzhijia` 等 | 具体 biz 见 `references/idp-query/biz/mysql/` |
| PostgreSQL | `paas` / `bi-postgresql` / `openapi` / `enterprise-relation-postgresql` 等 | 具体 biz 见 `references/idp-query/biz/postgresql/` |
| MongoDB | `appserver-fmcg` / `paas-bpm` 等 | 具体 biz 见 `references/idp-query/biz/mongodb/` |
| 对象 PG/Elasticsearch 对账 | 对象 API 名 | `idp object query --source pg` / `--source es`，先读 `references/object-es-reconciliation.md` |
| 企业 Elasticsearch 数据总量 | 无需对象 API 名 | `idp es query --operation count`，先读 `references/object-es-reconciliation.md` |
| PG `dbName` → 实例 IP（`fsdb...` 物理节点定位） | `tenant-router` | 见 [tenant-router.md](./references/idp-query/biz/postgresql/tenant-router.md#dbname--实例-ip)，`query tenant-router` 查 `pod_metadata_resource` |

> 所有 ClickHouse 日志表（`log_cep_dist`、`biz_log_function_dist`、`log_error_dist`、`app_log_dist` 等）统一使用 **`biz-app-log`**，表名写在 SQL `FROM` 中。常用表清单见 `references/idp-query/biz/clickhouse/biz-app-log.md`。  
> 聚合库 / 天级统计：`references/idp-query/biz/clickhouse/agg-databases.md`；运行时缺口：`references/idp-query/biz/clickhouse/known-gaps.md`；**错名映射**：`references/idp-query/biz/clickhouse/table-alias-map.md`。  
> **`system` 库默认可查**（sql-query 元数据路径）：运维排查优先用 `SHOW DATABASES` / `SHOW TABLES FROM system` / `system.tables` / `system.processes` / `system.query_log`，不要把 `system` 当成不可访问。边界与示例见 `references/idp-query/biz/clickhouse/system-db.md`。

### 高频日志表时间列与筛选列速查 (防止列名错误)

> 详见 ClickHouse 完整速查手册：[`high-frequency-cheatsheet.md`](references/idp-query/biz/clickhouse/high-frequency-cheatsheet.md)（含 12 张高频表核心字段、强制时间过滤列、Array 字段匹配规则及标准防错 SQL 模板）。

| 表名 (`biz-app-log`) | 强制时间列 | 核心筛选列 / 提示 |
| --- | --- | --- |
| `log_cep_dist` | **`stamp`** | `status`, `bizName`, `uri2`, `companyName`, `reqId` (用 `has(reqId, '...')`), `traceId` |
| `log_error_dist` | **`_time_second_`** | `app`, `loggerName` (**非 `logger`**), `traceId`, `msg`, `error` (**绝对无 `error_class` / `stamp` 列**) |
| `app_log_dist` | **`_time_second_`** | **`app`** (必带), `profile`, `level`, `logger`, `pod`, `traceId`, `msg` (**绝对无 `stamp` 列**) |
| `biz_log_function_dist` | **`_time_second_`** | `tenantId`, `apiName`, `traceId`, `errorCode`；**无 `createTime`** |
| `tomcat_access_dist` | **`_time_second_`** | `app`, `uri2`, `code` (**非 `status`**), `trace_id`；**禁止** `time_for_ckibana` |
| `biz_log_openapi_dist` | **`_time_second_`** | `ei`/`ea`, `openApiUrl`, `cost`, `traceId`（无 `uri`/`method`） |
| `biz_log_erpsyncdata_dist` | **`_time_second_`** | `tenantId`, `sourceObjApiName`, `traceId` |
| `biz_log_erp_ipaas_log_dist` / `biz_log_erp_sync_log_dist` | **`createTime`** | `erp_sync` 库，**无 `_time_second_`**；ipaas 另有 `workflowInstanceId`/`flowApiName` |
| `rpc_dist` / `service_dist` | **`_time_second_`** | `app`, `module`, `method` (**无 `traceId` / `interface` 列**) |
| `slow_log_dist` | **`_time_second_`** | `dbName`, `cost`, `query`, `traceId` |

### 双方言与 2026-08 合并硬规则

1. **不知 biz 名**：先 `fx-ops idp show datasources -j`，**禁止**凭记忆使用已删除旧名。
2. **双方言必须声明 dialect**（否则 `dialect_required`）：
   - `bi` → `--dialect postgresql|clickhouse` 或 `bi-postgresql` / `bi-clickhouse`
   - `enterprise-relation` → `--dialect postgresql|mongodb` 或 `enterprise-relation-postgresql`
   - `open-message` → `--dialect mysql|mongodb`
   - `link-eip-data-sync` → `--dialect postgresql|mongodb` 或 `link-eip-data-sync-postgresql`；独立库是 `link-eip-data-sync-1` / `link-eip-data-sync-747125`，不是 dialect
3. **旧名 → 新名（2026-08-07 起）**：

| 禁止使用的旧 biz | 正确入口 |
| --- | --- |
| `open-oauth` | `openapi` |
| `open-link-app` / `wechat-proxy` / `wechat-notice` / `link-enterprise-relation` | `enterprise-relation --dialect postgresql` |
| `wechat-union`（当目标是 PG 微信关系表） | 同上；mongodb `wechat-union` 仍可查 |
| `open-qywx` | `open-yunzhijia` |
| `eip-data-sync` / `eip_data_sync` / `syncdata` | **`link-eip-data-sync --dialect postgresql`**（Mongo 缓冲 `--dialect mongodb`；独立库 `-1` / `-747125`） |

4. **`--tenant-id` 不是永远必填**：`routeMode=fixed` 的 biz（当前 MySQL 全部 12 个 + 多数 PG fixed，如 `openapi`、`enterprise-relation`、`outer-oa`、`oncall`、`tenant-router`、`hospital-spider`、`link-eip-data-sync*`、`cross-notice` 等）`show/query` 可免 `-t`；表级 WHERE 仍按 filterHint。`tenant-route` biz（如 `paas`/`bi`/`feed`）仍必填。以各 biz 文档「路由」行与 `show datasources` 为准。

## 长周期统计门禁

> [!IMPORTANT]
> 意图含「天 / 周 / 月 / 趋势 / 容量 / 环比」或显式时间窗 **≥24h** 时，**必须**走聚合表，禁止对明细 dist 做跨天 `GROUP BY` 当趋势分析。

| 域 | 强制表 | 禁止（长周期） |
| --- | --- | --- |
| CEP | `cep_daily_dist` / `cep_ea_daily_dist`；故障窗 5min 用 `cep_minute_dist` / `cep_ea_dist`；异常样本 `kpi_cep` | `log_cep_dist` 跨天聚合 |
| Error | `log_error_daily_dist`（时间列 `_time_second_`，无 `day`） | `log_error_dist` 跨天全扫 |
| RPC / Service | `rpc_daily_dist` / `service_daily_dist` | `rpc_dist` / `service_dist` 跨天硬扛 |
| Page | 无 daily → 声明不可用 | `page_dist` ≥24h 聚合 |

- `show columns` / `query` **404** 或确认空表 → 结论标 **`platform_gap`**（表名 + profile + fallback），**禁止**改扫明细赌长窗。缺口表见 `known-gaps.md`。
- 单次 trace / 故障窗影响面仍用明细（如 `log_cep_dist`）；本门禁只管**趋势/容量/天级**，不替代 postmortem impact gate。

## 执行顺序

> [!IMPORTANT]
> **门禁安全边界与反向豁免**：
> 1. **静默校验**：编写并向数据库（MySQL/PG/CK/Mongo）发送 SQL/NoSQL 直查语句前，必须在内部校验只读性、schema 来源、时间窗、租户/服务过滤、LIMIT 与输出落盘路径；低风险通过时不输出 Checklist。
> 2. **显式告警场景**：仅当出现 DDL/DML、缺少时间窗、缺少租户/范围过滤、可能全表扫描、权限越界、`show columns` 降级或需要扩窗时，才在对话中输出单行风险说明并暂停或降级执行。
> 3. **绝对禁止输出**：对于本地磁盘文件读写（如 `write_to_file`）、非直查的系统终端命令（如 `open`、`mkdir`）、代码库只读查找（如 Sourcebot `read_file`）以及子代理分发等**非 SQL 执行操作**，**绝对禁止**输出任何安全门禁内容，防止对人机交互产生无意义的冗余噪音。
> **同一表复用原则**：同一次诊断会话中，对同一表的文档读取和 schema 确认只需在**首次查询或出错时**执行完整流程，后续查询直接复用已获取的 biz、表名、列名与类型信息。

1. **先读文档**：确定要查的数据源后，读取对应文档确认 biz 参数、表名、列名与类型，直接用于编写 SQL。**禁止凭空猜测列名与类型**。
- ClickHouse：先读 `biz-app-log.md` 常用表速查的「单表文档路径」列找到实际路径，直接 `read_file` 该文档获取列名与类型。速查表未覆盖时立即回退第 2 步 `show columns`
- MySQL/PostgreSQL/MongoDB：对应 `references/idp-query/biz/<方言>/` 下的文档
- 文档索引：`references/idp-query/biz/index.md`
2. **文档不全或查询报错时回退 show columns**：文档中缺少所需列名/类型，或 SQL 报 `Missing columns` / `Type mismatch` 时，用 `fx-ops idp --profile <profile> show columns <biz> <table> -j` 获取实时 schema 校验。
3. **静默门禁确认**：发送 SQL 前内部确认以下摘要；低风险不输出。只有命中显式告警场景时输出单行摘要（禁止多行输出）：
  ```
  [query-risk] 文档: <doc_name.md> | 库表: <biz_name>.<table_name> | 时间窗: <duration> | 过滤: <filter_key>='...' | LIMIT <limit_num> | reason: <risk_or_degrade>
  ```
4. **执行 SQL**：确认上述各项后执行。
5. **出错不猜**：SQL 报 `Missing columns` / `Type mismatch` / `Unknown table` 时，回到第 1 步或第 2 步用 `show columns` 重新确认，禁止通过报错信息反向猜测列名/类型反复试探。

### 常见 SQL 报错与根因速查

| 报错 | 根因 | 正确做法 |
|------|------|---------|
| `Missing columns: 'status'` | 表名写错或列名拼错 | `show columns` 核对真实列名 |
| `Type mismatch: reqId` | `reqId = 'xxx'` 对 Array(String) 用等值 | 改用 `has(reqId, 'xxx')` |
| `Cannot compare String with Int` | `status = '500'` 把 Int32 当字符串 | 改为 `status >= 500` |
| `Unknown table: biz-app-log.log_cep_dist` | SQL 中写了 `biz-app-log.log_cep_dist` | 只写 `FROM log_cep_dist`，biz-app-log 是命令行参数 |
| 查询超时 / 返回空 | 未带 `stamp` 时间过滤 | 必须加 `stamp BETWEEN` 且窗口 ≤24h |
| `WHERE traceId = '15-84f875' 无结果` | CEP 错误码不在 traceId 列 | 错误码是 reqId，改用 `has(reqId, '15-84f875')` |
| `Missing columns: "xxx" / Syntax error` | SQL 中字符串使用了双引号 `"xxx"` | 字符串字面量必须使用单引号 `'xxx'`，双引号被 Clickhouse 视为列名/标识符 |
| `Error: current profile "xxx" not found`（exit 2） | 本地 `~/.fx-ops/config.json` 缺该云环境 profile（新增云环境只更新了声明文件） | 仓库根执行 `node scripts/sync-fx-ops-profiles.js` 补建后重试；仍失败按脚本 WARNING 提示向用户报告 |

### SQL 错误分类与处理策略

| 错误类型 | 退出码 | 处理策略 |
| --- | --- | --- |
| `Missing columns` / `Type mismatch` | 1 | 回到 schema 校验步骤（第 1 步或第 2 步），**不重试** |
| 连接超时 / 网络错误 | 5 | 退避重试最多 2 次（间隔 5s/15s），仍失败回抛 `status=error` |
| 认证/授权失败 | 3/4 | 立即回抛 `status=error`，**不重试** |
| 查询超时（超大数据量） | 1 | 缩小时间窗或增加 `LIMIT`，最多重试 1 次 |
| 表不存在 | 1 | 验证表名，回抛 `status=error` |
| SQL 语法错误 | 1 | **不重试**，回抛 `status=error` 并附带原 SQL |
| 内存不足 | 1 | 缩小时间窗 + 减少 SELECT 列，最多重试 1 次 |

### `show columns` 降级路径

`show columns`（schema 校验）是强制性步骤，但 `show columns` 本身可能因 CLI 不可用、认证过期、网络故障而失败。当 `show columns` 失败时：

1. **按单表文档字段定义继续**（标注 `source=单表文档`、`confidence=medium`）
2. 执行 SQL 时若因类型不匹配报错 → 说明单表文档 stale，再次尝试 `show columns` 修正
3. 在 `context_updates` 或证据文件（如 `QRY-show-columns-fallback.json`）中记录 `show columns` 失败原因和降级决策
4. **禁止**因 `show columns` 失败就阻塞整个 traceIdLookup 流程——单表文档在绝大多数情况下是准确的

## 全局约定

遵从 fx-ops 总控的全局约定。本地额外约定:
- 若调用方上下文包含 traceId，必须复用主控 HND 的 `anchor_context` / `request_anchor` 以及 `index.md` 中已有证据提供的 `traceIdParsed`、`env`、`tenant_context`、`time_window`；这些字段用于选择 profile、拼租户过滤和限制时间分区。
- 若调用方上下文包含 CEP 错误码 / reqId 但无 `traceId/traceIdParsed`，本 skill 可执行 `traceIdLookup`：只查询 `log_cep_dist`，用 `has(reqId, '<ERROR_CODE>')` 反查真实 traceId，并通过 `context_updates` 回填 `traceIdLookup.status=resolved`、`traceId`、`traceIdParsed`、`tenant_context`、`time_window`。resolved 前禁止查 `app_log_dist`、`log_error_dist` 等后续链路表。
- 直接调用本 skill 且只有原始入口值时，先调用 `extract_error_anchor` / `parse_traceid` 区分它是 traceId、reqId 还是 CEP 错误码。明确 traceId 才解析 `traceIdParsed` 并按 `ea` 调用 `resolve_tenant_cloud`；若识别为 reqId / CEP 错误码，进入本 skill 的 `traceIdLookup` 小表反查，不把 reqId 当 traceId 使用。
- 共享输出：优先 **compact JSON**（`--json` / `-j`）；另有 `--output yaml|text`、`--pretty`、`--verbose`、`--debug`
- **SQL / Object / Mongo 结构化响应（v5 统一信封）**：`data.columns` + `data.items`（二维行数组）+ `returnedCount` / `hasMore` / `truncated`；错误码读 **`meta.errorCode`**。**禁止**再按 CLI `data.rows` / `rowCount` 解析 stdout。程序侧见 `fxops_invoke.extract_rows`；契约见 **`fx-ops` → `references/fx-ops-cli-capabilities.md`「Go CLI 查询响应信封」**（证据落盘仍用 `data.rows` dict 行，勿混谈）。
- `--tenant-id` / `-t`：是否必填取决于 biz（详见 references/idp-query-table.md）；ClickHouse 可选，租户过滤通常写在 SQL `WHERE` 中
- 一般 SOQL 查询使用 `idp object query`，由对象查询能力负责；只有用户明确指定 Elasticsearch，或要求同条件 PG/Elasticsearch 对账时，本 skill 按 `references/object-es-reconciliation.md` 编排双源查询。
- 编排流回抛须带 `dispatch_id`、`route_hint`、`target_capability?`、`evidence_paths[]`（见 `fx-ops/references/subagent-dispatch-templates.md`）；`need_further` 不驱动主控下一跳。

## 核心定位

`fx-ops-query` 负责把"要查什么源、为什么查这个源、如何控制查询风险"放在第一位。它不是单纯执行 SQL/NoSQL 命令，而是根据问题类型选择最合适的数据源，并给出可追溯证据。

适合本 skill 的问题：
- 查表、查数据、查表结构、查日志明细、验证脏数据或字段缺失
- 判断某条记录有没有写进去、什么时候写进去、是否同步延迟
- 指定从 Elasticsearch 查单对象数据，或用同一业务条件对比对象 PG/Elasticsearch 的数量、ID 和更新时间
- 查询企业 Elasticsearch 数据总量，并包含配置在大对象专属路由中的数据
- 排查租户分片、路由命中、Schema 变化、下游写入异常

不适合本 skill 单独闭环的问题：
- 只有单次请求失败，需要定位调用链上的首发异常
- 主要是 CPU、内存、GC、线程池、Pod 运行时异常
- 需要把多源事件串成时间线做因果分析

## 数据源选择树

先按"问题是什么"选源，再决定具体命令：

1. **要查业务数据是否存在、值是否正确**
- 优先 MySQL / PostgreSQL / MongoDB
2. **要查日志、审计、错误、慢 SQL、K8s 事件**
- 优先 ClickHouse
- 查 ClickHouse 自身库/表、当前进程、`query_log` 时走 `system` 库（[system-db.md](references/idp-query/biz/clickhouse/system-db.md)），不要当成不可访问
3. **要确认对象定义、SOQL 或 CRM 元数据**
- 转 `fx-ops-object`
4. **不知道 biz 名或不知道该查哪个源**
- 先走 `idp show datasources -j`，再进入具体方言
5. **`bi` 等多方言同名 biz**
- 必须先读 [idp-query/biz/bi.md](references/idp-query/biz/bi.md)；`show tables` 命令带 `--dialect`；执行 SQL 用 `bi-postgresql` / `bi-clickhouse`
6. **既怀疑数据不对，也怀疑请求链路有问题**
- 先保留查询范围，必要时回主控并联 `fx-ops-tracing`

不要因为 ClickHouse 好查就把所有问题都转成日志问题；数据是否写入成功，通常要回到真实业务库验证。

## 查询安全等级

- **L1：低风险只读**
- 小时间窗、精确主键、`LIMIT` 明确、Explain/Describe/Count、配置发现类查询
- **L2：中风险只读**
- 模糊条件、范围查询、跨分片聚合、日志聚合统计、可能返回较大结果集
- **L3：高风险只读**
- 宽时间窗 ClickHouse 扫描、未加主键/时间条件的 SQL、可能触发大表扫描或跨租户误查

执行要求：
- L1 可直接执行
- L2 先说明范围和收敛条件，再执行
- L3 必须先缩窗、先采样、先 count 预估，再决定是否继续

## 首轮假设树

收到数据排查请求后，先判断更像以下哪一类：

1. **数据缺失或脏数据**
- 记录不存在、字段值异常、状态不一致、同一实体多处不一致
2. **字段或 Schema 变更**
- 新旧字段不兼容、表结构变化、字段映射调整、代码已发版但数据结构未同步
3. **下游写入延迟或同步异常**
- 主库已有数据，但索引库/缓存/报表侧未更新；消息消费积压或异步任务失败
4. **租户分片或路由问题**
- 同一逻辑只在特定租户失败、数据查错库、命中错误分片或环境

首轮查询以验证这四类假设为目标，不要一开始就写复杂大 SQL。

## 路由

| 用户意图 | 先读 | 命令路径 |
| --- | --- | --- |
| 不知道 biz 名 | references/idp-query.md | `idp show datasources -j` |
| 查表列表或表结构 | references/idp-query-table.md | `idp show tables <biz> -j` / `idp show columns <biz> <table> -j` |
| 拼租户 WHERE / queryTemplate | references/idp-query-filter-hint.md + `idp-query/biz/<dialect>/<biz>.md` | `show columns -j` → `tenant get` → 按模板拼 `--sql` |
| SQL 直查 MySQL/PostgreSQL | references/idp-query-sql.md | `idp query <biz> -t <id> --sql "<SQL>" -j` |
| MongoDB 集合查询 | references/idp-query-mongodb.md | `idp query <biz> -t <id> --collection <name> --filter '<JSON>' -j` |
| ClickHouse 日志/审计查询 | references/idp-query-clickhouse.md | 先按场景选表，再 count 预估数据量，最后 `idp query <biz> --sql "<SQL>" -j` |
| ClickHouse `system` 库运维排查 | references/idp-query/biz/clickhouse/system-db.md | `idp query <biz> --sql "SHOW DATABASES"` / `SHOW TABLES FROM system` / `SELECT … FROM system.*` |
| 单对象 PG/Elasticsearch 查询与对账 | references/object-es-reconciliation.md | 固定业务 SOQL，分别执行 `idp object query --source pg` 和 `--source es` |
| 企业 Elasticsearch 总量 | references/object-es-reconciliation.md | `idp es query --operation count` 不传对象，核验总数与 `routeCounts` |
| Dubbo 注册中心只读查询 | references/idp-dubbo.md | `fx-ops idp dubbo show ...`（非 `idp query` SQL 路径） |
| 只知道业务含义，要找 biz | [idp-query/biz/index.md](references/idp-query/biz/index.md) | 先定位 biz，再读 `biz/<dialect>/<biz>.md` 表级筛选 |
| 自定义函数（APL）定义/版本/调用分析 | references/idp-function.md | `idp query paas` + `idp query biz-app-log` |
| SOQL 函数速查（只提供参考，不在本 skill 内执行 SOQL） | references/idp-query/soql-functions.md | 需要对象查询时回到对象查询能力执行 |
| SOQL 高级排查用法（只提供参考，不在本 skill 内执行 SOQL） | references/idp-query/soql-advanced.md | 需要对象查询时回到对象查询能力执行 |

## 观察 / 查询顺序

1. **先定源**
- 明确是业务库、日志库、审计库、对象元数据，还是连 biz 名都未知
2. **先控风险**
- 给本次查询标注 L1/L2/L3，先加租户、主键、时间窗、`LIMIT`
3. **先做最小验证**
- 先 count、先 sample、先单记录核对，不直接跑重查询
4. **再做扩展对比**
- 必要时比较上下游、主从、同步链路、不同租户/环境
5. **最后再补结构信息**
- 当怀疑字段/Schema 变更时，再看表结构、索引、字段映射

## 命令索引

命令发现和使用模板详见 references/idp-query.md。

## ClickHouse 安全流程

ClickHouse 查询**必须**：
1. 只知道诊断场景时，先读 `references/idp-query/biz/clickhouse/diagnostic-scenarios.md` 选候选表；已知真实表名时，直接读对应单表文档。
2. 读单表文档确认真实表名、租户字段、时间字段，不预读整个 `references/idp-query/biz/clickhouse/` 目录。
3. 应用日志、CEP 网关、慢请求、慢 SQL、SQL 统计等日志统一查询 `biz-app-log`，SQL 中必须写真实表名。
4. `biz-app-log` 示例 SQL 不使用 `SELECT 1`；如需探测表可查性，用 `SELECT * FROM <table> LIMIT 1`，确保请求路由到真实表。
5. ClickHouse 版 `bi` 查询命令保留 `--dialect clickhouse`。
6. 用 10 分钟采样估算 1 小时数据量。
7. 根据量级选择时间窗口（详见 references/idp-query-clickhouse.md）。
8. **【核心红线】严防 `app_log_dist` 跨天查询超时**：查询 `app_log_dist`（应用日志）表时，绝对禁止仅凭 traceId无时间窗查找。时间窗口默认限制在 6 小时以内，最大绝对不能超过 24 小时（1 天），防止 ClickHouse 扫描巨量分区导致查询超时或服务崩溃。
9. **【定位红线】禁止仅靠单 IP 过滤微服务**：在 K8s 混合部署或多服务共享 IP 的环境中，绝对禁止只通过 `server_ip LIKE '%<IP>%'` 或 `ip = '<IP>'` 来过滤特定服务的日志（例如 APL 执行引擎）。由于共享物理节点，同一 IP 的不同端口（Port）上往往部署了十多个不同的容器服务。凡涉及匹配 IP 定位特定微服务，**必须强制联合 IP 与 Port** 进行精确匹配（如 `server_ip = '<IP>:<PORT>'`），防止数据混淆。

## TraceIdLookup：reqId 反查 traceId

当输入是 CEP 错误码 / reqId / 截图错误码，且 HND / `index.md` 没有可复用的 `traceId/traceIdParsed` 时，本 skill 负责执行 `traceIdLookup`。这是唯一允许用 reqId 作为主过滤条件的阶段；目标是从 `log_cep_dist` 解析出真实 traceId，之后所有查询都切换到 `traceId`。

执行规则：

1. 先确认 `traceIdLookup.source_value` 或 `errorCodeParsed.errorCode`，缺失时调用 `extract_error_anchor` / `parse_traceid` 补齐。
2. 用 `fx-ops idp --profile <env> show columns biz-app-log log_cep_dist -j` 校验字段类型（**单表文档可能 stale，一律以 `show columns` 实时结果为准**）：`reqId` 为 `Array(String)`（故用 `has()`）、`traceId` 为 `String`、时间字段用 `stamp`（`DateTime64`，亦为分区/排序键，过滤最高效）。
3. 用 `biz-app-log` 查询 `log_cep_dist`，谓词固定为 `has(reqId, '<ERROR_CODE>')`，禁止写成 `reqId = ...` 或 `traceId = '<ERROR_CODE>'`。
4. 时间窗优先使用 `errorCodeParsed.timestamp` 或截图时间前后 5 分钟；空结果（traceIdLookup 反查）最多仅允许扩窗 1 轮（到 30m，ambiguous不扩），普通空结果再按 10m -> 1h -> 6h -> 24h 阶梯扩窗（统一扩窗阶梯见 fx-ops 主控「扩窗阶梯权威声明」），并记录扩窗原因。
5. 排序固定使用 `ORDER BY status DESC, request_time DESC`，优先选择真实错误行；多候选时按 status、request_time、errorCode/error、截图时间和租户线索消歧。
6. 查到唯一目标后返回 `context_updates`，至少包含:
- `traceIdLookup.status = "resolved"`
- `traceIdLookup.resolved_traceId`
- `traceId`
- `traceIdParsed.time`
- `traceIdParsed.ea`（若日志行有 ea）
- `tenant_context.ei/ea`（若日志行有 ei/ea）
- `time_window`（锚定到真实错误时间）

如 CEP 行中存在 `rpcId` 字段，**建议**附带：
- `traceIdLookup.resolved_rpcId`（取 status≥400 行的 rpcId）
7. 查不到返回 `status=empty`，`traceIdLookup.status=not_found`；多候选无法裁决返回 `status=partial`，`traceIdLookup.status=ambiguous` 并列出候选。两种情况都不得继续后续链路查询。

**强制前置**：执行以下 SQL 前，必须先完成 `fx-ops idp --profile <profile> show columns biz-app-log log_cep_dist -j`——`reqId` 字段类型以此次 `show columns` 实时返回为准（历史记录：`Array(String)`）。**未经 `show columns` 校验直接执行此 SQL 属于违规，结果无效**。

**已验证通过的标准 SQL**（`reqId` 为 `Array(String)` 时使用；若 `show columns` 返回标量，改用 `reqId = '<code>'`）：

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT stamp, bizName, serverName, server_ip, ei, ea, companyName, traceId, rpcId,
     reqId, uri, status, request_time, request_length, errorCode, error
 FROM log_cep_dist
 WHERE has(reqId, '<ERROR_CODE>')
  AND stamp BETWEEN '<TIME_MINUS_5MIN>' AND '<TIME_PLUS_5MIN>'
 ORDER BY status DESC, request_time DESC
 LIMIT 20" -j
```

> **rpcId 下游精准过滤**：`traceId` = 一次点击/开页；`rpcId` = 该操作下的一次 RPC（字符串为目标态，旧 `x.y.z` 废弃中）。上述 SQL 返回的 `rpcId` 应回传为 `traceIdLookup.resolved_rpcId`（取 status≥400 行）。下游在有 rpcId 列的表追加 `AND rpcId = '<R>'`，避免同 traceId 下其他 RPC 噪声。语义与覆盖矩阵见 `clickhouse/reqId-traceId-rpcId.md`。

## 输出回抛

完成本领域查询后，按 fx-ops 总控回抛协议返回:
- status: completed / partial / empty / error
- findings: 查询结果摘要和假设树判定
- evidence_files: 已落盘的证据文件列表
- confidence: high / medium / low
- route_hint: 编排流必须填写；如需继续分发使用 `need_capability`，已完成且无需下一跳用 `resolved_no_action`
- target_capability: `route_hint=need_capability` 时填写 `tracing` / `monitoring` / `code_search` 等能力类型
- need_further: 人类摘要，不能作为主控唯一下一跳依据

## 输出要求

最终输出必须包含：
- 本次选择的数据源及理由
- 查询安全等级（L1/L2/L3）与收敛条件
- 首轮假设树中当前最成立的一支，以及已排除的分支
- 关键查询结果与证据路径
- 是否需要升级到 `fx-ops-tracing`、`fx-ops-monitoring`、`fx-ops-timeline` 或 `code-search`

## 被调度时的约定

当本 skill 被 fx-ops 编排主控以 sub-agent 方式调度时，遵循以下输入/输出契约：

### 调用方传入

| 参数 | 说明 |
| --- | --- |
| `app` | 目标应用名（可选，用于定位 biz） |
| `traceId` | 原始 traceId（有则传入，用于 `traceId` 字段等值过滤；不得填 CEP 错误码 / reqId） |
| `traceIdParsed` | `extract_error_anchor` / `parse_traceid` 解析结果，含 `time`、`ea`、`uid`、`source/appName`、可选 `queryHint` |
| `errorCodeParsed` | CEP 错误码 / 截图错误码解析结果，含 `errorCode`、`sourceId`、`service`、`timestamp` 等 |
| `traceIdLookup` | reqId / CEP 错误码反查 traceId 的过程记录；`status=pending` 时本 skill 只执行 `log_cep_dist` 小表反查，`status=resolved` 且已回填 `traceId/traceIdParsed/resolved_rpcId` 后，才继续其它查询 |
| `env` | 环境标识（可选） |
| `tenant_context` | 租户范围，含 tenant_id / ei / ea / tenant_name（按需） |
| `time_window` | 查询时间窗口，含 start / end（按需） |
| `query_target_hints` | 查询目标提示，如 "验证订单是否写入"、"查日志错误分布"、"对比上下游数据一致性" 等（可选，用于缩小数据源选择范围） |

含 `traceIdParsed` 时，优先用 `traceIdParsed.time` 派生的 `time_window` 和 `traceIdParsed.ea/uid/source` 缩小查询；含 `errorCodeParsed` / `traceIdLookup` 但缺少 `traceIdParsed` 时，说明还停留在 reqId 转 traceId 阶段，本 skill 只能执行 `log_cep_dist` 小表反查，不得直接查询 `app_log_dist`、`log_error_dist` 等后续链路表。缺失 `time_window` 时不得查询 `app_log_dist` 等大表，应先回到时间解析或小表反查。

### 本 skill 输出

- **数据源选择理由**：为什么选这个 biz / 这个方言（MySQL / MongoDB / ClickHouse）
- **查询结果**：关键数据摘要，含安全等级标注
- **假设树评估**：首轮四类假设（数据缺失/Schema 变更/同步延迟/分片路由）中哪些被验证、哪些被排除

### 证据落盘

- 被调度时：证据保存到调用方指定的 `evidence_dir`，文件命名遵循调用方约定
