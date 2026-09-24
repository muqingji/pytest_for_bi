# Grafana 看板完整清单

> **维护说明**：本文档记录 foneshare 环境中可用的 Grafana 看板信息。
> 看板 UID、模板变量、面板 ID 以 `fx-ops idp grafana dashboard get --uid <uid>` 实际查询为准。
> 数据采集日期：2026-08-13。

## 1. 看板分类索引

| 类别 | 看板数 | 典型看板 |
|------|--------|----------|
| 日志类 | 8 | ch-log-error, ch-app-log, ch-slow-log, ch-apl |
| 应用服务类 | 8 | pod-jvm-monitor, ch-tomcat, ch-rpc |
| 中间件类 | 12 | pg-global, Redis, RocketMQ, Kafka, ES, MongoDB |
| MQ 类 | 4 | ch-mq-consume, ch-mq-dispatcher, RocketMQ, Kafka |
| 基础设施类 | 6 | single-node, Kubernetes, ClickHouse |
| 巡检告警类 | 8 | 灭火全景图, Sentinel限流, 全网巡检 |
| 全局核心类 | 5 | global-core-dashboard, fast-notifier |

## 2. 日志类看板

### 2.1 CEP 错误日志 - ch-log-error

| 属性 | 值 |
|------|-----|
| UID | `ch-log-error` |
| URL | `/d/ch-log-error/clickhouse-log-error` |
| 面板数 | 25 |
| 数据源 | ClickHouse（默认 `foneshare-clickHouse`） |
| 数据表 | `logger.log_error_dist` |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `datasource` | datasource | 数据源 | 默认 `foneshare-clickHouse`，正则 `.*-clickHouse.*` |
| `cnt` | custom | 返回条数限制 | `0`(不限), `10`, `100`, `1000`；默认 `0` |
| `interval` | interval | 聚合间隔 | `10s`, `30s`, `1m`, `10m`, `30m`, `1h`, `6h`, `12h`, `1d`, `7d`, `14d`, `30d`；默认 `1m` |
| `cluster` | query | 集群 | 动态查询，支持 `All` |
| `app` | query | 应用名 | 动态查询，依赖 `cluster`，支持 `All` |
| `profile` | query | 环境 profile | 动态查询，依赖 `app`，支持 `All` |
| `ea` | query | 企业 ID | 动态查询，依赖 `profile`，支持 `All` |
| `dbName` | query | 数据库名 | 动态查询，依赖 `ea`，支持 `All` |
| `traceId` | query | 链路追踪 ID | 动态查询，依赖 `dbName`，支持 `All` |
| `token` | query | 错误码/Token | 动态查询，支持 `All` |
| `loggerName` | query | 日志类名 | 动态查询，支持 `All` |
| `filter` | adhoc | 自定义过滤 | 无默认值 |
| `condition` | textbox | SQL 条件 | 默认 `1=1` |

**关键面板**：

| ID | 标题 | 类型 |
|----|------|------|
| 2 | count-by-app | timeseries |
| 3 | count-by-token | timeseries |
| 4 | count-by-ea | timeseries |
| 7 | count-by-pod | timeseries |
| 10 | detail | logs |

**适用场景**：错误堆栈、异常分析、按应用/租户/错误码统计

**链接示例**：
```
https://grafana.foneshare.cn/d/ch-log-error?var-app=fs-oncall&from=now-1h&to=now&viewPanel=2
```

### 2.2 CEP 报错 KPI 看板

| 属性 | 值 |
|------|-----|
| UID | `fe884bd1-166e-4426-b73e-1fd40aef995f` |
| URL | `/d/fe884bd1-166e-4426-b73e-1fd40aef995f` |
| 面板数 | 15 |
| 数据源 | ClickHouse |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `interval` | interval | 聚合间隔 | `1m`, `10m`, `30m`, `1h`, `6h`, `12h`, `1d`, `7d`, `14d`, `30d` |

**关键面板**：

| ID | 标题 | 类型 |
|----|------|------|
| 5 | 总数 | timeseries |
| 6 | 总错误数 | stat |
| 7 | 影响企业数 | stat |
| 8 | 影响用户数 | stat |
| 15 | 每日CEP错误数 | status-history |

**适用场景**：CEP 5xx 错误统计、影响范围评估

**链接示例**：
```
https://grafana.foneshare.cn/d/fe884bd1-166e-4426-b73e-1fd40aef995f?from=now-1h&to=now&viewPanel=5
```

### 2.3 应用日志 - ch-app-log

| 属性 | 值 |
|------|-----|
| UID | `ch-app-log` |
| URL | `/d/ch-app-log/clickhouse-app-logs` |
| 面板数 | 14 |
| 数据源 | ClickHouse |
| 数据表 | `logger.app_log_dist` |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `datasource` | datasource | 数据源 | 默认 `foneshare-clickHouse` |
| `cnt` | custom | 返回条数限制 | `0`, `10`, `100`, `1000` |
| `interval` | interval | 聚合间隔 | `10s`, `30s`, `1m`, `10m`, `30m`, `1h`, `6h`, `12h`, `1d`, `7d`, `14d`, `30d` |
| `app` | query | 应用名 | 动态查询，支持 `All` |
| `profile` | query | 环境 profile | 动态查询，支持 `All` |
| `level` | custom | 日志级别 | 支持 `All` |
| `userId` | query | 用户 ID | 动态查询，支持 `All` |
| `filter` | adhoc | 自定义过滤 | 无默认值 |
| `condition` | textbox | SQL 条件 | 默认 `1=1` |

**关键面板**：日志详情（logs）

**适用场景**：应用日志查询、错误日志

**链接示例**：
```
https://grafana.foneshare.cn/d/ch-app-log?var-app=fs-oncall&var-level=ERROR&from=now-1h&to=now
```

### 2.4 慢 SQL 日志 - ch-slow-log

