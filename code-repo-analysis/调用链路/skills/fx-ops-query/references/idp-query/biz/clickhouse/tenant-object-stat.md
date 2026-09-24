# tenant-object-stat

> schema_verified_at: 2026-09-01 | platform: foneshare | source: `show columns biz-app-log tenant_object_stat_dist -j`

**说明**: 租户对象记录数统计，按租户、对象 API 名称、物理表记录每次统计得到的数据行数。用于查看租户有哪些对象、每个对象有多少数据，以及跨租户对象规模分析。**长周期趋势/容量分析的主表**，单日快照查询走 `_time_second_` 分区。

**时间字段**: `_time_second_`（分区键 `toYYYYMMDD(_time_second_)`，TTL 120 天）；快照业务时间用 `createTime`（DateTime64(3)）。

> [!CAUTION]
> **去重口径（核心）**：该表同时存在主库快照与迁移对端库快照，叠加会重复计数（实测单租户可虚高 +99M）。长周期趋势/容量盘点**必须**只取主库快照 `status = ''`，排除 `status = 'migrate'` 对端库快照。独立 Schema 迁移租户存在迁移日切换：迁移前主库在 `schema='public'`，迁移后主库在 `schema='sch_<tenantId>'`，`status=''` 两条都取即可（不同 schema、不重叠）。

---

## 表：tenant_object_stat_dist

**说明**: 租户对象记录数统计分布式表。每次统计生成一行快照，按 `(tenantId, apiName, schema, status, createTime)` 粒度。

### 存储与索引

> schema_verified_at: 2026-09-01 | platform: foneshare

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'tenant_object_stat', rand())（foneshare）；其它环境 cluster01 |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(120)` |
| 时间列（查询） | `_time_second_`（分区键）；业务快照时间 `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenantId` | String | 租户 ID（如 `785001`）；keyField |
| `ea` | String | 租户账号（如 `gdsj2023`）；keyField |
| `dialect` | LowCardinality(String) | 源数据库方言，如 `postgresql` |
| `server` | LowCardinality(String) | 源数据库服务地址 |
| `schema` | LowCardinality(String) | 源 schema：`public`=**共享库**（多租户混存，单表含几百租户数据）或 `sch_<tenantId>`=**隔离 schema**（该租户独占）；**去重口径关键列**。迁移 = 共享库 public → 独立实例 + sch_<tenantId> |
| `db` | LowCardinality(String) | 源数据库名，带实例标识（如 `fsdb017072104001`）；**迁移会换实例**，迁移前后 db 名不同。命名规则：`fsdb*`=paas 业务库、`fsbidb*`=bi 数据仓库 |
| `table` | String | 物理表名 |
| `bizName` | LowCardinality(String) | 业务名称，如 `CRM` |
| `apiName` | String | 对象 API 名称；**含非业务对象行**（如 `zh_cn`/`ja_jp`/`vi_vn` 等多语言资源行，`num` 很小），排名前先按命名/`bizName` 剔噪 |
| `status` | LowCardinality(String) | **统计状态/目标库标识**：`''`（空串）= 主库快照；`migrate` = 迁移对端库快照。**去重口径关键列**，长周期趋势只取 `status=''` |
| `num` | Int64 | 记录行数（注意 CLI 返回为字符串，聚合前 `CAST` 或在程序侧 `int()`） |
| `createTime` | DateTime64(3, 'Asia/Shanghai') | 统计快照创建时间；按天取快照用 `toDate(createTime)` |
| `_time_second_` | DateTime | ClickHouse 写入时间（秒级），分区筛选字段 |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | ClickHouse 写入时间（纳秒级），PRIMARY/ORDER BY 键 |

### 去重口径详解

该表为「主库 + 迁移对端库」双写，`status` 区分两者：

| status | schema | 含义 | 是否计入主库趋势 |
| --- | --- | --- | --- |
| `''`（空串） | `public` | 迁移前主库快照（共享库，该租户在共享表中的行数） | ✅ 计入（迁移日之前） |
| `''`（空串） | `sch_<tenantId>` | 迁移后主库快照（隔离 schema，该租户独占实例） | ✅ 计入（迁移日及之后） |
| `migrate` | `public` | 迁移后对端库快照（共享库侧长期冻结） | ❌ 排除 |
| `migrate` | `sch_<tenantId>` | 迁移期间短暂出现的对端快照 | ❌ 排除 |

**迁移日判定**：同租户 `status=''` 且 `schema='sch_<tenantId>'` 的最早 `createTime` 即迁移完成日（如租户 785001 为 `2026-07-03`）。迁移不仅换 schema，还换 db 实例（如 `fsdb017052062001`→`fsdb017072104001`）。迁移日前主库在 `public`，迁移日及之后主库在 `sch_<tenantId>`。

**长周期趋势 SQL 只需 `WHERE status = ''`**，无需额外按 schema 切分——迁移前 `public` 与迁移后 `sch_<tenantId>` 是不同 schema、时间不重叠，`status=''` 自动各取一段。

### 查询模板

#### 1. 租户数据量按天趋势（近 N 天，主库去重）

```sql
SELECT
    toDate(createTime) AS day,
    apiName,
    schema,
    sum(num) AS total_records
