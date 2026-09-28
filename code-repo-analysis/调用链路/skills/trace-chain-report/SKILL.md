---
name: trace-chain-report
description: "当用户给出 traceId、调用日志，或要求生成调用链报告、代码走读和泳道 HTML 链路图时使用。同一 traceId 被多个接口复用时，按描述末尾路由拆开，只追该路由。先写事实卡再写报告，校验通过后才交付；禁止编造未取证的 RPC、耗时或根因。"
---

# trace-chain-report

## 定位

把一批 trace 写成互相隔离的调用链报告。本技能负责编排和写作，不替代 `fx-ops` 的故障首跳：用户拿 traceId 问报错、超时或根因时，先由 `fx-ops` 归一化环境、租户和时间窗。只有用户要调用链报告，或主控已经交来证据时，才进入本技能。

报告正文只能来自该条 trace 的 `fact-card.json`。原始日志留在证据目录，不抄进正文。

## 模式

| 模式 | 何时使用 | 行为 |
| --- | --- | --- |
| `knowledge` | 已有证据索引，或只做知识梳理 | 只读已落盘证据。不默认新查 Pod、Prometheus 或资源建议 |
| `live` | 证据不够，且调用方明确要求补线上事实 | 按入口、应用日志、下游、存储、资源、源码的顺序委托取证 |

`live` 按需委托这些能力，不写死兄弟技能的脚本路径：`fx-ops-tracing`、`fx-ops-query`、`fx-ops-k8s-app`、`fx-ops-monitoring`、`fx-ops-resource-recommend`、`code-search`。查不到就标 `未取证`，不用另一条 trace 填空。

## 输入与输出

输入可以是调用日志、直接粘贴的 traceId，或已经落盘的 evidence index。同一行多个 traceId 拆开。描述优先用 traceId 前的中文名。描述末尾的路由是另一条任务的身份，不能被 traceId 去重丢掉。

先解析，再写报告。解析只抽出任务，不查日志：

```bash
uv run --no-sync python scripts/parse_call_log.py <调用日志.md>
```

在本技能目录执行。安装到 `.agents/skills/trace-chain-report` 时，把 `scripts/parse_call_log.py` 换成那个路径。每条任务用返回的 `output_dir`，不要沿用调用日志里抄错的结果目录。

输出目录是 `<分析根目录>/调用链路/` 加上解析结果里的 `output_dir`。有路由时短标识用路由末段，不用企业号或 traceId 前几位硬凑。每条任务四份文件：

- `fact-card.json`
- `调用链路分析.md`
- `调用链路线性图.html`
- `证据索引.md`

证据目录由调用方传入。不要写死仓库里的 `output/evidence/<issue>`，也不要发明 issue 编号。

批量时，协调者只解析列表和汇总状态；每个 worker 只写自己的目录。一条失败标 `partial`，其他继续。重跑先读该目录的事实卡和证据索引，只补缺口。分享链接必须等用户明确要求。


## 重复 traceId 按路由拆链

一次进页会打出多个接口。抓包时这些接口的 traceId 可能相同，调用日志也会把同一个 traceId 贴在多行。不能按 traceId 合并成一份报告，也不能用其中一行的耗时、Pod 或 SQL 填另一行。

路由取描述末尾，不取正文中间的字段名。末尾反引号或末尾路径都算，例如 `getCategoryAndRpt`、`WatermarkApi/getWatermark`、`stat/chartConfig/query`、`FHH/EM1HBISTAT/fs-bi-stat/stat/data/query`。`chartType`、`source=1` 这种夹在句子里的记号不是路由。

| 解析结果 | 怎么处理 |
| --- | --- |
| 同一 traceId，末尾路由不同 | 各写一份。任务身份是 `traceId + route` |
| 同一 traceId，描述相同且没有路由 | 合并为先出现的那条 |
| 同一 traceId，描述不同但没有末尾路由 | 无法拆开，只保留先出现的描述。解析结果的 `merged_without_route` 要写进汇总 |
| 路由是完整 `FHH/EM1H...` | `service_code` 取 `EM1H` 后面的服务码，当作 CEP `bizName` 候选 |

`live` 取证时，路由是主过滤条件，贴来的 traceId 只是时间锚和企业锚：