| 属性 | 值 |
|------|-----|
| UID | `ch-slow-log` |
| URL | `/d/ch-slow-log/clickhouse-slow-log` |
| 面板数 | 37 |
| 数据源 | ClickHouse |
| 数据表 | `logger.slow_log_dist` |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `datasource` | datasource | 数据源 | 默认 `foneshare-clickHouse` |
| `interval` | interval | 聚合间隔 | `10s`, `30s`, `1m`, `10m`, `30m`, `1h`, `6h`, `12h`, `1d`, `7d`, `14d`, `30d` |
| `type` | query | 数据库类型 | 动态查询，支持 `All` |
| `dbName` | query | 数据库名 | 动态查询，依赖 `type`，支持 `All` |
| `app` | query | 应用名 | 动态查询，依赖 `dbName`，支持 `All` |
| `cost` | textbox | 耗时阈值(ms) | 默认 `1000`，可输入任意数值 |
| `filter` | adhoc | 自定义过滤 | 无默认值 |
| `clickhouse_adhoc_query` | constant | 表名 | 固定 `logger.slow_log_dist` |
| `condition` | textbox | SQL 条件 | 默认 `1=1` |

**关键面板**：慢查询统计、按数据库/应用分组

**适用场景**：数据库慢查询分析

**链接示例**：
```
https://grafana.foneshare.cn/d/ch-slow-log?var-app=fs-oncall&var-cost=1000&from=now-1h&to=now
```

### 2.5 慢 SQL 分布

| 属性 | 值 |
|------|-----|
| UID | `22aba92e-23e6-49cd-89e0-1cbac84bc4f3` |
| URL | `/d/22aba92e-23e6-49cd-89e0-1cbac84bc4f3/log-slow-sql-dist` |
| 面板数 | 1 |
| 数据源 | ClickHouse / Prometheus |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `env` | custom | 云环境 | 20 个选项（见 §8.2） |
| `namespace` | query | 命名空间 | 动态查询 |
| `datasource_prometheus` | datasource | Prometheus 数据源 | - |
| `datasource_clickhouse` | datasource | ClickHouse 数据源 | - |
| `app` | query | 应用名 | 动态查询 |
| `cost` | textbox | 耗时阈值(ms) | 可输入任意数值 |
| `condition` | textbox | SQL 条件 | - |
| `interval` | interval | 聚合间隔 | - |

**适用场景**：慢 SQL 分布统计（支持多云环境）

**链接示例**：
```
https://grafana.foneshare.cn/d/22aba92e-23e6-49cd-89e0-1cbac84bc4f3?var-env=mengniu&var-app=fs-oncall&from=now-1h&to=now
```

### 2.6 APL 函数日志 - ch-apl

| 属性 | 值 |
|------|-----|
| UID | `ch-apl` |
| URL | `/d/ch-apl/clickhouse-log-apl` |
| 面板数 | 18 |
| 数据源 | ClickHouse（默认 `ClickHouse-biz-log`） |
| 数据表 | `logger.biz_log_function_dist` |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `datasource` | datasource | 数据源 | 默认 `ClickHouse-biz-log` |
| `cnt` | custom | 返回条数限制 | `0`, `10`, `100`, `1000`；默认 `10` |
| `interval` | interval | 聚合间隔 | `1s`, `10s`, `1m`, `10m`, `30m`, `1h`, `6h`, `12h`, `1d`, `7d`, `14d`, `30d` |
| `appName` | query | 应用名 | 动态查询，支持 `All` |
| `ea` | query | 企业 ID | 动态查询，支持 `All` |
| `filter` | adhoc | 自定义过滤 | 无默认值 |
| `clickhouse_adhoc_query` | constant | 表名 | 固定 `logger.biz_log_function_dist` |

**关键面板**：函数执行统计、按应用/租户分组

**适用场景**：APL 函数超时、报错、执行统计

**链接示例**：
```
https://grafana.foneshare.cn/d/ch-apl?var-appName=Btn_Custom_Save&from=now-1h&to=now
```

### 2.7 变更日志 - ch-oplog

| 属性 | 值 |
|------|-----|
| UID | `ch-oplog` |
| URL | `/d/ch-oplog/clickhouse-oplog-changes` |
| 面板数 | 18 |
| 数据源 | ClickHouse |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `datasource` | datasource | 数据源 | 默认 `foneshare-clickHouse` |
| `cnt` | custom | 返回条数限制 | `0`, `10`, `100`, `1000` |
| `interval` | interval | 聚合间隔 | - |
| `db` | query | 数据库名 | 动态查询 |
| `ea` | query | 企业 ID | 动态查询 |
| `object_describe_api_name` | query | 对象 API 名称 | 动态查询 |
| `filter` | adhoc | 自定义过滤 | 无默认值 |
| `condition` | textbox | SQL 条件 | 默认 `1=1` |
| `clickhouse_adhoc_query` | constant | 表名 | - |

**适用场景**：数据变更追踪、操作审计

**链接示例**：
```
https://grafana.foneshare.cn/d/ch-oplog?var-ea=12345&from=now-1h&to=now
```

### 2.8 审计日志 - ch-audit

| 属性 | 值 |
|------|-----|
| UID | `ch-audit` |
| URL | `/d/ch-audit/clickhouse-audit-log` |
| 数据源 | ClickHouse |

**适用场景**：操作审计

## 3. 应用服务类看板

### 3.1 Pod/JVM 监控 - pod-jvm-monitor

| 属性 | 值 |
|------|-----|
| UID | `pod-jvm-monitor` |
| URL | `/d/pod-jvm-monitor/pod-jvm-monitor` |
| 面板数 | 100+ |
| 数据源 | Prometheus（默认 `foneshare-prometheus`） |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `datasource` | datasource | 数据源 | 默认 `foneshare-prometheus`，正则 `.*-prometheus` |
| `k8s_cluster` | query | K8S 集群 | 动态查询 `label_values(kube_namespace_created,k8s_cluster)`；默认 `k8s0` |
| `namespace` | query | 命名空间 | 动态查询，依赖 `k8s_cluster`；默认 `foneshare` |
| `app` | query | 应用名 | 动态查询，依赖 `namespace`；默认 `fs-oncall` |
| `pod` | query | Pod 名称 | 动态查询，依赖 `app` |
| `pod_ip` | query | Pod IP | 动态查询，依赖 `pod` |
| `host_ip` | query | 宿主机 IP | 动态查询，依赖 `pod` |
| `interval` | interval | 聚合间隔 | `1m`, `2m`, `5m`, `10m`, `30m`, `1h`, `6h`；默认 `1m` |
| `job` | constant | Job 匹配 | 固定 `.+-jvm-exporter(-closed)?` |
| `Filters` | adhoc | 自定义过滤 | 无默认值 |