FROM tenant_object_stat_dist
WHERE tenantId = '<tenantId>'
  AND ea = '<ea>'
  AND status = ''
  AND createTime >= now() - INTERVAL 90 DAY
GROUP BY day, apiName, schema
ORDER BY day ASC, total_records DESC
```

> 聚合到天时用 `toDate(createTime)`；`schema` 保留在 GROUP BY 用于核对迁移切换，趋势绘图时可再按 day 合并（程序侧 `day < 迁移日 AND schema='public'` 与 `day >= 迁移日 AND schema='sch_*'` 两段拼接）。

#### 2. 最新日 Top N 对象（主库去重）

```sql
SELECT
    apiName,
    schema,
    sum(num) AS total_records
FROM tenant_object_stat_dist
WHERE tenantId = '<tenantId>'
  AND status = ''
  AND toDate(createTime) = (
      SELECT max(toDate(createTime)) FROM tenant_object_stat_dist
      WHERE tenantId = '<tenantId>' AND status = ''
  )
GROUP BY apiName, schema
ORDER BY total_records DESC
LIMIT 20
```

#### 3. 校验去重口径（排查重复计数）

```sql
SELECT status, schema, count() AS cnt, min(createTime) AS earliest, max(createTime) AS latest
FROM tenant_object_stat_dist
WHERE tenantId = '<tenantId>'
GROUP BY status, schema
ORDER BY cnt DESC
```

> 若 `status='migrate'` 行数与 `status=''` 行数接近，说明该租户已完成独立 schema 迁移，叠加会接近翻倍；只取 `status=''` 即可。

#### 4. 跨租户对象规模排名（容量盘点）

```sql
SELECT tenantId, ea, apiName, sum(num) AS total_records
FROM tenant_object_stat_dist
WHERE status = ''
  AND createTime >= now() - INTERVAL 1 DAY
GROUP BY tenantId, ea, apiName
ORDER BY total_records DESC
LIMIT 100
```

### Schema 与 db 命名语义

| db 前缀 | 含义 | 典型对象 |
| --- | --- | --- |
| `fsdb*` | paas 业务库（CRM 对象数据） | SalesOrderProductObj / SalesOrderObj / CheckinsObj 等业务对象 |
| `fsbidb*` | bi 数据仓库（报表数据） | bi 聚合对象 |
| `fsfeed*` | feed 业务库（工作圈/动态数据） | feed 相关对象 |

| schema | 语义 | 租户范围 |
| --- | --- | --- |
| `public` | **共享库**，多租户混存 | 单表含几百租户数据，本表 `num` 已按 `tenantId` 切出该租户行数 |
| `sch_<tenantId>` | **隔离 schema**，该租户独占 | 迁移后该租户独占实例 + schema |

### 注意事项

- **CLI 返回 `num` 为字符串**：`fx-ops idp query biz-app-log` 的统一信封 `data.items` 为二维数组，`num` 列按 `Int64` 写出但经 JSON 序列化为字符串，程序侧聚合前须 `int()`。
- **非业务对象行**：`apiName` 含 `zh_cn`/`ja_jp`/`vi_vn`/`zh_tw` 等多语言资源行（`num` 通常 ≤ 数百），Top 排名前按命名或 `bizName` 剔噪，避免污染对象清单。
- **TTL 120 天**：超 120 天的快照已过期，长周期趋势上限约 120 天；要求 ≥120 天需走 `tenant_db_stat_dist` 或其它长保留源。
- **路由**：`biz-app-log` 为 `fixed` 路由，`show/query` 免传 `--tenant-id`；租户过滤写在 SQL `WHERE`。
- **大租户**：单租户对象数可达数千、日快照行数上万，全量 `GROUP BY day, apiName` 返回行数可能破万，程序侧先落盘 JSON 再摘要进模型，禁止把原始大表读进对话（见 fx-ops `cost-optimization.md`）。

### 相关文档

- [biz-app-log.md](./biz-app-log.md) — biz-app-log 全表清单与本表速查行
- fx-ops-scenario → tenant-object-data-trend.md — 基于本表的「企业对象数据量趋势」端到端报告能力（触发词、流程、HTML 模板）