---
name: fx-ops
description: traceId 或 reqId（含弹窗错误代码 1-xxxx）必用本 skill 首跳；≥2 条 resolved traceId 先做 CEP 分类再 1:1 瘦身派发。用户粘贴 NCRM CEP/top64 类弹窗：「系统出现异常，请稍后重试或保存截图并反馈给系统管理员」「系统服务繁忙，请联系纷享客服或稍后重试」、错误代码与服务 SFA/UDOBJ/FMCG/MFG、s311030117；先采集再分诊域 skill。亦含 NPE/OOM/重启、响应慢/接口慢/调用超时、失败、报错截图、根因排查、发布/改配后异常、脏数据/字段缺失、Dubbo/RPC/熔断、Grafana 链接与故障并存、联系值班 oncall；effort auto/low/medium/high 分档。本文件只是 Multica 导入桩，执行前必须读取本机完整 skill。
---

# fx-ops — Multica 导入桩

这个目录只为通过 Multica 本地 skill 导入上限。上限是最多 256 个文件、单文件 1MB、整包 8MB。完整 `fx-ops` 有 588 个文件，不能整包导入，也不要再复制 `scripts/`、`references/`、`evals/` 进来。

完整 skill 与全部脚本只在本机这一份：

`/Users/liushanshan/code/bug-finder/.agents/skills/fx-ops`

## 执行前硬规则

1. 收到 traceId、reqId、CEP 错误码或故障排查请求后，先完整阅读：
   `/Users/liushanshan/code/bug-finder/.agents/skills/fx-ops/SKILL.md`
2. 按该文件继续阅读它点名的 `references/`。不要用本导入桩代替那些规则。
3. 所有 `uv run` 和 `fx-ops` 命令的工作目录必须是上面的完整 skill 目录。禁止在本导入目录、任务临时目录或 Multica 注入副本里执行 `scripts/fx_ops_cli.py`。
4. 证据目录使用绝对路径，放在 bug-finder 仓库的 `output/evidence/<YYYYMMDD-Issue>/`。禁止编造未取证的 RPC、耗时、根因或代码位置。
5. 如果完整 skill 路径不存在或不可读，立刻停止并报告该路径。不要凭本文件猜命令、猜 playbook 或编报告。

## 首跳

- 已有 traceId 或 reqId：只走完整 `fx-ops`。先采集，再按完整 skill 分诊域 skill。
- 1 条 trace：在完整 skill 目录执行 `fast_rca`，读 stdout 的 `auto_decision` 后再决定是否升档。
- 2 条及以上 resolved traceId：先读完整 skill 的 `references/batch-trace-split.md`，做 CEP 分类后再 1:1 瘦身派发。
- 调用链 HTML、节点中文说明、Redis、MQ、copier、IP 的展示，在取证完成后按已导入的 `trace-chain-report` 生成。`fx-ops` 负责取证，不在本桩里拼 HTML。

命令形态以完整 skill 为准。在完整 skill 目录执行，`<dir>` 必须是绝对路径：

```bash
uv run --no-sync python scripts/fx_ops_cli.py run fast_rca -- \
  --trace-id '<traceId>' \
  --at '<YYYY-MM-DD HH:MM:SS>' \
  --evidence-dir '<dir>' \
  --profile foneshare \
  --json
```

参数不确定时，仍在完整 skill 目录执行：

```bash
uv run --no-sync python scripts/fx_ops_cli.py help fast_rca
```