**关键面板**：

| ID | 标题 | 类型 |
|----|------|------|
| 39 | CPU使用情况（所有实例） | timeseries |
| 40 | 内存使用情况（所有实例） | timeseries |
| 42 | JVM GC 频率 | timeseries |
| 45 | Tomcat 线程池 | timeseries |
| 19 | 容器内存使用量 | stat |
| 47 | java占用内存（物理内存） | stat |

**适用场景**：Pod 重启、CPU/内存使用率、JVM GC、堆内存、Tomcat 线程池

**链接示例**：
```
https://grafana.foneshare.cn/d/pod-jvm-monitor?var-k8s_cluster=k8s0&var-namespace=foneshare&var-app=fs-oncall&from=now-1h&to=now&viewPanel=39
```

### 3.2 ClickHouse Tomcat 日志 - ch-tomcat

| 属性 | 值 |
|------|-----|
| UID | `ch-tomcat` |
| URL | `/d/ch-tomcat/clickhouse-tomcat-log` |
| 面板数 | 37 |
| 数据源 | ClickHouse |
| 数据表 | `logger.tomcat_access_log_dist` |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `datasource` | datasource | 数据源 | 默认 `foneshare-clickHouse` |
| `cnt` | custom | 返回条数限制 | `0`, `10`, `100`, `1000` |
| `interval` | interval | 聚合间隔 | - |
| `app` | query | 应用名 | 动态查询，支持 `All` |
| `ea` | query | 企业 ID | 动态查询，支持 `All` |
| `filter` | adhoc | 自定义过滤 | 无默认值 |
| `condition` | textbox | SQL 条件 | 默认 `1=1` |
| `clickhouse_adhoc_query` | constant | 表名 | - |

**关键面板**：请求量、耗时分布、按应用/租户分组

**适用场景**：Tomcat 接口性能分析

**链接示例**：
```
https://grafana.foneshare.cn/d/ch-tomcat?var-app=fs-oncall&from=now-1h&to=now
```

### 3.3 ClickHouse Tomcat 慢查询

| 属性 | 值 |
|------|-----|
| UID | `bdxc9jjplm2o0a` |
| URL | `/d/bdxc9jjplm2o0a/clickhouse-tomcat-slow` |
| 面板数 | 30 |
| 数据源 | ClickHouse |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `datasource` | datasource | 数据源 | 默认 `foneshare-clickHouse` |
| `cnt` | custom | 返回条数限制 | `0`, `10`, `100`, `1000` |
| `interval` | interval | 聚合间隔 | - |
| `app` | query | 应用名 | 动态查询，支持 `All` |
| `ea` | query | 企业 ID | 动态查询，支持 `All` |
| `filter` | adhoc | 自定义过滤 | 无默认值 |
| `condition` | textbox | SQL 条件 | 默认 `1=1` |
| `clickhouse_adhoc_query` | constant | 表名 | - |

**关键面板**：慢接口 TOP、耗时分布

**适用场景**：Tomcat 慢接口分析

**链接示例**：
```
https://grafana.foneshare.cn/d/bdxc9jjplm2o0a?var-app=fs-oncall&from=now-1h&to=now
```

### 3.4 ClickHouse RPC - ch-rpc

| 属性 | 值 |
|------|-----|
| UID | `ch-rpc` |
| URL | `/d/ch-rpc/clickhouse-rpc` |
| 面板数 | 23 |
| 数据源 | ClickHouse |
| 数据表 | `logger.rpc_dist` |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `datasource` | datasource | 数据源 | 默认 `foneshare-clickHouse` |
| `cnt` | custom | 返回条数限制 | `0`, `10`, `100`, `1000` |
| `interval` | interval | 聚合间隔 | `1s`, `10s`, `1m`, `10m`, `30m`, `1h`, `6h`, `12h`, `1d`, `7d`, `14d`, `30d` |
| `app` | query | 应用名 | 动态查询，支持 `All` |
| `server` | query | 服务端 | 动态查询，支持 `All` |
| `profile` | query | 环境 profile | 动态查询，支持 `All` |
| `filter` | adhoc | 自定义过滤 | 无默认值 |
| `condition` | textbox | SQL 条件 | 默认 `1=1` |
| `clickhouse_adhoc_query` | constant | 表名 | 固定 `logger.rpc_dist` |

**关键面板**：调用量、耗时、错误率

**适用场景**：RPC 调用性能分析

**链接示例**：
```
https://grafana.foneshare.cn/d/ch-rpc?var-app=fs-oncall&from=now-1h&to=now
```

### 3.5 RPC 根因分析

| 属性 | 值 |
|------|-----|
| UID | `be95wrtusnf28e` |
| URL | `/d/be95wrtusnf28e/RPC根因分析` |

**适用场景**：RPC 问题定位、调用关系分析

### 3.6 服务调用关系图

| 属性 | 值 |
|------|-----|
| UID | `a7414283-837b-4585-825a-96350aef008f` |
| URL | `/d/a7414283-837b-4585-825a-96350aef008f/服务调用关系图` |

**适用场景**：服务依赖分析、调用拓扑

### 3.7 应用全景图

| 属性 | 值 |
|------|-----|
| UID | `func-app-all` |
| URL | `/d/func-app-all/应用全景图` |

**适用场景**：应用健康度总览

### 3.8 SpringBoot 监控

| 属性 | 值 |
|------|-----|
| UID | `JrQc1xsmk` |
| URL | `/d/JrQc1xsmk/SpringBoot监控` |

**适用场景**：Spring 应用 JVM 指标

## 4. 中间件类看板

### 4.1 PostgreSQL

| 属性 | 值 |
|------|-----|
| UID | `000000039` |
| URL | `/d/000000039/postgresql` |
| 面板数 | 22 |
| 数据源 | Prometheus |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `interval` | interval | 聚合间隔 | - |
| `namespace` | query | 命名空间 | 动态查询 |
| `release` | query | Release 名称 | 动态查询 |
| `instance` | query | 实例 | 动态查询 |
| `datname` | query | 数据库名 | 动态查询，支持 `All` |
| `mode` | query | 模式 | 动态查询，支持 `All` |

