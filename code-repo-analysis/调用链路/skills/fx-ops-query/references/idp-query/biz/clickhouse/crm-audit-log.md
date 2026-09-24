# crm-audit-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**方言**: `clickhouse`
**说明**: CRM 审计日志，记录用户对 CRM 对象的业务操作和审计详情。
**租户 ID**: 需要 `--tenant-id` 传 EI；租户条件仍必须写进 SQL。
**查询入口**: `fx-ops idp query crm-audit-log`

下列内容是表级租户筛选参考。执行前用 `show columns crm-audit-log <name> -j` 核对实时 schema、`filterHint` 和列类型；文档不能替代运行时结果。

## 名称和路由边界

`crm-audit-log` 是 CLI biz，`audit_log` 是当前常用逻辑表名，路由返回的 `dbName`、候选配置名和物理表名不是同一个概念。某些环境的 `show tables` 可能返回 `audit_log_permanent` 或带后缀的候选名，但这不等于该名称可以在当前路由直接查询。

固定规则：

- `show tables` 只用于发现候选表，不能据此断言表真实存在。
- 对候选表执行 `show columns`；只有返回正常 schema 的名称才允许进入 SQL。
- 如果运行时 `audit_log` 可查、`audit_log_permanent` 返回 `Table not found`，使用 `audit_log`，不要自行拼接永久表或时间分片名。
- 不要为了绕过空结果，猜测 `audit_log_202601`、`audit_log_permanent` 或其他物理分片。路由 fallback、历史存储和 TTL 由平台返回结果说明。
- 查询结果必须记录 CLI biz、逻辑表名、实际路由数据库名、schema 校验结果和查询时间窗。

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables crm-audit-log -j
fx-ops idp --profile <profile> show columns crm-audit-log audit_log -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j
fx-ops idp --profile <profile> query crm-audit-log --tenant-id <EI> --sql "<SQL>" -j
```

`--tenant-id` 传 EI；SQL 中的 `tenantId` 也传同一个 EI。不要把 EA 或中文企业名称填入 `tenantId`。

## 布局审计字段口径

| 字段 | 口径 | 审计用途 |
| --- | --- | --- |
| `tenantId` | EI，`String` | 生产租户隔离 |
| `objectName` | 对象名称，实测可出现对象 API 名 | 优先按对象 API 名过滤 |
| `module` | 模块/对象 API 线索 | 与 `objectName` 交叉核对，不替代对象字段 |
| `textMessage` | 文本消息，可能包含中文对象名称 | 中文名称辅助核对，不能代替 API 名 |
| `operation` | `LowCardinality(String)` | 当前布局样本使用字符串值 `'3'`，先用样本确认再套用 |
| `bizOperationName` | 业务操作名 | 布局审计使用 `'update_layout'` |
| `operationTime` | `DateTime64(3, 'Asia/Shanghai')` | 使用北京时间半开区间 |
| `traceId` | 链路追踪 ID | 串联 CEP、metadata 和其它变更源 |
| `userId` / `userName` | 审计记录操作人 | 需与 CEP 和变更事件对齐后再做责任归因 |
| `jsonMessage` | JSON 文本详情 | 只作为已命中记录的补充，不作为没有记录时的主过滤条件 |

## 布局查询模板

先用小范围 `count` 和分组确认过滤口径，再查询明细。`operation` 是字符串，不能写成未校验的数值条件。

```sql
SELECT
  objectName,
  module,
  textMessage,
  operation,
  bizOperationName,
  count() AS records,
  uniqExact(traceId) AS traces,
  min(operationTime) AS first_operation_time,
  max(operationTime) AS last_operation_time
FROM audit_log
WHERE tenantId = '<EI>'
  AND operationTime >= toDateTime64('<START>', 3, 'Asia/Shanghai')
  AND operationTime < toDateTime64('<END>', 3, 'Asia/Shanghai')
  AND bizOperationName = 'update_layout'
  AND operation = '3'
GROUP BY objectName, module, textMessage, operation, bizOperationName
ORDER BY first_operation_time ASC
LIMIT 500
```

单对象明细同时保留 API 名和中文名，避免把显示名误传给结构化字段：

```sql
SELECT
  operationTime,
  traceId,
  userId,
  userName,
  module,
  objectName,
  textMessage,
  operation,
  bizOperationName,
  jsonMessage
FROM audit_log
WHERE tenantId = '<EI>'
  AND operationTime >= toDateTime64('<START>', 3, 'Asia/Shanghai')
  AND operationTime < toDateTime64('<END>', 3, 'Asia/Shanghai')
  AND bizOperationName = 'update_layout'
  AND operation = '3'
  AND (objectName = '<ObjectApiName>' OR textMessage = '<ObjectDisplayName>')
ORDER BY operationTime ASC
LIMIT 500
```

`objectName = '<ObjectApiName>'` 是主条件，`textMessage = '<ObjectDisplayName>'` 只是辅助条件。若 OR 查询命中混合对象，改为 API 名和中文名分开查询并在证据中记录各自结果。

## 空结果处理

`audit_log` 空结果的准确语义是：在当前路由、租户、时间窗和过滤条件下，本表没有返回行。它不能直接推出“没有布局操作”。

空结果时依次执行：

1. 用 `show columns` 确认实际逻辑表和字段类型。
2. 分别用对象 API 名和中文名复核 `objectName`、`textMessage`，同时检查 `module`。
3. 保留租户、时间、`bizOperationName` 和 `operation`，暂时去掉对象条件，确认是不是名称过滤错误。
4. 按相同窗口查询 metadata changes，再用命中的 trace 查 CEP 操作路径。
5. 用窄时间窗、租户和布局表条件查询 oplog；记录每个源的 `hit`、`empty`、`error` 或 `out_of_range`。

最终结果应写成类似：`audit_log=empty; metadata=hit; cep=hit; oplog=before_after_empty`，不能简化成“未发生布局操作”。

## 结构与索引参考

以下为整理过的常用字段；运行时仍以 `show columns` 为准。

| 字段 | 类型/说明 |
| --- | --- |
| `id` | `String`，记录 ID |
| `tenantId` | `String`，租户 EI |
| `userId` / `userName` | 操作人 ID 和名称 |
| `traceId` | `String`，链路 ID |
| `module` / `objectName` | 模块和对象名称线索 |
| `objectId` | 对象记录 ID，布局审计可能为空 |
| `operation` | `LowCardinality(String)`，操作类型 |
| `bizOperationName` | 业务操作名称 |
| `operationTime` | `DateTime64(3, 'Asia/Shanghai')` |
| `textMessage` / `internationalTextMessage` | 文本和国际化消息 |
| `jsonMessage` | JSON 消息详情 |
| `operationObject` / `memo` | 操作对象和备注 |

常见排序键为 `(tenantId, module, objectId, operationTime, id)`；不要因此省略时间和租户条件。

## 相关查询能力

- metadata 变更事件需要关注对象 API、trace、user、状态和实际覆盖窗口。
- CEP 需要关注请求 URI、`operate`、用户线索和同一 trace。
- oplog 需要检查 before/after 是否非空并可还原组件差异。
- `mt_ui_component` 只用于当前态校验，`last_modified_by` 不能单独作为历史责任人。
- 对象级审计输出必须按对象分开统计，并区分批次 trace 数和布局明细数。
