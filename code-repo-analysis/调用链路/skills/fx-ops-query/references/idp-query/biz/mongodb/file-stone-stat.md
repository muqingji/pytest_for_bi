# file-stone-stat

**方言**: `mongodb` 
**说明**: 企业文件存储容量与用量统计（warehouse / EnterpriseFileStats），一行一企业；与 file-stone 分片文件元数据互补 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）


下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns file-stone-stat <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query file-stone-stat`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables file-stone-stat --dialect mongodb -j
fx-ops idp --profile <profile> show columns file-stone-stat EnterpriseFileStats --dialect mongodb -j
fx-ops idp --profile <profile> query file-stone-stat --collection EnterpriseFileStats --filter '<JSON>' -j
```

## 关键约束

- **不传 `--tenant-id`**：固定直连路由，不要求租户身份
- **无强制租户列**：查询时自行在 filter 中用 `EA` 做多企业筛选（支持 `$in`）
- **TD 未必都有**：部分文档无 `TD` 字段，勿作默认过滤键
- **时间字段为 number 毫秒**：`CT`、`LUT` 是 `long` 类型 Unix 毫秒（非 `Date`/ISO 字符串）

## 统计

- 表级筛选条目: **1**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **0**
- 使用 `$tenant_account` / EA: **0**（平台不注入租户条件，查询方自行在 filter 中用 EA）

## 其他表

无强制租户列，平台不自动注入筛选条件。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `EnterpriseFileStats` | - | `LUT` | - |

### EnterpriseFileStats 字段参考

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_id` | object | MongoDB 主键 |
| `EA` | string | 企业账号；常见 `EA_1` 索引，多租户过滤首选（如 `$in`） |
| `NA` | string | 企业名称；**部分文档可能缺失** |
| `TD` | string | 租户 ID 字符串；**未必都有**，勿作默认过滤键 |
| `CT` | long | 创建时间，**number 类型 Unix 毫秒**（非 Date） |
| `LUT` | long | 最后更新时间，**number 类型 Unix 毫秒**；时间范围过滤主字段 |
| `LQ` | long | 已购容量（字节，Int64） |
| `UQ` | long | 已用容量（字节，Int64） |
| `FC` | long | 文件总数 |
| `PS` | int | 产品状态 |
| `VS` | int | 版本标识 |

### 查询示例

```bash
# 多企业批量查询（优先用 EA，有索引）
fx-ops idp --profile <profile> query file-stone-stat \
  --collection EnterpriseFileStats \
  --filter '{"EA":{"$in":["ea1","ea2","ea3"]}}' \
  --limit 50 \
  -j

# 按时间范围过滤（LUT 为毫秒时间戳）
fx-ops idp --profile <profile> query file-stone-stat \
  --collection EnterpriseFileStats \
  --filter '{"LUT":{"$gte":1761897600000}}' \
  --limit 100 \
  -j
```