**关键面板**：连接数、查询耗时、事务

**适用场景**：PG 性能监控

**链接示例**：
```
https://grafana.foneshare.cn/d/000000039?var-namespace=foneshare&from=now-1h&to=now
```

### 4.2 PostgreSQL Global - pg-global

| 属性 | 值 |
|------|-----|
| UID | `pg-global` |
| URL | `/d/pg-global/postgresql-global` |
| 面板数 | 29 |
| 数据源 | Prometheus |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `datasource` | datasource | 数据源 | 默认 `ksc-prometheus` |
| `k8s_cluster` | query | K8S 集群 | 动态查询 `label_values(pg_up,k8s_cluster)`，支持 `All` |
| `job` | query | Job 名称 | 动态查询，支持 `All` |
| `type` | custom | 类型 | `PAAS : 172.17.12\|13\|52\|53.*\|10.210.62\|63.*`, `BI : 172.17.14\|15\|54\|55.*\|10.210.64\|65.*` |
| `host` | query | 主机 | 动态查询，支持 `All` |
| `host2` | query | 实例 | 动态查询，依赖 `host`，支持 `All` |
| `host3` | query | 服务器 | 动态查询，依赖 `host`，支持 `All` |
| `interval` | interval | 聚合间隔 | `1s`, `1m`, `2m`, `10m`, `30m`, `1h`, `6h`, `12h`, `1d`, `7d`, `14d`, `30d` |
| `Filters` | adhoc | 自定义过滤 | 无默认值 |

**关键面板**：全局监控、负载、连接池

**适用场景**：PG 集群监控

**链接示例**：
```
https://grafana.foneshare.cn/d/pg-global?var-k8s_cluster=k8s0&from=now-1h&to=now
```

### 4.3 PG 负载高快速定位

| 属性 | 值 |
|------|-----|
| UID | `ee3lv70x8idc0f` |
| URL | `/d/ee3lv70x8idc0f/PG负载高快速定位` |

**适用场景**：PG 高负载问题定位

### 4.4 Redis 监控

| 属性 | 值 |
|------|-----|
| UID | `JIeHsmmYMk` |
| URL | `/d/JIeHsmmYMk/Redis监控` |
| 面板数 | 21 |
| 数据源 | Prometheus |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `datasource` | datasource | 数据源 | 默认 `foneshare-prometheus` |
| `vendor` | query | 供应商 | 动态查询 `label_values(redis_up, vendor)` |
| `account` | query | 账号 | 动态查询，依赖 `vendor` |
| `group` | query | 分组 | 动态查询，依赖 `account`，支持 `All` |
| `name` | query | 实例名 | 动态查询，依赖 `group`，支持 `All` |
| `instance` | query | 实例地址 | 动态查询，依赖 `name` |
| `iid` | query | 实例 ID | 动态查询，依赖 `name` |

**关键面板**：连接数、内存使用、命中率

**适用场景**：Redis 性能监控

**链接示例**：
```
https://grafana.foneshare.cn/d/JIeHsmmYMk?var-vendor=tencent&var-account=my-account&from=now-1h&to=now
```

### 4.5 RocketMQ

| 属性 | 值 |
|------|-----|
| UID | `zkVx1w_iz_` |
| URL | `/d/zkVx1w_iz_/rocketmq` |
| 面板数 | 26 |
| 数据源 | Prometheus |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `datasource` | datasource | 数据源 | 默认 `foneshare-prometheus` |
| `k8s_cluster` | query | K8S 集群 | 动态查询 `label_values(kube_namespace_created,k8s_cluster)` |
| `host` | query | 主机 | 动态查询，支持 `All` |
| `job` | query | Job 名称 | 动态查询 |
| `group` | query | 消费组 | 动态查询，支持 `All` |
| `topic` | query | Topic | 动态查询，排除 `%RETRY%.*`，支持 `All` |

**关键面板**：堆积量、消费延迟、TPS

**适用场景**：RocketMQ 监控

**链接示例**：
```
https://grafana.foneshare.cn/d/zkVx1w_iz_?var-k8s_cluster=k8s0&var-topic=my-topic&from=now-1h&to=now
```

### 4.6 MQ 消费监控 - ch-mq-consume

| 属性 | 值 |
|------|-----|
| UID | `behszrvrrlds0f` |
| URL | `/d/behszrvrrlds0f/clickhouse-mq-consume` |
| 面板数 | 11 |
| 数据源 | ClickHouse |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `datasource` | datasource | 数据源 | 默认 `foneshare-clickHouse` |
| `cnt` | custom | 返回条数限制 | `0`, `10`, `100`, `1000` |
| `interval` | interval | 聚合间隔 | - |
| `topic` | query | Topic | 动态查询，支持 `All` |
| `group` | query | 消费组 | 动态查询，支持 `All` |
| `filter` | adhoc | 自定义过滤 | 无默认值 |
| `clickhouse_adhoc_query` | constant | 表名 | - |
| `condition` | textbox | SQL 条件 | - |

**关键面板**：

| ID | 标题 | 类型 |
|----|------|------|
| 5 | delayNum-by-topicAndGroup | timeseries |
| 6 | delayCost-by-topicAndGroup | timeseries |
| 23 | delayNum-by-eaAndgroup | timeseries |
| 19 | count-by-status | timeseries |
| 9 | detail | table |

**适用场景**：MQ 消费延迟、消费状态统计

**链接示例**：
```
https://grafana.foneshare.cn/d/behszrvrrlds0f?var-topic=my-topic&var-group=my-group&from=now-1h&to=now
```

### 4.7 MQ 分发监控 - ch-mq-dispatcher

