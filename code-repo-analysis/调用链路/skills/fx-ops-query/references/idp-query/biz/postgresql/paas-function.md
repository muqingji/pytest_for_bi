> **注意**: `paas-function` **不是** `idp show datasources` 中的 live biz。APL 函数定义/版本请走 `fx-ops-query` 的 function 能力（见 `references/idp-function.md`），禁止 `idp query paas-function`。

<!-- fx-ops-query:curated -->

# paas 函数相关表（PostgreSQL）

自定义函数（也称 APL）定义和插件，通过 `fx-ops idp query paas --tenant-id <id> --sql` 查询。

## 表：mt_udef_function

**说明**: 自定义函数定义表。同一 `api_name` 可存在多个版本（`version`），只有 `is_current = true` 的版本为当前生效版本。

**租户ID字段**: `tenant_id`

### 字段定义

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | varchar | 主键 ID |
| `tenant_id` | varchar | 租户 ID |
| `api_name` | varchar | 函数 API 名称（同一 api_name 可多版本） |
| `binding_object_api_name` | varchar | 绑定的对象 API 名称 |
| `function_name` | varchar | 函数显示名称 |
| `parameters` | jsonb | 参数列表（JSON） |
| `return_type` | varchar | 返回值类型 |
| `body` | varchar | 函数体 |
| `application` | varchar | 所属应用 |
| `name_space` | varchar | 命名空间 |
| `last_modified_time` | bigint | 最后修改时间（时间戳） |
| `last_modified_by` | varchar | 最后修改人 ID |
| `created_by` | varchar | 创建人 ID |
| `create_time` | bigint | 创建时间（时间戳） |
| `is_current` | bool | 是否为当前生效版本 |
| `is_deleted` | bool | 是否已删除 |
| `version` | int | 版本号 |

### 版本机制

- 同一 `api_name` 可以有多个版本行，递增 `version`
- `is_current = true` 的行是当前生效的版本，其余为历史版本
- 查询生效函数时加 `WHERE is_current = true AND is_deleted = false`

---

## 表：mt_function_plugin

**说明**: 函数插件表。

**租户ID字段**: `tenant_id`

### 字段定义

| 字段 | 类型 | 说明 |
|------|------|------|
| `tenant_id` | varchar | 租户 ID |
| `last_modified_time` | bigint | 最后修改时间（时间戳） |

> 注：该表完整字段需通过 `table get` 或 `information_schema.columns` 获取，schema 发现仅返回索引列。

---

## 查询示例

```bash
# 查租户所有生效函数
fx-ops idp --profile <profile> query paas --tenant-id 74164 --sql "SELECT api_name, function_name, binding_object_api_name, return_type, version FROM mt_udef_function WHERE tenant_id = '74164' AND is_current = true AND is_deleted = false ORDER BY api_name" -j

# 查某个函数所有版本
fx-ops idp --profile <profile> query paas --tenant-id 74164 --sql "SELECT api_name, version, is_current, is_deleted, created_time FROM mt_udef_function WHERE tenant_id = '74164' AND api_name = 'myFunc__c' ORDER BY version" -j
```

## 相关文档

- ../../../idp-function.md — 函数查询入口
- ../../../idp-query-sql.md — PostgreSQL 查询规则
- ../clickhouse/biz-log-function.md — ClickHouse 函数日志表
