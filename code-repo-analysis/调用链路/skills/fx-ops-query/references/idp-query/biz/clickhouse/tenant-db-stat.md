# tenant-db-stat

> schema_verified_at: 2026-09-01 | platform: foneshare | source: `show columns biz-app-log tenant_db_stat_dist -j`

**说明**: 租户**数据库表**记录数统计，按租户、数据库、schema、物理表记录每次统计得到的数据行数。用于跨租户容量盘点、租户级**表规模**分析和异常增长排查。与 `tenant_object_stat_dist`（对象粒度）互补：本表是**物理表粒度**，可发现对象表聚合不到的底层表（如 schema_migrations、索引表、非业务表）。

**时间字段**: `_time_second_`（分区键 `toYYYYMMDD(_time_second_)`，TTL 90 天）；快照业务时间用 `createTime`（DateTime64(3)）。

> [!CAUTION]
> **TTL 仅 90 天**（`tenant_object_stat_dist` 是 120 天），长周期趋势上限约 90 天；要求 >90 天的对象级趋势走 `tenant_object_stat_dist`。
>
> **去重口径（与对象表不同）**：主库快照 `status = 'normal'`（注意是字符串 `normal`，**非空串**），排除 `status = 'migrate'` 对端库快照。独立 schema 迁移租户迁移日前主库在 `schema='public'`，迁移日后主库在 `schema='sch_<tenantId>'`，`status='normal'` 两条都取。
>
> **Nullable 字段**：`tenantId`/`ea`/`table`/`bizName`/`num` 均为 Nullable，跨租户盘点用 `isNotNull(tenantId) AND tenantId != ''`，聚合 `num` 用 `sum(num)`（自动忽略 NULL）或 `sumIf(num, isNotNull(num))`。

---

## 表：tenant_db_stat_dist

**说明**: 租户数据库表记录数统计分布式表。每次统计生成一行快照，按 `(tenantId, db, schema, table, status, createTime)` 粒度。

### 存储与索引

> schema_verified_at: 2026-09-01 | platform: foneshare

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'tenant_db_stat', rand())（foneshare）；其它环境 cluster01 |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_nanosecond_) + toIntervalDay(90)` |
| 时间列（查询） | `_time_second_`（分区键）；业务快照时间 `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenantId` | Nullable(String) | 租户 ID（如 `785001`）；keyField；**Nullable**，跨租户盘点须 `isNotNull` 过滤 |
| `ea` | Nullable(String) | 租户账号；keyField；**Nullable** |
| `dialect` | LowCardinality(String) | 源数据库方言，如 `postgresql` |
| `server` | LowCardinality(String) | 源数据库服务地址 |
| `schema` | LowCardinality(String) | 源 schema：`public`=**共享库**（多租户混存，单表含几百租户数据）或 `sch_<tenantId>`=**隔离 schema**（该租户独占）；**去重口径关键列**。迁移 = 共享库 public → 独立实例 + sch_<tenantId> |
| `db` | LowCardinality(String) | 源数据库名，带实例标识（如 `fsdb017072104001`）；**迁移会换实例**，迁移前后 db 名不同。命名规则：`fsdb*`=paas 业务库、`fsbidb*`=bi 数据仓库 |
| `table` | Nullable(String) | **物理表名**（粒度列，非 `apiName`）；**Nullable** |
| `bizName` | Nullable(String) | 业务名称，如 `CRM`；**Nullable** |
| `status` | LowCardinality(String) | **统计状态**：`normal` = 主库快照；`migrate` = 迁移对端库快照。**去重口径关键列**，长周期趋势只取 `status='normal'`（注意是字符串 `normal`，与对象表 `status=''` 不同） |
| `num` | Nullable(Int64) | 记录行数；**Nullable**，聚合用 `sum(num)`（自动忽略 NULL）；CLI 返回为字符串，程序侧 `int()` |
| `createTime` | DateTime64(3, 'Asia/Shanghai') | 统计快照创建时间；按天取快照用 `toDate(createTime)` |
| `_time_second_` | DateTime('Asia/Shanghai') | ClickHouse 写入时间（秒级），分区筛选字段 |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | ClickHouse 写入时间（纳秒级），PRIMARY/ORDER BY 键 |

### 去重口径详解

与 `tenant_object_stat_dist` 同为「主库 + 迁移对端库」双写，但 `status` 取值不同：

| status | schema | 含义 | 是否计入主库趋势 |
| --- | --- | --- | --- |
| `normal` | `public` | 迁移前主库快照（共享库，该租户在共享表中的行数） | ✅ 计入（迁移日之前） |
| `normal` | `sch_<tenantId>` | 迁移后主库快照（隔离 schema，该租户独占实例） | ✅ 计入（迁移日及之后） |
| `migrate` | `public` | 迁移后对端库快照（共享库侧长期冻结） | ❌ 排除 |

**迁移日判定**：同租户 `status='normal'` 且 `schema='sch_<tenantId>'` 的最早 `createTime`。注意 db 表迁移日可能比 object 表**早 1-3 天**（db 表先开始迁移，如租户 785001 db 表迁移日 2026-07-01，object 表 2026-07-03），两表趋势对齐时各取各的迁移日。迁移不仅换 schema，还换 db 实例（如 `fsdb017052062001`→`fsdb017072104001`）。

**长周期趋势 SQL 只需 `WHERE status = 'normal'`**，迁移前 `public` 与迁移后 `sch_<tenantId>` 时间不重叠，`status='normal'` 自动各取一段。

### 查询模板

#### 1. 租户表级数据量按天趋势（近 N 天，主库去重）

```sql
SELECT
    toDate(createTime) AS day,
    db, schema, table,
    sum(num) AS total_records