| 属性 | 值 |
|------|-----|
| UID | `0exGOTBVk` |
| URL | `/d/0exGOTBVk/clickhouse-mq-dispatcher` |
| 面板数 | 20 |
| 数据源 | ClickHouse |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `datasource` | datasource | 数据源 | 默认 `foneshare-clickHouse` |
| `cnt` | custom | 返回条数限制 | `0`, `10`, `100`, `1000` |
| `interval` | interval | 聚合间隔 | - |
| `appName` | query | 应用名 | 动态查询 |
| `porterName` | query | Porter 名称 | 动态查询 |
| `ea` | query | 企业 ID | 动态查询 |
| `apiName` | query | API 名称 | 动态查询 |
| `filter` | adhoc | 自定义过滤 | 无默认值 |
| `clickhouse_adhoc_query` | constant | 表名 | - |
| `condition` | textbox | SQL 条件 | - |

**适用场景**：消息分发监控。`DispatcherReporter` 的 `status` 硬编码 `success`；堆积看 tries/delayCost/remainNum。无 `dispatcher_*` Prometheus 指标。

**关键面板**：remainNum-by-topicAndEaAndAppName、delayCost-by-appNameAndEa、dispatch-by-status、detail（含 tries）。

**链接示例**：
```
https://grafana.foneshare.cn/d/0exGOTBVk?var-appName=my-app&from=now-1h&to=now
```

堆积曲线另见 UID `KYxTQz87k`（`logger.metrics_dist`，tag `dispatcher-delay`）。

### 4.8 MQ 消息积压

| 属性 | 值 |
|------|-----|
| UID | `Lb9O2S-iz` |
| URL | `/d/Lb9O2S-iz/RocketMq消息积压` |

**适用场景**：MQ 堆积监控（RocketMQ 4.x + 腾讯 TDMQ）。**不是** Kafka lag 看板。

### 4.8b Kafka（kafka-exporter）

| 属性 | 值 |
| --- | --- |
| UID | `i8HLvrkiz` |
| URL | `/d/i8HLvrkiz/kafka` |
| 面板数 | 13 |
| 数据源 | Prometheus（默认 `foneshare-prometheus`） |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
| --- | --- | --- | --- |
| `datasource` | datasource | 数据源 | 默认 `foneshare-prometheus` |
| `job` | query | `label_values(kafka_brokers,job)` | 当前值可能是 `kafka3-prometheus-kafka-exporter`；lag 采集常见 `kafka-log-exporter` |
| `cluster` | query | `monitoring_instance` | 支持 `All` |
| `topic_name` | query | Topic | 支持 `All` |
| `group_id` | query | Consumer Group（标签 `consumergroup`） | 支持 `All` |

**关键面板**：Brokers、消费组、延迟合计（`kafka_consumergroup_lag_sum`）、消费积压量 TOP50（`kafka_consumergroup_lag`）、Topic 生产量、预计延迟时间。

**适用场景**：Kafka 消费组 lag。指标名 `kafka_consumergroup_lag`，禁止套用 `rocketmq_*`。TDMQ/CKafka Kafka 名 env-blocked。

**链接示例**：
```
https://grafana.foneshare.cn/d/i8HLvrkiz?var-job=kafka-log-exporter&from=now-1h&to=now
```

### 4.9 Elasticsearch

| 属性 | 值 |
|------|-----|
| UID | `4yyL6dBMk` |
| URL | `/d/4yyL6dBMk/elasticsearch` |
| 面板数 | 54 |
| 数据源 | Prometheus |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `datasource` | datasource | 数据源 | 默认 `foneshare-prometheus` |
| `interval` | interval | 聚合间隔 | `1m`, `10m`, `30m`, `1h`, `6h`, `12h`, `1d`, `7d`, `14d`, `30d` |
| `job` | query | Job 名称 | 动态查询 `label_values(elasticsearch_cluster_health_status, job)`，支持 `All` |
| `cluster` | query | 集群名 | 动态查询，依赖 `job` |
| `name` | query | 节点名 | 动态查询，依赖 `cluster`，支持 `All` |
| `instance` | query | 实例 | 动态查询，依赖 `cluster`，支持 `All` |
| `index` | query | 索引名 | 动态查询，依赖 `name`，支持 `All` |

**关键面板**：集群健康、索引性能、搜索耗时

**适用场景**：ES 性能监控

**链接示例**：
```
https://grafana.foneshare.cn/d/4yyL6dBMk?var-cluster=ES-FONESHARE-03&from=now-1h&to=now
```

### 4.10 MongoDB

| 属性 | 值 |
|------|-----|
| UID | `a96d1359-c20a-46ea-96d8-fec10af3341a` |
| URL | `/d/a96d1359-c20a-46ea-96d8-fec10af3341a/mongodb` |

**适用场景**：MongoDB 连接数、操作耗时

### 4.11 MongoDB 慢查询

| 属性 | 值 |
|------|-----|
| UID | `be6nqn2ep44cga` |
| URL | `/d/be6nqn2ep44cga/clickhouse-mongo-slow-log` |
| 面板数 | 22 |
| 数据源 | ClickHouse |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `datasource` | datasource | 数据源 | 默认 `foneshare-clickHouse` |
| `server` | query | 服务器 | 动态查询，支持 `All` |
| `db_table` | query | 数据库.表 | 动态查询，支持 `All` |
| `appName` | query | 应用名 | 动态查询，支持 `All` |
| `mongo_operator` | query | 操作类型 | 动态查询，支持 `All` |
| `eiEA` | query | 企业 ID | 动态查询，支持 `All` |
| `component` | query | 组件 | 动态查询，支持 `All` |
| `cost` | custom | 耗时阈值(ms) | 可选值 |
| `filter` | adhoc | 自定义过滤 | 无默认值 |
| `condition` | textbox | SQL 条件 | - |
| `clickhouse_adhoc_query` | constant | 表名 | - |

**适用场景**：Mongo 慢查询分析

**链接示例**：
```
https://grafana.foneshare.cn/d/be6nqn2ep44cga?var-appName=my-app&var-cost=1000&from=now-1h&to=now
```

### 4.12 MySQL

| 属性 | 值 |
|------|-----|
| UID | `MQWgroiiz` |
| URL | `/d/MQWgroiiz/mysql` |

**适用场景**：MySQL 监控

## 5. 基础设施类看板

### 5.1 Node Exporter Full

