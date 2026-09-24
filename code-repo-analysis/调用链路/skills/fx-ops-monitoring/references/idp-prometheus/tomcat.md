# Tomcat 指标

用于排查 Spring Boot / Tomcat HTTP 连接线程池、请求量、耗时、错误、队列和连接。

## 当前环境已验证结论

| 指标 | 状态 |
| --- | --- |
| `tomcat_threads_current_threads` | **不存在**，当前环境未采集 |
| `tomcat_threads_busy_threads` | **不存在**，当前环境未采集 |
| `tomcat_threads_config_max_threads` | **不存在**，当前环境未采集 |
| `tomcat_global_request_seconds_count` | **不存在**，当前环境未采集 |
| `tomcat_global_error_total` | **不存在**，当前环境未采集 |
| `http_server_requests_seconds_count` | ✅ 存在（仅 springboot-actuator 应用） |

当前环境 Spring Boot 应用使用 Micrometer 暴露 `http_server_requests_seconds_*` 系列指标，而非传统 Tomcat JMX 指标。排查 Tomcat 层时优先使用 `http_server_requests_seconds_*`。

## 先确认指标命名

```bash
# 检查 http_server_requests 指标（推荐，仅 springboot-actuator 应用有）
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (__name__)(http_server_requests_seconds_count{app_name="${app_name}",job="springboot-actuator"})' -j

# 检查传统 Tomcat 指标（当前环境不存在，仅作参考）
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (__name__)(tomcat_threads_current_threads{app_name="${app_name}"})' -j
```

## http_server_requests（推荐，springboot-actuator 应用）

| 目标 | PromQL 模板 |
| --- | --- |
| 请求速率（按 URI） | `sum by (uri,method,status)(rate(http_server_requests_seconds_count{app_name="${app_name}",job="springboot-actuator"}[1m]))` |
| 平均耗时（按 URI） | `sum by (uri,method)(rate(http_server_requests_seconds_sum{app_name="${app_name}",job="springboot-actuator"}[5m])) / sum by (uri,method)(rate(http_server_requests_seconds_count{app_name="${app_name}",job="springboot-actuator"}[5m]))` |
| P99 耗时 | `histogram_quantile(0.99, sum by (le,uri)(rate(http_server_requests_seconds_bucket{app_name="${app_name}",job="springboot-actuator"}[5m])))` |
| 错误请求速率（5xx） | `sum by (uri,method)(rate(http_server_requests_seconds_count{app_name="${app_name}",job="springboot-actuator",status=~"5.."}[1m]))` |

## 线程池（传统 Tomcat JMX，当前环境不存在）

以下模板仅作参考，当前环境未采集 `tomcat_*` 指标：

| 目标 | Micrometer 模板 | JMX / 自定义模板 |
| --- | --- | --- |
| 当前线程数 | `tomcat_threads_current_threads{app_name="${app_name}"}` | `tomcat_executor_http_currentthreadcount{app_name="${app_name}"}` |
| 忙碌线程数 | `tomcat_threads_busy_threads{app_name="${app_name}"}` | `tomcat_executor_http_activecount{app_name="${app_name}"}` |
| 最大线程数 | `tomcat_threads_config_max_threads{app_name="${app_name}"}` | `tomcat_executor_http_maxthreads{app_name="${app_name}"}` |
| 线程使用率 | `tomcat_threads_busy_threads{app_name="${app_name}"} / tomcat_threads_config_max_threads{app_name="${app_name}"} * 100` | `tomcat_executor_http_activecount{app_name="${app_name}"} / tomcat_executor_http_maxthreads{app_name="${app_name}"} * 100` |

## 请求量、耗时、错误（传统 Tomcat JMX，当前环境不存在）

以下模板仅作参考，当前环境未采集 `tomcat_*` 指标：

| 目标 | PromQL 模板 |
| --- | --- |
| 请求速率 | `sum by (pod)(rate(tomcat_global_request_seconds_count{app_name="${app_name}"}[1m]))` |
| 平均耗时 | `sum by (pod)(rate(tomcat_global_request_seconds_sum{app_name="${app_name}"}[5m])) / sum by (pod)(rate(tomcat_global_request_seconds_count{app_name="${app_name}"}[5m]))` |
| 错误速率 | `sum by (pod)(rate(tomcat_global_error_total{app_name="${app_name}"}[1m]))` |

## 连接（传统 Tomcat JMX，当前环境不存在）

以下模板仅作参考，当前环境未采集 `tomcat_*` 指标：

| 目标 | PromQL 模板 |
| --- | --- |
| 当前连接数 | `tomcat_connections_current_connections{app_name="${app_name}"}` |
| keep-alive 连接 | `tomcat_connections_keepalive_current_connections{app_name="${app_name}"}` |
| 最大连接数配置 | `tomcat_connections_config_max_connections{app_name="${app_name}"}` |
| 连接使用率 | `tomcat_connections_current_connections{app_name="${app_name}"} / tomcat_connections_config_max_connections{app_name="${app_name}"} * 100` |

## Range 查询模板

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'sum by (uri,method,status)(rate(http_server_requests_seconds_count{app_name="${app_name}",job="springboot-actuator"}[1m]))' \
 --start "$(date -u -v-30M +%Y-%m-%dT%H:%M:%SZ)" \
 --end "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
 --step "1m" -j
```

## 解读

| 现象 | 优先检查 |
| --- | --- |
| busy/max 长时间高 | Tomcat 线程池饱和、慢请求、下游阻塞 |
| 请求速率正常但耗时升高 | Tomcat 线程、JVM GC、DB/Redis/外部 HTTP |
| 错误速率升高 | `status`、`uri`；Prometheus 只能看到聚合错误指标，不能看到异常堆栈或单请求 trace |
| 连接数高 | keep-alive、客户端连接池、负载均衡连接复用 |
