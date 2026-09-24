# JVM 指标

用于排查 Java 应用的 JVM 内存、GC、Class loading、线程、文件描述符。当前环境存在三类 JVM exporter 配置，指标命名和标签差异较大，排查前必须先确认 job。

## Exporter 差异（已验证）

| 维度 | ① `springboot-actuator` | ② `tke70-k8s1-jvm-exporter` / `k8s*-jvm-exporter` | ③ `k8s1-jvm-exporter`(旧) / `vm-jvm-exporter` |
| --- | --- | --- | --- |
| 占比 | ~5% | ~90%（主力） | ~5% |
| 内存指标名 | `jvm_memory_used_bytes` | `jvm_memory_used_bytes` | `jvm_memory_bytes_used` |
| 内存池指标名 | `jvm_memory_pool_used_bytes` | `jvm_memory_pool_used_bytes` | `jvm_memory_pool_bytes_used` |
| 内存池标签 | `area` + `id`（如 `G1 Eden Space`） | 只有 `area`（heap/nonheap） | 只有 `area`（heap/nonheap） |
| GC 指标名 | `jvm_gc_pause_seconds_count` / `_sum` / `_bucket` | `jvm_gc_collection_seconds_count` / `_sum` | `jvm_gc_collection_seconds_count` / `_sum` |
| GC 标签 | `gc` + `action` + `cause` | `gc` | `gc` |
| 线程指标 | `jvm_threads_live_threads` / `jvm_threads_states_threads` 等 | ❌ 无 | ❌ 无 |
| FD 指标名 | `process_files_open_files` / `process_files_max_files` | `process_open_fds` | `process_open_fds` |
| Class loading | `jvm_classes_loaded_classes` / `jvm_classes_unloaded_classes_total` | ❌ 无 | ❌ 无 |

排查时必须先确认目标 Pod 的 job，再选择对应的指标名：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (job)(jvm_memory_used_bytes{app_name="${app_name}"} or jvm_memory_bytes_used{app_name="${app_name}"})' -j
```

## 先确认 JVM 信息

```bash
# 确认目标应用的 job 和指标命名
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (job,app_name,area)(jvm_memory_used_bytes{app_name="${app_name}",job=~".*jvm-exporter|springboot-actuator"} or jvm_memory_bytes_used{app_name="${app_name}"})' -j
```

## Java 版本与内存池

| Java 版本 | 常见 GC / 内存池名称 |
| --- | --- |
| Java 8 | `PS Eden Space`、`PS Survivor Space`、`PS Old Gen`、`Metaspace`、`Compressed Class Space`、`Code Cache` |
| Java 8 CMS | `Par Eden Space`、`Par Survivor Space`、`CMS Old Gen`、`Metaspace`、`Compressed Class Space` |
| Java 17 | `G1 Eden Space`、`G1 Survivor Space`、`G1 Old Gen`、`Metaspace`、`Compressed Class Space`、`CodeHeap 'non-nmethods'`、`CodeHeap 'profiled nmethods'`、`CodeHeap 'non-profiled nmethods'` |
| Java 21 | 通常同 Java 17；dashboard 样例展示 G1 与 CodeHeap 分区 |
| Java 25 | 预期仍以 Micrometer/JMX 导出的内存池标签为准；不要写死池名，先按 `id` / `pool` 标签发现 |

发现内存池标签：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (area,id)(jvm_memory_used_bytes{app_name="${app_name}",job="springboot-actuator"}) or count by (area)(jvm_memory_used_bytes{app_name="${app_name}",job=~".*jvm-exporter"}) or count by (area)(jvm_memory_bytes_used{app_name="${app_name}"})' -j
```

## 内存

> **命名兼容**：内存指标有两种命名方式，必须用 `or` 兼容查询：
> - Micrometer 命名：`jvm_memory_used_bytes` / `jvm_memory_committed_bytes` / `jvm_memory_max_bytes`
> - JMX exporter 命名：`jvm_memory_bytes_used` / `jvm_memory_bytes_committed` / `jvm_memory_bytes_max`
>
> 以下模板统一使用 `or` 兼容写法，无需按 exporter 类型拆分。

