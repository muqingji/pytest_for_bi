# foneshare 腾讯云公网负载均衡指标

用于按指标名解释 **foneshare** 环境、腾讯云 **公网负载均衡（Public CLB）** 的 Prometheus 监控信号。覆盖四类：客户端 ↔ LB、LB ↔ 后端 RS、丢包/限速/容量使用率、健康检查。

本文件只做指标说明。不覆盖内网 LB、其他云厂商、其他环境；不改告警规则或采集配置；不写入凭据或采集地址。

查询时 `--profile foneshare`。先按指标名对照下表，不要把客户端侧与 RS 侧写混。

## 单位约定

单位以本表「文档单位」为准。与腾讯云控制台/文档冲突时，同时保留文档单位标注，**不自行换算或统一单位**。

| 差异项 | 文档单位 | 不要改成 |
| --- | --- | --- |
| `ClientNewConn`（`qce_lb_public_clientnewconn_max`） | 个/秒（文档） | 个/分钟 |
| `NewConn`（`qce_lb_public_newconn_sum`） | 个/分钟（文档） | 个/秒 |
| `InDropBits` / `OutDropBits` | Byte（文档） | bit / Mbps |

`NewActiveConn` 只解释到「新建活跃连接相关（命名对应 NewActiveConn）」，不要编造更细的业务定义。

## 发现查询

确认 `qce_lb_public_*` 是否存在后再按名称解释。宽前缀查询可能 502，优先 instant、限制点数：

```bash
fx-ops idp --profile foneshare prometheus query --promql \
 'count by (__name__)({__name__=~"qce_lb_public_.*"})' -j --limit-points 100
```

标签因采集链路而异。先用小范围 instant 查询确认后再加 matcher；不要假设与 `qce_rocketmq_*` 标签完全相同。

## 客户端 ↔ LB

| Prometheus 指标 | 文档英文名 | 含义 | 单位（文档） |
| --- | --- | --- | --- |
| `qce_lb_public_clientconnum_max` | ClientConnum | 客户端到 LB 的活跃连接数 | 个 |
| `qce_lb_public_clientinactiveconn_max` | ClientInactiveConn | 客户端到 LB 的非活跃连接数 | 个 |
| `qce_lb_public_clientconcurconn_max` | ClientConcurConn | 客户端到 LB 的并发连接数 | 个 |
| `qce_lb_public_clientnewconn_max` | ClientNewConn | 客户端到 LB 的新建连接数 | 个/秒（文档） |
| `qce_lb_public_clientinpkg_max` | ClientInpkg | 客户端到 LB 的入包量 | 个/秒 |
| `qce_lb_public_clientoutpkg_max` | ClientOutpkg | LB 到客户端的出包量 | 个/秒 |
| `qce_lb_public_clientintraffic_max` | ClientIntraffic | 客户端到 LB 的入带宽 | Mbps |
| `qce_lb_public_clientouttraffic_max` | ClientOuttraffic | LB 到客户端的出带宽 | Mbps |
| `qce_lb_public_clientaccintraffic_sum` | ClientAccIntraffic | 客户端到 LB 的入流量（累计流量） | MB |
| `qce_lb_public_clientaccouttraffic_sum` | ClientAccOuttraffic | LB 到客户端的出流量 | MB |

## LB ↔ 后端 RS

| Prometheus 指标 | 文档英文名 | 含义 | 单位（文档） |
| --- | --- | --- | --- |
| `qce_lb_public_intraffic_max` | InTraffic | LB 到后端的入带宽 | Mbps |
| `qce_lb_public_outtraffic_max` | OutTraffic | 后端到 LB 的出带宽 | Mbps |
| `qce_lb_public_inpkg_max` | InPkg | LB 到后端的入包量 | 个/秒 |
| `qce_lb_public_outpkg_max` | OutPkg | 后端到 LB 的出包量 | 个/秒 |
| `qce_lb_public_connum_sum` | ConNum | LB 到后端的连接数 | 个 |
| `qce_lb_public_newconn_sum` | NewConn | LB 到后端的新建连接数 | 个/分钟（文档） |
| `qce_lb_public_newactiveconn_max` | NewActiveConn | 新建活跃连接相关（命名对应 NewActiveConn） | 个 |
| `qce_lb_public_accouttraffic_sum` | AccOuttraffic | LB 到后端的出流量 | MB |

## 丢包 / 限速 / 容量使用率

| Prometheus 指标 | 文档英文名 | 含义 | 单位（文档） |
| --- | --- | --- | --- |
| `qce_lb_public_droptotalconns_max` | DropTotalConns | 丢弃连接数（标准账户） | 个 |
| `qce_lb_public_indropbits_max` | InDropBits | 公网入方向丢弃带宽 | Byte（文档） |
| `qce_lb_public_outdropbits_max` | OutDropBits | 公网出方向丢弃带宽 | Byte |
| `qce_lb_public_indroppkts_max` | InDropPkts | 公网入方向丢弃包量 | 个/秒 |
| `qce_lb_public_outdroppkts_max` | OutDropPkts | 公网出方向丢弃包量 | 个/秒 |
| `qce_lb_public_intrafficvipratio_max` | IntrafficVipRatio | 入带宽使用率（VIP） | % |
| `qce_lb_public_outtrafficvipratio_max` | OuttrafficVipRatio | 出带宽使用率（VIP） | % |
| `qce_lb_public_concurconnvipratio_max` | ConcurConnVipRatio | 并发连接数使用率（VIP） | % |
| `qce_lb_public_newconnvipratio_max` | NewConnVipRatio | 新建连接数使用率（VIP） | % |

## 健康检查

| Prometheus 指标 | 文档英文名 | 含义 | 单位（文档） |
| --- | --- | --- | --- |
| `qce_lb_public_healthrscount_sum` | HealthRsCount | 健康检查正常后端数 | 个 |
| `qce_lb_public_unhealthrscount_sum` | UnhealthRsCount | 健康检查异常后端数 | 个 |