FROM tenant_db_stat_dist
WHERE tenantId = '<tenantId>'
  AND status = 'normal'
  AND createTime >= now() - INTERVAL 90 DAY
GROUP BY day, db, schema, table
ORDER BY day ASC, total_records DESC
```

> 物理表数量远多于对象数（单租户可达上万表），全量 `GROUP BY day, table` 返回行数可能极大，**务必先落盘 JSON 再摘要**，或先按 Top N 收敛。

#### 2. 最新日 Top N 物理表（主库去重）

```sql
SELECT
    db, schema, table, bizName,
    sum(num) AS total_records
FROM tenant_db_stat_dist
WHERE tenantId = '<tenantId>'
  AND status = 'normal'
  AND toDate(createTime) = (
      SELECT max(toDate(createTime)) FROM tenant_db_stat_dist
      WHERE tenantId = '<tenantId>' AND status = 'normal'
  )
GROUP BY db, schema, table, bizName
ORDER BY total_records DESC
LIMIT 50
```

#### 3. 校验去重口径（排查重复计数）

```sql
SELECT status, schema, count() AS cnt, min(createTime) AS earliest, max(createTime) AS latest
FROM tenant_db_stat_dist
WHERE tenantId = '<tenantId>'
GROUP BY status, schema
ORDER BY cnt DESC
```

> 若 `status='migrate'` 行数与 `status='normal'` 行数接近，说明已完成独立 schema 迁移，叠加会接近翻倍；只取 `status='normal'`。

#### 4. 跨租户表级容量盘点

```sql
SELECT tenantId, ea, db, table, sum(num) AS total_records
FROM tenant_db_stat_dist
WHERE status = 'normal'
  AND isNotNull(tenantId) AND tenantId != ''
  AND createTime >= now() - INTERVAL 1 DAY
GROUP BY tenantId, ea, db, table
ORDER BY total_records DESC
LIMIT 100
```

#### 5. 异常增长排查（单表日增量突增）

```sql
SELECT
    toDate(createTime) AS day, db, schema, table,
    sum(num) AS total_records,
    sum(num) - any(sum(num)) OVER (ORDER BY table, day) AS delta
FROM tenant_db_stat_dist
WHERE tenantId = '<tenantId>' AND status = 'normal'
  AND createTime >= now() - INTERVAL 30 DAY
GROUP BY day, db, schema, table
ORDER BY delta DESC
LIMIT 50
```

### Schema 与 db 命名语义

| db 前缀 | 含义 | 典型表 |
| --- | --- | --- |
| `fsdb*` | paas 业务库（CRM 对象数据） | `mt_data` / `object_data` / `mt_data_extra`（共享大宽表，public 上多租户共用） |
| `fsbidb*` | bi 数据仓库（报表数据） | bi 聚合表 |
| `fsfeed*` | feed 业务库（工作圈/动态数据） | feed 相关表 |

| schema | 语义 | 租户范围 |
| --- | --- | --- |
| `public` | **共享库**，多租户混存 | 单表含几百租户数据，本表 `num` 已按 `tenantId` 切出该租户行数 |
| `sch_<tenantId>` | **隔离 schema**，该租户独占 | 迁移后该租户独占实例 + schema |

**共享宽表**（`mt_data`/`object_data`/`mt_data_extra`）：在 `public` 上是几百租户共用的大宽表，本表按 `tenantId` 统计已切出该租户份额；迁移后该租户的宽表副本落在 `sch_<tenantId>`。趋势分析时无需特殊处理，`status='normal'` + `tenantId` 过滤已覆盖迁移前后两段。

### 注意事项

- **TTL 90 天**：超 90 天快照已过期；要求 >90 天趋势走 `tenant_object_stat_dist`（120 天 TTL）。
- **物理表粒度**：`table` 是物理表名（如 `mt_account`），非对象 `apiName`；含非业务表（schema_migrations、索引表等），容量盘点时可按 `db` 或 `bizName` 收敛。
- **Nullable 字段**：`tenantId`/`ea`/`table`/`num` 均可空，跨租户盘点须 `isNotNull(tenantId) AND tenantId != ''`；`num` 聚合用 `sum(num)`（自动忽略 NULL）。
- **status='normal' 非空串**：与 `tenant_object_stat_dist` 的 `status=''` 不同，两表趋势对齐时注意口径切换。
- **迁移日可能早于对象表**：db 表迁移日可能比 object 表早 1-3 天，两表趋势对齐各取各的迁移日。
- **路由**：`biz-app-log` 为 `fixed` 路由，`show/query` 免传 `--tenant-id`；租户过滤写在 SQL `WHERE`。
- **大租户**：物理表数量可达上万，全量趋势行数极大，**先落盘 JSON 再摘要进模型**，禁止原始大表读进对话。

### 与 tenant_object_stat_dist 的对比

| 维度 | tenant_object_stat_dist | tenant_db_stat_dist |
| --- | --- | --- |
| 粒度 | 对象（`apiName`） | 物理表（`table`） |
| 主库 status | `''`（空串） | `normal` |
| TTL | 120 天 | 90 天 |
| Nullable 字段 | 否 | 是（`tenantId`/`ea`/`table`/`num`） |
| 迁移日 | 通常较晚 | 可能早 1-3 天 |
| 适用场景 | 对象规模、业务量趋势 | 表级容量、异常增长、底层表发现 |

### 相关文档

- [tenant-object-stat.md](./tenant-object-stat.md) — 对象粒度单表文档（互补）
- [biz-app-log.md](./biz-app-log.md) — biz-app-log 全表清单
- fx-ops-scenario → tenant-object-data-trend.md — 基于本表与对象表的「企业数据量趋势」端到端报告能力