| 属性 | 值 |
|------|-----|
| UID | `single-node` |
| URL | `/d/single-node/node-exporter-full` |
| 面板数 | 152 |
| 数据源 | Prometheus |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `job` | query | Job 名称 | 动态查询 `label_values(node_boot_time_seconds, job)`，支持 `All`；默认选中 `k8s1-node-exporter`, `pg-node-exporter`, `pgbouncer-node-exporter`, `mongo-node-exporter` |
| `node` | query | 节点 IP | 动态查询，依赖 `job` |
| `port` | query | 端口 | 动态查询，依赖 `node`；默认 `9100` |

**关键面板**：CPU、内存、磁盘、网络（152 个面板）

**适用场景**：主机全面监控

**链接示例**：
```
https://grafana.foneshare.cn/d/single-node?var-job=k8s1-node-exporter&var-node=172.17.52.13&from=now-1h&to=now
```

### 5.2 Kubernetes Node

| 属性 | 值 |
|------|-----|
| UID | `7mPcYniz` |
| URL | `/d/7mPcYniz/9-Kubernetes-Node` |

**适用场景**：K8s 节点资源监控

### 5.3 ClickHouse

| 属性 | 值 |
|------|-----|
| UID | `thEkJB_Mz23` |
| URL | `/d/thEkJB_Mz23/clickhouse` |

**适用场景**：ClickHouse 集群监控

### 5.4 Nginx VTS

| 属性 | 值 |
|------|-----|
| UID | `70ABSeViz` |
| URL | `/d/70ABSeViz/Nginx VTS` |

**适用场景**：Nginx 流量监控

### 5.5 Etcd

| 属性 | 值 |
|------|-----|
| UID | `hzhXdzznZn` |
| URL | `/d/hzhXdzznZn/Etcd` |

**适用场景**：Etcd 集群健康

### 5.6 ClickHouse DB Limit

| 属性 | 值 |
|------|-----|
| UID | `eb5b82ba-cd03-41f2-bd68-044ffb494052` |
| URL | `/d/eb5b82ba-cd03-41f2-bd68-044ffb494052/clickhouse-db-limit` |
| 面板数 | 28 |
| 数据源 | ClickHouse |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `datasource` | datasource | 数据源 | 默认 `foneshare-clickHouse` |
| `interval` | interval | 聚合间隔 | - |
| `appName` | query | 应用名 | 动态查询，支持 `All` |
| `dbName` | query | 数据库名 | 动态查询，支持 `All` |
| `ei` | query | 企业 ID | 动态查询，支持 `All` |
| `dbIp` | query | 数据库 IP | 动态查询，支持 `All` |
| `filter` | adhoc | 自定义过滤 | 无默认值 |
| `clickhouse_adhoc_query` | constant | 表名 | - |

**适用场景**：CH 限额监控

**链接示例**：
```
https://grafana.foneshare.cn/d/eb5b82ba-cd03-41f2-bd68-044ffb494052?var-appName=my-app&from=now-1h&to=now
```

## 6. 巡检告警类看板

### 6.1 灭火全景图 - foneshare

| 属性 | 值 |
|------|-----|
| UID | `d515ee47-4818-4340-ab9b-a42c759a1e2c` |
| URL | `/d/d515ee47-4818-4340-ab9b-a42c759a1e2c` |
| 面板数 | 43 |
| 数据源 | Prometheus + ClickHouse |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `env` | custom | 云环境 | 19 个选项（见 §8.2）；默认 `foneshare` |
| `datasource_prometheus` | datasource | Prometheus 数据源 | - |
| `datasource_clickhouse` | datasource | ClickHouse 数据源 | - |

**适用场景**：多云环境综合巡检

**链接示例**：
```
https://grafana.foneshare.cn/d/d515ee47-4818-4340-ab9b-a42c759a1e2c?var-env=mengniu&from=now-1h&to=now
```

### 6.2 灭火全景图 - clouds

| 属性 | 值 |
|------|-----|
| UID | `a4766984-66a2-4a00-94f1-49a7cc76958d` |
| URL | `/d/a4766984-66a2-4a00-94f1-49a7cc76958d` |
| 面板数 | - |
| 数据源 | Prometheus + ClickHouse |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `env` | custom | 云环境 | 25 个选项（最全，见 §8.2） |

**适用场景**：专属云巡检（覆盖最全）

**链接示例**：
```
https://grafana.foneshare.cn/d/a4766984-66a2-4a00-94f1-49a7cc76958d?var-env=mengniu&from=now-1h&to=now
```

### 6.3 全网巡检

| 属性 | 值 |
|------|-----|
| UID | `clickhouse-log-cep-clouds` |
| URL | `/d/clickhouse-log-cep-clouds/全网巡检` |

**适用场景**：日常巡检

### 6.4 Sentinel 接口限流监控

| 属性 | 值 |
|------|-----|
| UID | `sentinel-rate-limit-dashboard` |
| URL | `/d/sentinel-rate-limit-dashboard/Sentinel接口限流监控` |
| 面板数 | 11 |
| 数据源 | ClickHouse |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `datasource` | datasource | 数据源 | 默认 `foneshare-clickHouse` |
| `focusUris` | textbox | 关注的 URI | 支持正则，多个用 `\|` 分隔 |
| `business` | textbox | 业务标识 | 默认 `.*` |
| `profile` | query | 环境 profile | 动态查询，支持 `All` |
| `pod` | query | Pod 名称 | 动态查询，依赖 `profile`，支持 `All` |
| `interface` | query | 接口名 | 动态查询，依赖 `profile`/`pod`，支持 `All` |
| `callerBiz` | query | 调用方业务 | 动态查询，支持 `All` |
| `interval` | interval | 聚合间隔 | `1m`, `10m`, `30m`, `1h`, `6h`, `12h`, `1d`, `7d`, `14d`, `30d` |

**关键面板**：限流统计、按接口/应用分组

**适用场景**：接口限流监控

**链接示例**：
```
https://grafana.foneshare.cn/d/sentinel-rate-limit-dashboard?var-profile=foneshare&from=now-1h&to=now
```

### 6.5 持续报错监控

| 属性 | 值 |
|------|-----|
| UID | `ce2lxrsbruy9sf` |
| URL | `/d/ce2lxrsbruy9sf/持续报错监控-全网` |