1. 用贴来的 traceId 查 `log_cep_dist`，只保留 `uri` 或 `uri2` 对上该路由的行。对不上的其他接口留在证据边界，写「同 traceId 的其他路由，未纳入」。
2. 一行都对不上，说明这个 traceId 属于同页的另一个接口。用它的 `ea` 和解析时间做窄窗，再按路由反查真正的 traceId。有完整路径时 `uri2` 等值；只有末段时用 `position(uri, '<route>') > 0`。CEP 必须带 `bizName` 候选和 `stamp`，禁止无 bizName 的宽窗 `uri LIKE`。`EM1HBISTAT` 先试 `BISTAT`，`EM1HBICRM` 先试 `BICRM`，`EM1HQIXINEXT` 先试 `QIXINEXT`；后缀路由没有服务码时，用同页已命中行的 `bizName`，对不上就换候选，不要猜一个扫数小时。
3. 反查到唯一行，事实卡 `trace_id` 改成该行的 traceId，`pasted_trace_id` 保留原值。反查到多条，标 `partial` 并列出候选，不选一条继续写。
4. 报告入口必须是这条路由。同 traceId 下的兄弟接口不是本请求的下游，除非这条路由的应用日志里真有对它的调用。

## 写作门禁

事实标记只有四档：`已观测`、`代码映射`、`推断`、`未取证`。网关总耗时减去已量化分段后，差额写 `未细分`，不记到某个方法上。时间戳空档不是方法耗时。

代码走读：只有 `code-search` 给出仓库、文件和符号时，才允许标 `代码映射`，并且只写对得上的步骤。没有命中时，第 6 节必须写「未取得精确源码」，只列日志里的类名和方法名。

脱敏：正文不写用户标识和密码。链路里出现的 Redis、MQ、copier，以及 ClickHouse、Pod、Node IP，必须写进对应卡片。没有日志或架构证据就不要补。完整 traceId 保留。

查库节点必须同时写数据库名和表名。Mongo 写数据库名和集合名。物理库名只来自本 span 的 SQL 日志、JDBC 地址或已核对的路由结果。源码里的数据源配置名、biz、租户不是物理库名，可以另写，但不能冒充数据库名。库名没取到就写 `数据库名未取证`，不能省略，也不能把别的请求或别的服务的库名抄过来。

MQ 的发送和消费节点必须同时写 MQ 名字、发送方、消费方。名字用 topic 或 queue 原文。发送方、消费方写服务和方法；消费方有消费组也要写。缺的一侧写 `未取证`，不能只写「发了 MQ」或只写一侧。

图：自包含泳道 HTML，不引用外链，也不要用纵向分层卡片或 SVG 代替。列从左到右是参与方，从上到下是调用顺序。每张卡片用中文写清这一跳做了什么，并带上接口路径或方法名。没有证据的参与方不要开列，但查表不能因为慢 SQL 为空就整列省略。版式只参照 `调用链路/统计图/新建统计图获取主题列表-01M39DP86/调用链路线性图.html`，不抄它的事实。

## 下钻到查表

服务方法不是终点。`sql_slow_dist` 为 0 只说明没有慢查询，不能当成没有查表，也不能因此不画数据层。

`live` 写报告前必须继续往下：

1. 从应用日志抽出叶子方法。日志里的 `dbFieldName`、`ORDER BY`、表别名一并记下。
2. 用 `code-search` 打开叶子方法，追到 Mapper、Repository 和 MyBatis XML 的 `FROM` 表，并核对它绑定的数据源。命中仓库、文件、符号后，每个实际查询做成 `layer=data` 节点，标记 `代码映射`。一次 SQL 连接多张表时仍是一张卡，每张表都写数据库名和表名，不要画成多次往返。卡片写中文查表动作、Mapper 方法、数据库名和表名，不贴完整 SQL。
3. 慢 SQL、RPC 和下游服务只作补充。慢 SQL 为空时，仍要画源码里对上的查表。慢 SQL 里的 `db` 只属于打出它的那一次查询。
4. 源码和日志都查过仍没有表名时，数据层仍留一张卡，标记 `未取证`，写明查过的方法，并写 `数据库名未取证`、`表名未取证`。禁止不画数据层就交付。
5. 日志或源码出现 MQ 发送、消费时，同样下钻到 topic 或 queue、发送方、消费方。三个字段缺一就写 `未取证`，不能因为只有一侧 span 就省略另一侧。

字段、章节和事实卡结构见 `references/report-contract.md`。批量任务文本见 `references/multica-batch-prompt.md`。

## 校验

解析和校验只检查结构，不生成报告正文：

```bash
uv run --no-sync python scripts/parse_call_log.py <调用日志.md>
uv run --no-sync python scripts/validate_report.py <报告目录> --peer <另一条报告目录> --check-evidence
```

校验失败就改事实卡或正文，不能把未通过的报告当完成。
