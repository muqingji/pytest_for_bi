# cep-agg（CEP SLA / 趋势聚合）

> schema_verified_at: 2026-08-01 | platform: v5.10.0
> 底层库：**agg_sla**（通过 `biz-app-log` 集群统一查询，SQL 只写表名）

**说明**: CEP 网关请求分钟级聚合统计表，按业务和 URI 在 5 分钟粒度汇总请求量、耗时、失败数及流量大小。

**统一约定**:

- 查询入口：`fx-ops idp query biz-app-log --sql "SELECT ... FROM <表名> ..."`
- `failCount` / `slowCount` 为聚合计数；`slowCount` 口径为慢请求 **> 3s**（表描述）
- 多数表 **无** `ei`/`traceId`；企业维度表用 `ea`
- 时间列：天表用 `day`（`Date`），分钟表用 `stamp`（`DateTime`，5 分钟桶）

---

## 表选型

| 表名 | 粒度 | 维度 | 租户键 | 典型用途 |
| --- | --- | --- | --- | --- |
| `cep_minute_dist` | 5 分钟 | `bizName` + `uri2` | 无 | 故障窗口内 URI/业务失败与慢请求曲线 |
| `cep_ea_dist` | 5 分钟 | `bizName` + `ea` | `ea` | 某企业故障窗口内请求/失败趋势 |
| `cep_daily_dist` | 天 | `bizName` + `uri2` | 无 | 按天 URI 容量与失败趋势（长周期） |
| `cep_ea_daily_dist` | 天 | `bizName` + `ea` | `ea` | 按天企业维度 SLA / 失败率 |
| `cep_daily_ea_uid_dist` | 天 | `ea` | `ea` | 企业日 PV/UV（AggregateFunction） |

TTL 参考：分钟表 `cep_minute_dist` 约 90 天；`cep_ea_dist` 约 366 天；天表多为 `day + 740 天`。

---

## 表：cep_minute_dist

**说明**: CEP 网关请求分钟级聚合统计表，按业务和 URI 在 5 分钟粒度汇总请求量、耗时、失败数及流量大小。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster01', 'agg_sla', 'cep_minute_local', rand()) |
| PARTITION BY | `toYYYYMMDD(stamp)` |
| PRIMARY KEY | `(stamp, bizName, uri2)` |
| ORDER BY | `(stamp, bizName, uri2)` |
| TTL | `toDate(stamp) + toIntervalDay(90)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `stamp` |

CEP 网关请求 **5 分钟** 聚合（业务 + URI）。

### 存储特征

- **ENGINE**: `Distributed('cluster01', 'agg_sla', 'cep_minute_local', rand())`
- **PARTITION BY**: `toYYYYMMDD(stamp)`
- **PRIMARY KEY / ORDER BY**: `(stamp, bizName, uri2)`
- **TTL**: `toDate(stamp) + toIntervalDay(90)`

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `stamp` | DateTime | 5 分钟聚合时间戳 |
| `bizName` | LowCardinality(String) | 业务名称 |
| `uri2` | String | 对 URI 做聚合和规范化处理后的路径；进行统计分析或筛选过滤时优先使用 uri2 |
| `totalCount` | Int64 | 总请求次数 |
| `totalCost` | Float64 | 总耗时（毫秒） |
| `failCount` | Int64 | 失败请求次数 |
| `slowCount` | Int64 | 慢请求次数（> 3s） |
| `requestSize` | Int64 | 请求总字节数 |
| `responseSize` | Int64 | 响应总字节数 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 时间 | `stamp` |

### 查询示例

```bash
# 故障窗口内按 URI 看失败/慢请求
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT stamp, bizName, uri2, totalCount, failCount, slowCount, totalCost FROM cep_minute_dist WHERE bizName = '<BIZNAME>' AND stamp BETWEEN '<T-1h>' AND '<T+30m>' ORDER BY failCount DESC LIMIT 50"

