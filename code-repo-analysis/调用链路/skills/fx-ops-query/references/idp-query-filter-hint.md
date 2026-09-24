# filterHint 与表级筛选模板

业务库（MySQL / PostgreSQL / MongoDB）的租户筛选 **不** 靠 Agent 猜列名，而靠 IDP Schema API 返回的 `filterHint` 与本 skill 中的 biz 参考文档。拼 SQL 前必须走完本流程。

## 数据从哪来

| 层级 | 来源 | API 字段 |
| --- | --- | --- |
| 表级筛选 | `show columns -j` 返回的 `filterHint`（租户列、时间列、WHERE 模板） | `filterHint.queryTemplate` 等 |
| 字段含义 | `show columns -j` 自省；biz 文档中的 **表字段说明**；ClickHouse 另见 `clickhouse/<table>.md` 单表文档 | `columns` / 文档表格 |
| 兜底 | 仅有候选租户/时间列、无模板时 | `queryTemplate` 为 `null` |

各 biz 筛选与字段索引见 `idp-query/biz/<dialect>/<biz>.md`；复杂子查询表以该文档 **「复杂筛选表」** 章节为准（手写整理页如 `postgresql/paas-function.md` 优先）。

## 必读命令

```bash
# 1. 表列表（fixed 路由可免 --tenant-id；tenant-route 必填）
fx-ops idp --profile <profile> show tables <biz> -j
fx-ops idp --profile <profile> show tables <biz> --tenant-id <EI> -j   # tenant-route

# 2. 单表结构 + filterHint（必须用 JSON）
fx-ops idp --profile <profile> show columns <biz> <table> -j
# 双方言加 --dialect；tenant-route 加 --tenant-id

# 3. 企业账号 EA（多数 filterHint 模板需要，不是 EI）
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j
```

**注意**:
- CLI 的 text 输出 **不显示** `queryTemplate`；只有 `-j` 能看到 `table.filterHint.queryTemplate`。
- **CLI 免 `-t` ≠ SQL 免租户条件**：fixed 路由只表示连接/路由不依赖 tenant；WHERE 仍按 `queryTemplate` / 业务文档拼租户过滤。
- 旧 biz 名映射见 [biz/index.md](./idp-query/biz/index.md)（`open-oauth`→`openapi` 等）。

## filterHint 字段

```json
{
 "tenantColumn": { "name": "ea", "type": "string", "indexed": true },
 "timeColumn": { "name": "update_time", "type": "datetime", "indexed": false },
 "queryTemplate": "`ea`=$tenantAccount"
}
```

| 字段 | 含义 |
| --- | --- |
| `tenantColumn.name` | 主租户列（守卫与提示用） |
| `timeColumn` | 推荐增量/时间窗列；可能为 `null` |
| `queryTemplate` | 归一化后的 WHERE 片段模板；可能为 `null` |

### 占位符（服务端已归一化）

| 模板中 | 替换为 |
| --- | --- |
| `$tenantId` | 请求中的 EI（`--tenant-id`） |
| `$tenantAccount` | 企业账号 EA，来自 `tenant get` 的 `tenantAccount` |

历史占位符（如 `$tenant_id`、`$ea`）在 API 中已归一化为上述二者。

## 拼 SQL（MySQL / PostgreSQL）

1. 有 `queryTemplate`：将 `$tenantAccount` / `$tenantId` 换成 **带单引号** 的字面量（注意 SQL 转义 `'` → `''`）。
2. 将模板内 `` `col` `` 按方言转换：MySQL/ClickHouse 保留反引号；PostgreSQL 可转为 `"col"`。
3. 组装：

```sql
SELECT * FROM <table> WHERE <filled_template> LIMIT 100
```

4. **无** `queryTemplate`：用 `tenantColumn.name` 手写，例如 `WHERE ea = '<EA>' LIMIT 100`。

### 复杂模板（无单列租户条件或含子查询）

`queryTemplate` 中常见：

- 未使用单列租户占位，整段为子查询或关联条件
- 模板含 `IN (SELECT ... FROM ... WHERE fs_corp_id=$tenant_account ...)`

**禁止** 简化为 `WHERE tenant_id = <EI>`。必须把 **整段** `queryTemplate` 填入 WHERE，并使用 **EA** 替换 `$tenantAccount`。

示例（mail / `email_activity`）：

```sql
SELECT * FROM email_activity
WHERE email_id IN (
 SELECT DISTINCT id FROM email
 WHERE fs_corp_id = '<EA>' AND status IN (1, 5)
)
LIMIT 20
```

各 biz 复杂表清单见 `idp-query/biz/<dialect>/<biz>.md` 的 **「复杂筛选表」** 章节。

## 拼 MongoDB filter

`queryTemplate` 常为 JSON，例如 `{"tenantId":"$tenantAccount"}`：

1. 替换占位符（字符串 **不加** SQL 引号）。
2. 填入 `fx-ops idp query <biz> --collection <name> --filter '<JSON>'`。

## 与执行守卫的关系

| 机制 | 作用 |
| --- | --- |
| `queryTemplate` | **UX 辅助**，帮助写 WHERE |
| `tenant-enforcement` | 执行前 **强制** 校验 SQL/Mongo 是否满足已注册的表级租户筛选规则 |

模板填错仍可能返回 `tenant_filter_missing` / `tenant_filter_mismatch`（400）。

## 多方言同名 biz

下列 biz **同名多 dialect**，未指定会 `dialect_required`：

| biz | dialects | 文档 |
| --- | --- | --- |
| `bi` | postgresql + clickhouse | [biz/bi.md](./idp-query/biz/bi.md) |
| `enterprise-relation` | postgresql + mongodb | [postgresql](./idp-query/biz/postgresql/enterprise-relation.md) / [mongodb](./idp-query/biz/mongodb/enterprise-relation.md) |
| `open-message` | mysql + mongodb | [mysql](./idp-query/biz/mysql/open-message.md) / [mongodb](./idp-query/biz/mongodb/open-message.md) |

- `show tables` / `show columns` / `query`：必须 `--dialect <d>`，或使用别名 `<biz>-<dialect>`（如 `bi-postgresql`、`enterprise-relation-mongodb`）
- **禁止**对双方言 biz 省略 dialect 直接 `query bi` / `query enterprise-relation` / `query open-message`

## 快速对照

| 场景 | 做法 |
| --- | --- |
| 不知有哪些 biz | `show datasources -j` |
| 双方言选哪个库 | 读上表对应文档，显式 `--dialect` |
| 不知有哪些表 | `show tables <biz> [-t <EI>] -j`（fixed 可免 `-t`） |
| 不知字段与模板 | `show columns <biz> T -j` |
| 模板用 EA | `tenant get --tenant-id <EI> -j` |
| 正则/分表名 | 先 `show tables`，再对实际表名 `show columns` |
| 复杂子查询表 | 读 `idp-query/biz/<dialect>/<biz>.md` §复杂筛选表 |
| 旧 biz 名 | 见 [biz/index.md](./idp-query/biz/index.md) 2026-08 映射 |

## 相关文档

- 表发现命令：idp-query-table.md
- SQL 执行：idp-query-sql.md
- MongoDB：idp-query-mongodb.md
- 各 biz 表级规则：`idp-query/biz/mysql/index.md`、`postgresql/index.md`、`mongodb/index.md`