**适用场景**：持续错误监控

### 6.6 事件中心

| 属性 | 值 |
|------|-----|
| UID | `a10c8008-2deb-4ea5-863b-7c9d5c1c1f14` |
| URL | `/d/a10c8008-2deb-4ea5-863b-7c9d5c1c1f14/事件中心` |

**适用场景**：事件追踪

### 6.7 资源预警排行

| 属性 | 值 |
|------|-----|
| UID | `ce1c2b36-37c3-4e4b-a5d9-b42f07a0e1e7` |
| URL | `/d/ce1c2b36-37c3-4e4b-a5d9-b42f07a0e1e7/资源预警排行` |

**适用场景**：资源管理

### 6.8 DB 磁盘空间监控

| 属性 | 值 |
|------|-----|
| UID | `cdvgbfufqy7eoa` |
| URL | `/d/cdvgbfufqy7eoa/DB磁盘空间监控` |

**适用场景**：磁盘预警

## 7. 全局核心看板

### 7.1 Global Core Dashboard

| 属性 | 值 |
|------|-----|
| UID | `Q0XU_SQnz` |
| URL | `/d/Q0XU_SQnz/global-core-dashboard` |
| 面板数 | 21 |
| 数据源 | Prometheus + ClickHouse |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `app_name` | query | 应用名 | 动态查询 `label_values(jvm_info, app_name)`，支持 `All` |
| `namespace` | query | 命名空间 | 动态查询，依赖 `app_name`，支持 `All` |
| `pod_name` | query | Pod 名称 | 动态查询，依赖 `namespace`，支持 `All` |
| `es_app` | query | ES 应用 | 动态查询，支持 `All` |
| `mq_instance` | query | MQ 实例 | 动态查询，支持 `All` |

**关键面板**：

| ID | 标题 | 类型 |
|----|------|------|
| 52 | CEP超5秒或者错误 | timeseries |
| 63 | log-error-by-app | timeseries |
| 98 | paas-oplog扫描延迟 | timeseries |
| 100 | dispatcher消费延迟 | timeseries |

**适用场景**：综合监控、快速定位问题

**链接示例**：
```
https://grafana.foneshare.cn/d/Q0XU_SQnz?var-app_name=fs-oncall&from=now-1h&to=now&viewPanel=52
```

### 7.2 Fast Notifier - ch-fast-notifier

| 属性 | 值 |
|------|-----|
| UID | `ch-fast-notifier` |
| URL | `/d/ch-fast-notifier/clickhouse-fast-notifier` |
| 面板数 | 14 |
| 数据源 | ClickHouse（默认 `ClickHouse-biz-log`） |
| 数据表 | `logger.notifier_broadcast_ack_dist` |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `datasource` | datasource | 数据源 | 默认 `ClickHouse-biz-log` |
| `cnt` | custom | 返回条数限制 | `0`, `10`, `100`, `1000`；默认 `0` |
| `interval` | interval | 聚合间隔 | `10s`, `30s`, `1m`, `10m`, `30m`, `1h`, `6h`, `12h`, `1d`, `7d`, `14d`, `30d` |
| `room` | query | 通知房间 | 动态查询，支持 `All` |
| `producer` | query | 生产者 | 动态查询，依赖 `room`，支持 `All` |
| `filter` | adhoc | 自定义过滤 | 无默认值 |
| `clickhouse_adhoc_query` | constant | 表名 | 固定 `logger.notifier_broadcast_ack_dist` |
| `condition` | textbox | SQL 条件 | 默认 `1=1` |

**关键面板**：

| ID | 标题 | 类型 |
|----|------|------|
| 2 | count-by-room | timeseries |
| 3 | cost-by-room | timeseries |
| 4 | count-by-producer | timeseries |
| 12 | count-by-broker | timeseries |
| 10 | detail | table |

**适用场景**：通知监控、消息发送统计

**链接示例**：
```
https://grafana.foneshare.cn/d/ch-fast-notifier?var-room=my-room&from=now-1h&to=now
```

### 7.3 Log Flow - ch-log-flow

| 属性 | 值 |
|------|-----|
| UID | `ZvmNQ8BVz` |
| URL | `/d/ZvmNQ8BVz/clickhouse-log-flow` |
| 面板数 | 18 |
| 数据源 | ClickHouse |

**模板变量**：

| 变量名 | 类型 | 说明 | 选项/默认值 |
|--------|------|------|-------------|
| `datasource` | datasource | 数据源 | 默认 `foneshare-clickHouse` |
| `cnt` | custom | 返回条数限制 | `0`, `10`, `100`, `1000` |
| `interval` | interval | 聚合间隔 | - |
| `appName` | query | 应用名 | 动态查询 |
| `ea` | query | 企业 ID | 动态查询 |
| `objectId` | query | 对象 ID | 动态查询 |
| `filter` | adhoc | 自定义过滤 | 无默认值 |
| `clickhouse_adhoc_query` | constant | 表名 | - |
| `condition` | textbox | SQL 条件 | - |

**适用场景**：日志流量监控

**链接示例**：
```
https://grafana.foneshare.cn/d/ZvmNQ8BVz?var-appName=my-app&from=now-1h&to=now
```

## 8. env 变量速查表

### 8.1 有 env 变量的看板

| 看板 | UID | env 选项数 |
|------|-----|-----------|
| 灭火全景图 - foneshare | `d515ee47-4818-4340-ab9b-a42c759a1e2c` | 19 |
| 灭火全景图 - clouds | `a4766984-66a2-4a00-94f1-49a7cc76958d` | 25（最全） |
| 慢SQL分布 | `22aba92e-23e6-49cd-89e0-1cbac84bc4f3` | 20 |

### 8.2 env 选项完整列表（并集 25 个）