| 目标 | PromQL 模板 |
| --- | --- |
| JVM 总使用内存 | `sum by (pod)(jvm_memory_used_bytes{app_name="${app_name}",job=~".*jvm-exporter|springboot-actuator"} or jvm_memory_bytes_used{app_name="${app_name}"})` |
| JVM 总提交内存 | `sum by (pod)(jvm_memory_committed_bytes{app_name="${app_name}",job=~".*jvm-exporter|springboot-actuator"} or jvm_memory_bytes_committed{app_name="${app_name}"})` |
| JVM 最大内存 | `sum by (pod)(jvm_memory_max_bytes{app_name="${app_name}",job=~".*jvm-exporter|springboot-actuator"} or jvm_memory_bytes_max{app_name="${app_name}"})` |
| Heap 使用 | `sum by (pod)(jvm_memory_used_bytes{app_name="${app_name}",job=~".*jvm-exporter|springboot-actuator",area="heap"} or jvm_memory_bytes_used{app_name="${app_name}",area="heap"})` |
| Heap 使用率 | `sum by (pod)(jvm_memory_used_bytes{app_name="${app_name}",job=~".*jvm-exporter|springboot-actuator",area="heap"} or jvm_memory_bytes_used{app_name="${app_name}",area="heap"}) / sum by (pod)(jvm_memory_max_bytes{app_name="${app_name}",job=~".*jvm-exporter|springboot-actuator",area="heap"} or jvm_memory_bytes_max{app_name="${app_name}",area="heap"}) * 100` |
| Non-Heap 使用 | `sum by (pod)(jvm_memory_used_bytes{app_name="${app_name}",job=~".*jvm-exporter|springboot-actuator",area="nonheap"} or jvm_memory_bytes_used{app_name="${app_name}",area="nonheap"})` |
| 按内存池使用 | `sum by (pod,id)(jvm_memory_used_bytes{app_name="${app_name}",job="springboot-actuator"})`（仅 ① springboot-actuator 有 `id` 标签） |

②③ 没有 `id`/`pool` 标签，无法按内存池拆分。如果 exporter 使用 `pool` 标签而不是 `id` 标签，把 `sum by (pod,id)` 改成 `sum by (pod,pool)`。

## 内存池（Memory Pool）

内存池指标有两种命名方式，必须用 `or` 兼容查询：

- Micrometer 命名：`jvm_memory_pool_used_bytes` / `jvm_memory_pool_committed_bytes` / `jvm_memory_pool_max_bytes`
- JMX exporter 命名：`jvm_memory_pool_bytes_used` / `jvm_memory_pool_bytes_committed` / `jvm_memory_pool_bytes_max`

| 目标 | PromQL 模板 |
| --- | --- |
| 非 Eden 内存池使用 | `sum(jvm_memory_pool_bytes_used{app_name="${app_name}",pool!~".*Eden.*"}) by (app_name,pool) or sum(jvm_memory_pool_used_bytes{app_name="${app_name}",pool!~".*Eden.*"}) by (app_name,pool)` |
| Eden 内存池使用 | `sum(jvm_memory_pool_bytes_used{app_name="${app_name}",pool=~".*Eden.*"}) by (app_name,pool) or sum(jvm_memory_pool_used_bytes{app_name="${app_name}",pool=~".*Eden.*"}) by (app_name,pool)` |
| 内存池总使用 | `sum(jvm_memory_pool_bytes_used{app_name="${app_name}"}) by (app_name) or sum(jvm_memory_pool_used_bytes{app_name="${app_name}"}) by (app_name)` |

注意：内存池指标在 ② 主力 jvm-exporter 上可能只有 `area` 标签而无 `pool`/`id` 标签，此时无法按池拆分，只能用上面的 `jvm_memory_used_bytes{area="heap"} or jvm_memory_bytes_used{area="heap"}` 查询。

## 容器内存与 JVM 内存对齐

dashboard 同时展示"容器角度"和"JVM 角度"。两者不要混用：

| 视角 | 指标 | 排查用途 |
| --- | --- | --- |
| 容器工作集 | `container_memory_working_set_bytes` | 判断是否接近容器 limit、是否可能 Container OOM |
| RSS / 物理占用 | `container_memory_rss` | 近似 Java 进程物理内存，不等同于 heap |
| JVM heap | `jvm_memory_used_bytes{area="heap"}` | 判断 Java 对象内存压力 |
| JVM nonheap | `jvm_memory_used_bytes{area="nonheap"}` | 判断 Metaspace、CodeHeap、Compressed Class Space |
| JVM committed | `jvm_memory_committed_bytes` | JVM 向 OS 承诺的内存，不等同于实际 RSS |

JVM OOM 通常看 heap/nonheap 与 max；Container OOM 优先看 working set 与容器 memory limit。

## GC

GC 指标有两种命名方式，用 `or` 兼容查询：

- Micrometer 命名：`jvm_gc_pause_seconds_count` / `_sum` / `_bucket`（① springboot-actuator）
- JMX exporter 命名：`jvm_gc_collection_seconds_count` / `_sum`（②③）

