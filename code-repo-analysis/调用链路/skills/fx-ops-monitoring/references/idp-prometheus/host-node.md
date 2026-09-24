# K8S Node / 宿主机指标

用于排查 Pod 所在 Node 的 CPU、load、内存、磁盘 IO、网络、socket。当 Pod 延迟高但 Pod 自身资源正常时，优先检查 Node 层。

Pod 的 `host_ip` 标签可映射到 node-exporter 的 `instance` 或 kube-state-metrics 的 `node`。

> [!NOTE]
> 无论是 K8S 容器节点（通过 Pod `host_ip` 标签获取）还是独立部署中间件的虚拟机（例如通过 PostgreSQL `datname` 查到的 `host` 标签 IP），只要获取到其节点 IP，都可以通过 node-exporter 指标，使用 `instance=~".*${node_ip}.*"` 的模板来查询其宿主物理机的运行指标。

## 过滤模板

```text
instance=~".*${host_ip}.*"
```

先发现 node-exporter 的 job：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (job)(node_uname_info)' -j --limit-points 200
```

## CPU

| 目标 | PromQL 模板 |
| --- | --- |
| CPU 使用率 | `100 - avg by (instance)(rate(node_cpu_seconds_total{mode="idle",instance=~".*${host_ip}.*"}[5m])) * 100` |
| CPU iowait | `avg by (instance)(rate(node_cpu_seconds_total{mode="iowait",instance=~".*${host_ip}.*"}[5m])) * 100` |
| Load 1m / 5m / 15m | `node_load1{instance=~".*${host_ip}.*"}` / `node_load5{instance=~".*${host_ip}.*"}` / `node_load15{instance=~".*${host_ip}.*"}` |

## 内存

| 目标 | PromQL 模板 |
| --- | --- |
| 可用内存 | `node_memory_MemAvailable_bytes{instance=~".*${host_ip}.*"}` |
| 总内存 | `node_memory_MemTotal_bytes{instance=~".*${host_ip}.*"}` |
| 内存使用率 | `(1 - node_memory_MemAvailable_bytes{instance=~".*${host_ip}.*"} / node_memory_MemTotal_bytes{instance=~".*${host_ip}.*"}) * 100` |
| buffer | `node_memory_Buffers_bytes{instance=~".*${host_ip}.*"}` |
| cache | `node_memory_Cached_bytes{instance=~".*${host_ip}.*"}` |
| swap 使用率 | `(node_memory_SwapTotal_bytes{instance=~".*${host_ip}.*"} - node_memory_SwapFree_bytes{instance=~".*${host_ip}.*"}) / node_memory_SwapTotal_bytes{instance=~".*${host_ip}.*"} * 100` |

Linux 内存排查优先看 `MemAvailable`，不要只看 free memory。

## 文件系统容量

| 目标 | PromQL 模板 |
| --- | --- |
| 磁盘使用率 | `(1 - node_filesystem_avail_bytes{instance=~".*${host_ip}.*",fstype!~"tmpfs|overlay|squashfs"} / node_filesystem_size_bytes{instance=~".*${host_ip}.*",fstype!~"tmpfs|overlay|squashfs"}) * 100` |
| 可用空间 | `node_filesystem_avail_bytes{instance=~".*${host_ip}.*",fstype!~"tmpfs|overlay|squashfs"}` |
| inode 使用率 | `(1 - node_filesystem_files_free{instance=~".*${host_ip}.*",fstype!~"tmpfs|overlay|squashfs"} / node_filesystem_files{instance=~".*${host_ip}.*",fstype!~"tmpfs|overlay|squashfs"}) * 100` |

过滤掉 `tmpfs`、`overlay`、`squashfs` 等虚拟文件系统，避免 dashboard 被容器挂载点污染。

## 磁盘 IO

| 目标 | PromQL 模板 |
| --- | --- |
| 读吞吐 | `rate(node_disk_read_bytes_total{instance=~".*${host_ip}.*",device!~"loop.*",device!~"ram.*"}[5m])` |
| 写吞吐 | `rate(node_disk_written_bytes_total{instance=~".*${host_ip}.*",device!~"loop.*",device!~"ram.*"}[5m])` |
| 读 IOPS | `rate(node_disk_reads_completed_total{instance=~".*${host_ip}.*",device!~"loop.*",device!~"ram.*"}[5m])` |
| 写 IOPS | `rate(node_disk_writes_completed_total{instance=~".*${host_ip}.*",device!~"loop.*",device!~"ram.*"}[5m])` |
| 每次读耗时 | `rate(node_disk_read_time_seconds_total{instance=~".*${host_ip}.*",device!~"loop.*",device!~"ram.*"}[5m]) / rate(node_disk_reads_completed_total{instance=~".*${host_ip}.*",device!~"loop.*",device!~"ram.*"}[5m])` |
| 每次写耗时 | `rate(node_disk_write_time_seconds_total{instance=~".*${host_ip}.*",device!~"loop.*",device!~"ram.*"}[5m]) / rate(node_disk_writes_completed_total{instance=~".*${host_ip}.*",device!~"loop.*",device!~"ram.*"}[5m])` |
| I/O util | `rate(node_disk_io_time_seconds_total{instance=~".*${host_ip}.*",device!~"loop.*",device!~"ram.*"}[5m]) * 100` |

dashboard 中"每次 IO 读写耗时参考小于 100ms"对应读写耗时模板。结果为秒，展示时通常转成 ms。

## 网络

| 目标 | PromQL 模板 |
| --- | --- |
| 流入 | `sum by (instance)(rate(node_network_receive_bytes_total{instance=~".*${host_ip}.*",device!="lo",device!~"docker.*",device!~"veth.*",device!~"cali.*"}[5m]))` |
| 流出 | `sum by (instance)(rate(node_network_transmit_bytes_total{instance=~".*${host_ip}.*",device!="lo",device!~"docker.*",device!~"veth.*",device!~"cali.*"}[5m]))` |
| 入包 | `sum by (instance)(rate(node_network_receive_packets_total{instance=~".*${host_ip}.*",device!="lo",device!~"docker.*",device!~"veth.*",device!~"cali.*"}[5m]))` |
| 出包 | `sum by (instance)(rate(node_network_transmit_packets_total{instance=~".*${host_ip}.*",device!="lo",device!~"docker.*",device!~"veth.*",device!~"cali.*"}[5m]))` |
| 丢包 | `sum by (instance)(rate(node_network_receive_drop_total{instance=~".*${host_ip}.*",device!="lo",device!~"docker.*",device!~"veth.*",device!~"cali.*"}[5m]) + rate(node_network_transmit_drop_total{instance=~".*${host_ip}.*",device!="lo",device!~"docker.*",device!~"veth.*",device!~"cali.*"}[5m]))` |
| 错误包 | `sum by (instance)(rate(node_network_receive_errs_total{instance=~".*${host_ip}.*",device!="lo",device!~"docker.*",device!~"veth.*",device!~"cali.*"}[5m]) + rate(node_network_transmit_errs_total{instance=~".*${host_ip}.*",device!="lo",device!~"docker.*",device!~"veth.*",device!~"cali.*"}[5m]))` |

## Socket

| 目标 | PromQL 模板 |
| --- | --- |
| 已建立 TCP | `node_netstat_Tcp_CurrEstab{instance=~".*${host_ip}.*"}` |
| TCP time-wait | `node_sockstat_TCP_tw{instance=~".*${host_ip}.*"}` |
| TCP alloc | `node_sockstat_TCP_alloc{instance=~".*${host_ip}.*"}` |
| socket used | `node_sockstat_sockets_used{instance=~".*${host_ip}.*"}` |
| UDP inuse | `node_sockstat_UDP_inuse{instance=~".*${host_ip}.*"}` |

## Range 查询模板

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 '100 - avg by (instance)(rate(node_cpu_seconds_total{mode="idle",instance=~".*${host_ip}.*"}[5m])) * 100' \
 --start "$(date -u -v-30M +%Y-%m-%dT%H:%M:%SZ)" \
 --end "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
 --step "1m" -j
```

## 解读

| 现象 | 优先检查 |
| --- | --- |
| Pod 延迟高但 Pod CPU/内存正常 | Node CPU iowait、磁盘耗时、网络丢包 |
| Node load 高 | CPU 核数、iowait、磁盘 util、进程阻塞 |
| 磁盘 util 接近 100% | 每次 IO 耗时、读写吞吐、IOPS、具体设备 |
| 网络流量高 | node 网络与 Pod 网络同时看，确认是单 Pod 还是整机 |
| socket 激增 | `CurrEstab`、`TCP_tw`、应用连接池、Tomcat 线程池 |