| env 值 | 对应云环境 |
|--------|-----------|
| `foneshare` | 主站（默认） |
| `mengniu` | 蒙牛 |
| `hsyk` | 何氏眼科 |
| `sbt` | 双胞胎 |
| `iflytek` | 科大讯飞 |
| `hisense` | 海信 |
| `xjgc` | 许继 |
| `chinatower` | 铁塔 |
| `yangnongchem` | 扬农 |
| `wuzizui99` | 伍子醉 |
| `hexagonmi` | 海克斯康 |
| `kemaicrm` | 北美等 |
| `teleagi` | 电信 |
| `cpgc` | 中船动力 |
| `wingd` | WinGD |
| `kehua` | 科华 |
| `hws` | 亚马逊-法兰克福 |
| `hwc` | 华为云 |
| `ucd` | 紫光云 |
| `ucd-test` | 测试环境 |
| `ksc` | 亚马逊-香港 |
| `ale` | 钉钉云 |
| `cloudmodel` | 模板云 |
| `allink8s` | allink8s |
| `forsharecrm` | 亚马逊-新加坡 |

## 9. 链接格式模板

### 9.1 通用格式

```
https://grafana.foneshare.cn/d/<uid>?var-<var1>=<value1>&var-<var2>=<value2>&from=<start>&to=<end>&viewPanel=<panel_id>
```

### 9.2 无 env 变量的看板

```
https://grafana.foneshare.cn/d/<uid>?var-datasource=<ds>&var-app=<app>&from=<start>&to=<end>&viewPanel=<id>
```

### 9.3 有 env 变量的看板

```
https://grafana.foneshare.cn/d/<uid>?var-env=<env>&from=<start>&to=<end>
```

### 9.4 时间参数格式

| 格式 | 示例 |
|------|------|
| 相对时间 | `from=now-1h&to=now` |
| 相对时间 | `from=now-15m&to=now` |
| 相对时间 | `from=now-6h&to=now` |
| 绝对时间 | `from=2026-08-13T02:00:00Z&to=2026-08-13T03:30:00Z` |

### 9.5 完整示例

```bash
# CEP 错误 - 按应用查看
https://grafana.foneshare.cn/d/ch-log-error?var-app=fs-oncall&from=now-1h&to=now&viewPanel=2

# Pod JVM - 按应用查看
https://grafana.foneshare.cn/d/pod-jvm-monitor?var-k8s_cluster=k8s0&var-namespace=foneshare&var-app=fs-oncall&from=now-1h&to=now&viewPanel=39

# 灭火全景图 - 蒙牛环境
https://grafana.foneshare.cn/d/d515ee47-4818-4340-ab9b-a42c759a1e2c?var-env=mengniu&from=now-1h&to=now

# PG Global - 按集群查看
https://grafana.foneshare.cn/d/pg-global?var-k8s_cluster=k8s0&from=now-1h&to=now

# RocketMQ - 按 topic 查看
https://grafana.foneshare.cn/d/zkVx1w_iz_?var-k8s_cluster=k8s0&var-topic=my-topic&from=now-1h&to=now

# MQ 消费监控 - 按 topic/group 查看
https://grafana.foneshare.cn/d/behszrvrrlds0f?var-topic=my-topic&var-group=my-group&from=now-1h&to=now

# Global Core Dashboard - 按应用查看
https://grafana.foneshare.cn/d/Q0XU_SQnz?var-app_name=fs-oncall&from=now-1h&to=now&viewPanel=52

# Fast Notifier - 按 room 查看
https://grafana.foneshare.cn/d/ch-fast-notifier?var-room=my-room&from=now-1h&to=now

# Redis - 按 vendor/account 查看
https://grafana.foneshare.cn/d/JIeHsmmYMk?var-vendor=tencent&var-account=my-account&from=now-1h&to=now

# Elasticsearch - 按集群查看
https://grafana.foneshare.cn/d/4yyL6dBMk?var-cluster=ES-FONESHARE-03&from=now-1h&to=now

# Sentinel 限流 - 按 profile 查看
https://grafana.foneshare.cn/d/sentinel-rate-limit-dashboard?var-profile=foneshare&from=now-1h&to=now

# Node Exporter - 按节点查看
https://grafana.foneshare.cn/d/single-node?var-job=k8s1-node-exporter&var-node=172.17.52.13&from=now-1h&to=now
```

## 10. 看板嵌入建议汇总

| 场景 | 推荐看板 | 关键变量 |
|------|----------|----------|
| **CEP 5xx** | `fe884bd1-...` | `interval` |
| **错误堆栈** | `ch-log-error` | `app`, `profile`, `ea`, `traceId` |
| **Pod 重启/CPU/内存** | `pod-jvm-monitor` | `k8s_cluster`, `namespace`, `app`, `pod` |
| **JVM GC** | `pod-jvm-monitor` | `k8s_cluster`, `namespace`, `app`, `pod` |
| **Tomcat 耗时** | `ch-tomcat` | `app`, `ea` |
| **Tomcat 慢查询** | `bdxc9jjplm2o0a` | `app`, `ea` |
| **RPC 调用** | `ch-rpc` | `app`, `server`, `profile` |
| **APL 函数** | `ch-apl` | `appName`, `ea` |
| **慢 SQL** | `ch-slow-log` | `dbName`, `app`, `cost` |
| **应用日志** | `ch-app-log` | `app`, `profile`, `level` |
| **PostgreSQL** | `pg-global` | `k8s_cluster`, `job`, `host` |
| **Redis** | `JIeHsmmYMk` | `vendor`, `account`, `instance` |
| **RocketMQ** | `zkVx1w_iz_` | `k8s_cluster`, `group`, `topic` |
| **Kafka lag** | `i8HLvrkiz` | `job`, `topic_name`, `group_id` |
| **MQ 消费** | `behszrvrrlds0f` | `topic`, `group` |
| **MQ 分发** | `0exGOTBVk` | `appName`, `porterName`, `ea` |
| **dispatcher 堆积** | `KYxTQz87k` | tag `dispatcher-delay`（`logger.metrics_dist`） |
| **Elasticsearch** | `4yyL6dBMk` | `cluster`, `instance`, `index` |
| **MongoDB** | `be6nqn2ep44cga` | `server`, `appName`, `cost` |
| **限流** | `sentinel-rate-limit-dashboard` | `profile`, `pod`, `interface` |
| **主机** | `single-node` | `job`, `node` |
| **多云综合** | `d515ee47-...` | `env` |
| **全局核心** | `Q0XU_SQnz` | `app_name`, `namespace` |
| **通知监控** | `ch-fast-notifier` | `room`, `producer` |