| 目标 | PromQL 模板 |
| --- | --- |
| GC 次数 / 分钟 | `sum by (pod,gc)(increase(jvm_gc_collection_seconds_count{app_name="${app_name}",job=~".*jvm-exporter"}[1m])) or sum by (pod,action,cause)(increase(jvm_gc_pause_seconds_count{app_name="${app_name}",job="springboot-actuator"}[1m]))` |
| GC 耗时 / 分钟 | `sum by (pod,gc)(increase(jvm_gc_collection_seconds_sum{app_name="${app_name}",job=~".*jvm-exporter"}[1m])) or sum by (pod,action,cause)(increase(jvm_gc_pause_seconds_sum{app_name="${app_name}",job="springboot-actuator"}[1m]))` |
| 平均 GC 耗时 | `sum by (pod,gc)(rate(jvm_gc_collection_seconds_sum{app_name="${app_name}",job=~".*jvm-exporter"}[5m])) / sum by (pod,gc)(rate(jvm_gc_collection_seconds_count{app_name="${app_name}",job=~".*jvm-exporter"}[5m])) or sum by (pod,action,cause)(rate(jvm_gc_pause_seconds_sum{app_name="${app_name}",job="springboot-actuator"}[5m])) / sum by (pod,action,cause)(rate(jvm_gc_pause_seconds_count{app_name="${app_name}",job="springboot-actuator"}[5m]))` |
| GC pause P99（仅 springboot-actuator） | `histogram_quantile(0.99, sum by (le,pod)(rate(jvm_gc_pause_seconds_bucket{app_name="${app_name}",job="springboot-actuator"}[5m])))` |

先确认 GC 指标命名：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (gc)(jvm_gc_collection_seconds_count{app_name="${app_name}",job=~".*jvm-exporter"}) or count by (gc,action,cause)(jvm_gc_pause_seconds_count{app_name="${app_name}",job="springboot-actuator"})' -j
```

## Class loading

仅 ① springboot-actuator 有 class loading 指标。②③ 均无。

| 目标 | PromQL 模板 |
| --- | --- |
| 当前已加载类 | `jvm_classes_loaded_classes{app_name="${app_name}",job="springboot-actuator"}` |
| 卸载类速率 | `rate(jvm_classes_unloaded_classes_total{app_name="${app_name}",job="springboot-actuator"}[5m])` |

类数量持续增长时，结合 Metaspace 使用率判断是否类加载泄漏。

## Threads Count

仅 ① springboot-actuator 有线程指标。②③ 均无。

| 目标 | PromQL 模板 |
| --- | --- |
| 线程总数 | `jvm_threads_live_threads{app_name="${app_name}",job="springboot-actuator"}` |
| daemon 线程 | `jvm_threads_daemon_threads{app_name="${app_name}",job="springboot-actuator"}` |
| peak 线程 | `jvm_threads_peak_threads{app_name="${app_name}",job="springboot-actuator"}` |
| 按状态线程数 | `sum by (pod,state)(jvm_threads_states_threads{app_name="${app_name}",job="springboot-actuator"})` |

`BLOCKED` 异常升高时优先查锁竞争和线程 dump。

## Open File Descriptors

FD 指标有两种命名方式，用 `or` 兼容查询：

- Micrometer 命名：`process_files_open_files` / `process_files_max_files`（① springboot-actuator）
- JMX exporter 命名：`process_open_fds` / `process_max_fds`（②③）

| 目标 | PromQL 模板 |
| --- | --- |
| 打开 FD 数 | `process_open_fds{app_name="${app_name}",job=~".*jvm-exporter"} or process_files_open_files{app_name="${app_name}",job="springboot-actuator"}` |
| 最大 FD 数 | `process_max_fds{app_name="${app_name}",job=~".*jvm-exporter"} or process_files_max_files{app_name="${app_name}",job="springboot-actuator"}` |
| FD 使用率 | `(process_open_fds{app_name="${app_name}",job=~".*jvm-exporter"} or process_files_open_files{app_name="${app_name}",job="springboot-actuator"}) / (process_max_fds{app_name="${app_name}",job=~".*jvm-exporter"} or process_files_max_files{app_name="${app_name}",job="springboot-actuator"}) * 100` |

注意：② 主力 jvm-exporter 可能不暴露 `process_max_fds`，此时 FD 使用率查询的分母为空。

## Range 查询模板

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'sum by (pod,area)(jvm_memory_used_bytes{app_name="${app_name}",job=~".*jvm-exporter|springboot-actuator"} or jvm_memory_bytes_used{app_name="${app_name}"})' \
 --start "$(date -u -v-30M +%Y-%m-%dT%H:%M:%SZ)" \
 --end "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
 --step "1m" -j
```

## 解读

| 现象 | 优先检查 |
| --- | --- |
| Heap 持续上升且 Full GC 后不回落 | heap leak、缓存、对象保留 |
| Non-Heap / Metaspace 持续上升 | 类加载泄漏、动态代理、热加载 |
| GC 次数或耗时突增 | heap 压力、分配速率、老年代占用 |
| Thread BLOCKED 增多 | 锁竞争、同步热点、线程 dump |
| FD 持续升高 | socket/file 未关闭、连接池泄漏 |
| 容器内存高但 JVM heap 不高 | direct buffer、thread stack、native memory、page cache |