# 5 分钟失败率曲线
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT stamp, sum(totalCount) AS total, sum(failCount) AS fail, if(sum(totalCount)=0, 0, sum(failCount)/sum(totalCount)) AS fail_rate FROM cep_minute_dist WHERE stamp >= now() - INTERVAL 6 HOUR GROUP BY stamp ORDER BY stamp"
```

---

## 表：cep_ea_dist

**说明**: CEP 网关请求企业维度分钟级聚合统计表，按业务和企业账号在 5 分钟粒度汇总请求量、耗时、失败数及流量大小。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster01', 'agg_sla', 'cep_ea_local', rand()) |
| PARTITION BY | `toYYYYMMDD(stamp)` |
| PRIMARY KEY | `(stamp, bizName, ea)` |
| ORDER BY | `(stamp, bizName, ea)` |
| TTL | `toDate(stamp) + toIntervalDay(366)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `stamp` |

CEP 网关请求 **企业维度 5 分钟** 聚合。

### 存储特征

- **ENGINE**: `Distributed('cluster01', 'agg_sla', 'cep_ea_local', rand())`
- **PARTITION BY**: `toYYYYMMDD(stamp)`
- **PRIMARY KEY / ORDER BY**: `(stamp, bizName, ea)`
- **TTL**: `toDate(stamp) + toIntervalDay(366)`

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `stamp` | DateTime | 5 分钟聚合时间戳 |
| `bizName` | LowCardinality(String) | 业务名称 |
| `ea` | String | 企业账号名称 |
| `totalCount` | Int64 | 总请求次数 |
| `totalCost` | Float64 | 总耗时（毫秒） |
| `failCount` | Int64 | 失败请求次数 |
| `slowCount` | Int64 | 慢请求次数（> 3s） |
| `requestSize` | Int64 | 请求总字节数 |
| `responseSize` | Int64 | 响应总字节数 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户账号 | `ea` |
| 时间 | `stamp` |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT stamp, bizName, ea, totalCount, failCount, slowCount, totalCost FROM cep_ea_dist WHERE ea = '<EA>' AND stamp >= now() - INTERVAL 2 HOUR ORDER BY stamp DESC LIMIT 50"
```

---

## 表：cep_daily_dist

**说明**: CEP 网关请求按天聚合统计表，按业务名称和 URI 维度汇总请求量、耗时、失败数及流量大小。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster01', 'agg_sla', 'cep_daily_local', rand()) |
| PARTITION BY | `toYYYYMMDD(day)` |
| PRIMARY KEY | `(day, bizName, uri2)` |
| ORDER BY | `(day, bizName, uri2)` |
| TTL | `day + toIntervalDay(740)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `day` |

CEP 网关请求 **按天** 聚合（业务 + URI）。

### 存储特征

- **ENGINE**: `Distributed('cluster01', 'agg_sla', 'cep_daily_local', rand())`
- **PARTITION BY**: `toYYYYMMDD(day)`
- **PRIMARY KEY / ORDER BY**: `(day, bizName, uri2)`
- **TTL**: `day + toIntervalDay(740)`

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `day` | Date | 统计日期 |
| `bizName` | LowCardinality(String) | 业务名称 |
| `uri2` | String | 对 URI 做聚合和规范化处理后的路径；进行统计分析或筛选过滤时优先使用 uri2 |
| `totalCount` | Int64 | 总请求次数 |
| `totalCost` | Float64 | 总耗时（毫秒） |
| `failCount` | Int64 | 失败请求次数 |
| `slowCount` | Int64 | 慢请求次数（> 3s） |
| `requestSize` | Int64 | 请求总字节数 |
| `responseSize` | Int64 | 响应总字节数 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 时间 | `day` |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT day, bizName, uri2, totalCount, failCount, slowCount FROM cep_daily_dist WHERE day >= today() - 7 AND bizName = '<BIZNAME>' ORDER BY failCount DESC LIMIT 50"
```

---

## 表：cep_ea_daily_dist

**说明**: CEP 网关请求按天企业维度聚合统计表，按业务和企业账号汇总请求量、耗时、失败数及流量大小。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster01', 'agg_sla', 'cep_ea_daily_local', rand()) |
| PARTITION BY | `toYYYYMMDD(day)` |
| PRIMARY KEY | `(day, bizName, ea)` |
| ORDER BY | `(day, bizName, ea)` |
| TTL | `day + toIntervalDay(740)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `day` |

CEP 网关请求 **按天企业维度** 聚合。

