---
name: trace-chain-report
description: "当用户给出 traceId、调用日志，或要求生成调用链报告、代码走读和分层 HTML 链路图时使用。先写事实卡再写报告，校验通过后才交付；禁止编造未取证的 RPC、耗时或根因。"
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

输入可以是调用日志、直接粘贴的 traceId，或已经落盘的 evidence index。同一行多个 traceId 拆开。描述优先用 traceId 前的中文名。

输出目录只有一种写法：`<分析根目录>/调用链路/统计图/<中文描述>-<短标识>/`。短标识用企业或 traceId 前几位消歧。每条 trace 四份文件：

- `fact-card.json`
- `调用链路分析.md`
- `调用链路线性图.html`
- `证据索引.md`

证据目录由调用方传入。不要写死仓库里的 `output/evidence/<issue>`，也不要发明 issue 编号。

批量时，协调者只解析列表和汇总状态；每个 worker 只写自己的目录。一条失败标 `partial`，其他继续。重跑先读该目录的事实卡和证据索引，只补缺口。分享链接必须等用户明确要求。

## 写作门禁

事实标记只有四档：`已观测`、`代码映射`、`推断`、`未取证`。网关总耗时减去已量化分段后，差额写 `未细分`，不记到某个方法上。时间戳空档不是方法耗时。

代码走读：只有 `code-search` 给出仓库、文件和符号时，才允许标 `代码映射`，并且只写对得上的步骤。没有命中时，第 6 节必须写「未取得精确源码」，只列日志里的类名和方法名。

脱敏：正文不写用户标识和密码。链路里出现的 Redis、MQ、copier，以及 ClickHouse、Pod、Node IP，必须写进对应卡片。没有日志或架构证据就不要补。完整 traceId 保留。

图：自包含分层 HTML，不引用外链，也不要再画横向 SVG 长条。版式是页头、纵向层级、层内卡片和层间箭头。每张卡片用中文写清这一跳做了什么，并带上接口路径或方法名。没有证据的层不要补组件。

字段、章节和事实卡结构见 `references/report-contract.md`。批量任务文本见 `references/multica-batch-prompt.md`。

## 校验

解析和校验只检查结构，不生成报告正文：

```bash
uv run --no-sync python .agents/skills/trace-chain-report/scripts/parse_call_log.py <调用日志.md>
uv run --no-sync python .agents/skills/trace-chain-report/scripts/validate_report.py <报告目录> --peer <另一条报告目录> --check-evidence
```

校验失败就改事实卡或正文，不能把未通过的报告当完成。