### 存储特征

- **ENGINE**: `Distributed('cluster01', 'agg_sla', 'cep_ea_daily_local', rand())`
- **PARTITION BY**: `toYYYYMMDD(day)`
- **PRIMARY KEY / ORDER BY**: `(day, bizName, ea)`
- **TTL**: `day + toIntervalDay(740)`

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `day` | Date | 统计日期 |
| `bizName` | LowCardinality(String) | 业务名称 |
| `ea` | String | 企业账号名称 |
| `totalCount` | Int64 | 总请求次数 |
| `totalCost` | Float64 | 总耗时（毫秒） |
| `failCount` | Int64 | 失败请求次数 |
| `slowCount` | Int64 | 慢请求次数（> 3s） |
| `requestSize` | Int64 | 请求总字节数 |
| `responseSize` | Int64 | 响应总字节数 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户账号 | `ea` |
| 时间 | `day` |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT day, bizName, ea, totalCount, failCount, if(totalCount=0,0,failCount/totalCount) AS fail_rate, totalCost FROM cep_ea_daily_dist WHERE ea = '<EA>' AND day >= today() - 14 ORDER BY day DESC, failCount DESC LIMIT 50"
```

---

## 表：cep_daily_ea_uid_dist

**说明**: CEP 网关请求按天 PV/UV 聚合表，按企业账号维度统计每日的请求 PV 和独立用户 UV，使用 AggregateFunction 存储以便下钻。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster01', 'agg_sla', 'cep_daily_ea_uid_local', rand()) |
| PARTITION BY | `toYYYYMM(day)` |
| PRIMARY KEY | — |
| ORDER BY | `(day, ea)` |
| TTL | — |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `day` |

CEP 网关按天 **PV/UV**（企业账号维度）。`pv`/`uv` 为 **AggregateFunction** 状态列，查询必须用 Merge 函数，禁止直接 `SELECT pv, uv`。

### 存储特征

- **ENGINE**: `Distributed('cluster01', 'agg_sla', 'cep_daily_ea_uid_local', rand())`
- **PARTITION BY**: `toYYYYMM(day)`
- **ORDER BY**: `(day, ea)`

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `day` | Date | 统计日期 |
| `ea` | String | 企业账号名称 |
| `pv` | AggregateFunction(count, Nullable(Int32)) | 请求 PV（使用 countState 聚合） |
| `uv` | AggregateFunction(uniq, String) | 独立用户 UV（使用 uniqState 聚合） |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户账号 | `ea` |
| 时间 | `day` |

### 查询示例

```bash
# 企业日 PV/UV（必须 Merge）
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT day, ea, countMerge(pv) AS pv, uniqMerge(uv) AS uv FROM cep_daily_ea_uid_dist WHERE ea = '<EA>' AND day >= today() - 7 GROUP BY day, ea ORDER BY day DESC"

# 多企业按天 UV TopN
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT day, ea, uniqMerge(uv) AS uv FROM cep_daily_ea_uid_dist WHERE day = today() - 1 GROUP BY day, ea ORDER BY uv DESC LIMIT 20"
```

> 直接 `SELECT pv` 会返回二进制状态或类型错误；统一 `countMerge(pv)` / `uniqMerge(uv)`，并在 `GROUP BY` 中带上维度列。

---

## 与明细表的配合

| 步骤 | 表 | 目的 |
| --- | --- | --- |
| 1. 看趋势 | `cep_minute_dist` / `cep_ea_dist` | 锁定故障时间窗与放大业务/URI/企业 |
| 2. 看长周期 | `cep_daily_dist` / `cep_ea_daily_dist` | 日环比、容量与失败率基线 |
| 3. 看活跃度 | `cep_daily_ea_uid_dist` | 企业 PV/UV 是否异常下跌 |
| 4. 下钻明细 | `log_cep_dist` 或 `kpi_cep` | 取 `traceId`/`reqId`/错误文案 |

---

## 相关文档

- [log-cep.md](./log-cep.md) — 全量 CEP 明细 `log_cep_dist`
- [kpi-cep.md](./kpi-cep.md) — KPI/异常明细 `kpi_cep`
- [index.md](./index.md) — ClickHouse 表定义索引
