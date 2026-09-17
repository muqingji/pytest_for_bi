# 同事接入 QA-Agent 配置指南

给要在本机跑 QA-Agent 的同事用。设计原理看 [README.md](../README.md) 和
[QA_AGENT_DESIGN.md](../../QA_AGENT_DESIGN.md)。本文件只回答：本机怎么装、哪些
ID 必须改、一轮八卡怎么挂上、定时器怎么装、G01 怎么批、常见故障怎么查。

不要照抄别人电脑上的 `generated/` 路径、Project ID 或 LaunchAgent plist。那些是
本机运行态，仓库不入库。

## 1. 先选你要跑哪条链

| 目标 | 需要 Multica / 定时器 | 怎么验证 |
| --- | --- | --- |
| 只跑离线质量门禁和本地试点 | 否 | `make install` 后 `make -C qa-agents test` / `make -C qa-agents pilot` |
| 接入 Multica 八卡（C1–C8）真实工作流 | 是 | 本机 `generated/<run>/` + `active-workflows.json` + LaunchAgent |

同事日常要用的是第二条。第一条可以先用来确认 Python 环境没问题。

`--approve-g01` / `--approve-g02` 只允许本地开发验证，生产审批必须走 Multica 人工
Gate，不能用 Makefile 开关代替。

## 2. 本机前置

- macOS（定时器走 `~/Library/LaunchAgents`；Linux/Windows 需自行改成 cron/systemd）
- Python 3.10+
- Git 仓库 `pytest_for_bi`
- Multica CLI 在 PATH 中。常见路径：`/usr/local/bin/multica` 或 `/opt/homebrew/bin/multica`。向工作区维护者要安装包，不要猜下载地址。
- 已登录 Multica，并被加入共享 Workspace「服务端需求自动化测试」
- 可选：`uv`（用来重建 `qa-agents/.venv`）

硬约束：

- 不要改 `fs-qa-knowledge` 或任何业务仓（`fs-bi`、`fbi` 等）。策略是只读取证。
- 不要把 `generated/`、`.venv`、`config/environment.*.local.json` 提交进 Git。
- 不要把 Case Provider 当生产能力。当前钉死的远端 commit 没有
  `qa-agent-provider.json`，也没有无副作用 `artifact_only` 入口。

## 3. 安装 Python 环境

仓库里有两套 venv，用途不同，都要有。

### 3.1 仓库根目录 `.venv`（离线测试 / Makefile）

`qa-agents/Makefile` 默认用 `../.venv/bin/python`。

```bash
cd /path/to/pytest_for_bi
python3 -m venv .venv
source .venv/bin/activate
make install
make -C qa-agents test
```

### 3.2 `qa-agents/.venv`（八卡定时器）

LaunchAgent 写死用 `qa-agents/.venv/bin/python`，并通过 `PYTHONPATH=qa-agents/src`
加载代码，不依赖 `pip install -e`。

```bash
cd /path/to/pytest_for_bi
python3 -m venv qa-agents/.venv
qa-agents/.venv/bin/python -m pip install -e qa-agents
```

若本机有 `uv`：

```bash
cd qa-agents
uv sync
```

确认：

```bash
test -x qa-agents/.venv/bin/python
PYTHONPATH=qa-agents/src qa-agents/.venv/bin/python -c "import qa_agents; print('ok')"
command -v multica && multica version
```

112 环境执行（N08 及以后）另外需要 `config/environment.112.local.json`（权限
`0600`，Git 忽略）。只跑 C1–C4 设计链可以先不配。

## 4. 配置分三层，不要混

| 层 | 路径 | 谁改 | 说明 |
| --- | --- | --- | --- |
| 共享模板 | `qa-agents/multica/workflow-center-config.json` | 工作区维护者 | Workspace / 默认 Project / Agent 映射。不要把你的本机 live ID 写回去。 |
| 共享策略 | `qa-agents/policies/g01-*.json` 等 | 工作区维护者 | G01 审批白名单、风险策略。同事要批 G01，必须先把自己加进白名单。 |
| 远端身份清单 | `qa-agents/multica/workspace-manifest.json` | 工作区维护者 | Workspace、Squad、Agent、Runtime 的远端 ID。编排器按它绑定，不要手改 Runtime。 |
| 本机运行态 | `generated/<run>/`、`generated/active-workflows.json` | 每位同事自己的电脑 | Git 忽略。每轮需求一份。 |

共享 Workspace 的固定字段（可复用，不要发明新的）：

| 字段 | 当前共享值 | 用途 |
| --- | --- | --- |
| `workspace_id` | `457d700f-6c27-4a59-871d-c2c56bca9f46` | Workspace「服务端需求自动化测试」，Issue 前缀 `QAA` |
| `node_agents` | 见模板 `workflow-center-config.json` | A02/A03/A05/A06/A08/… 的远端 Agent ID |
| `workflow_lead_id` | `e7354c2e-c418-4979-8294-5ca3b5707afb` | Squad 组长 |
| G01 试点审批人 | actor `muqj11262` / member `c2c6b9c6-4fb9-4439-a4a5-de4e93784c54` | **不是你的 ID 就批不了** |

你必须从自己的 live 卡片抄、不能从模板盲拷的字段：

| 字段 | 模板里的值（不要当 live） | 怎么拿到 |
| --- | --- | --- |
| `workflow_project_id` | `84580297-a0ca-4cce-9db9-59cade66f83c` | C1–C8 所在需求项目。打开任意一张阶段卡看 `project_id` |
| `internal_project_id` / `run_project_id` | `1b6d44c3-ea4b-4d9c-b86d-9074802fb604` | Parent / Run / A0x 内部执行项目 |
| `human_owner_member_id` | 无默认 | 你的 Multica member UUID |
| `a22_bug_finder_root` | 维护者本机绝对路径 | 改成你机器上的 bug-finder 路径，或先关掉 `a22_bug_finder_integrity_enabled` |

G01 Adapter 的 `multica.project_id`（`c2c84f1f-20af-456d-9eca-c9fbbd253840`）是
内部执行项目默认值。阶段卡可能在另一个 Project 上。绑定以**本轮 spec 里的 G01
metadata** 为准，不要假设「Adapter 默认 Project = 我这轮 C2 所在 Project」。

别人机器上的 live 例子（只说明「模板 ≠ live」，不要复制）：

- 模板 `workflow_project_id` ≠ 20260909 重跑的 `9484c7ab-40fe-4990-bb37-eca327b5bae5`
- 模板 `internal_project_id` ≠ 20260909 重跑的 `b100a330-ab2e-4092-ad57-0f674a7b8a91`

## 5. 同事要批 G01，先加白名单

当前 `qa-agents/policies/g01-multica-policy.json` 只允许试点 QA Owner。状态改成
`done` 不算批准；评论人如果不在白名单，同步器会忽略。

需要工作区维护者把你的账号加进：

1. `qa-agents/policies/g01-multica-policy.json`
   - `allowed_actor_ids`
   - `allowed_multica_member_ids`
   - `multica.assignee_member_id`（若你是这轮审核人）
2. `qa-agents/multica/workspace-manifest.json` 的 `gate_policies.G01`（以及 G02/G03，若你也要签）

查自己的 member ID：

```bash
multica auth whoami --output json
# 或从已有 Issue 的 assignee 字段抄 UUID
```

没有加白名单之前，不要指望评论能推进 C2。

## 6. 创建一轮本机运行目录

`generated/` 整棵树都是 Git 忽略的。每一轮需求独占一个目录。

推荐布局：

```text
generated/<run>/
  workflow-config.json
  current/workflow-center-spec.json
  sync-auto/
  artifacts-auto/
generated/active-workflows.json
```

### 6.1 已有 Multica 八卡（最常见）

1. 复制模板：

```bash
mkdir -p generated/<run>/current
cp qa-agents/multica/workflow-center-config.json generated/<run>/workflow-config.json
```

2. 编辑 `generated/<run>/workflow-config.json`，至少改这些：

```json
{
  "schema_version": "multica-workflow-center/1.0",
  "workspace_id": "<workspace_id>",
  "workflow_project_id": "<C1-C8 所在项目>",
  "internal_project_id": "<内部执行项目>",
  "run_project_id": "<通常与 internal_project_id 相同>",
  "g01_policy": "qa-agents/policies/g01-review-policy.json",
  "g01_adapter_policy": "qa-agents/policies/g01-multica-policy.json",
  "node_agents": { "...从模板保留..." },
  "node_input_files": {},
  "n24_workflow_input": "qa-agents/eval/workflows/<your-input>/input/workflow-input.json",
  "n24_source_snapshot": "qa-agents/eval/workflows/<your-input>/input/source-snapshot.json",
  "n24_risk_policy": "qa-agents/policies/risk-policy.json"
}
```

缺 `n24_*` 时 N24 会空转，C2 批完也不会真正出风险策略。

`prior_test_rules_paths` 可选。G01 简洁评论里的 `test_rules` 经常是一段自然语言，
A08 需要结构化规则。没有结构化表时，不要让 A08 猜，显式指到一份
`g01-review-decision.json`。

3. 准备 `generated/<run>/current/workflow-center-spec.json`，schema 必须是
`requirement-workflow/1.0`，并包含本轮 `workflow_id`、`workflow_run_id`、C1–C8
以及 parent/run 绑定。已有运行可从维护者处拷一份 spec 再改 ID；新需求用下一节的
`init-autopilot`。

### 6.2 新需求，还没有父卡

准备 `autopilot-request/1.0`：

```json
{
  "schema_version": "autopilot-request/1.0",
  "workflow_id": "REQ-<STABLE-ID>",
  "requirement_id": "REQ-<STABLE-ID>",
  "workflow_run_id": "<run-id>",
  "workflow_definition_version": "1.0",
  "source_snapshot_id": "<snapshot-id>",
  "title": "<需求标题>",
  "human_owner_member_id": "<你的 Multica member UUID>"
}
```

`workflow_id` 必须等于稳定 `requirement_id`。然后：

```bash
PYTHONPATH=qa-agents/src .venv/bin/python -m qa_agents init-autopilot \
  --request /path/to/autopilot-request.json \
  --config generated/<run>/workflow-config.json \
  --registry generated/<run>/autopilot-registry \
  --output generated/<run>
```

`make -C qa-agents init-autopilot` 也可以，但要自己设 `AUTOPILOT_REQUEST`。

## 7. 注册到监听器

定时器只扫 `generated/active-workflows.json`。没注册 = 不会调度。

```bash
PYTHONPATH=qa-agents/src qa-agents/.venv/bin/python \
  qa-agents/scripts/workflow_monitor.py \
  --registry generated/active-workflows.json \
  register \
  --config generated/<run>/workflow-config.json \
  --artifact-root generated/<run> \
  --spec generated/<run>/current/workflow-center-spec.json
```

扫描时如果目录里已经同时有 `workflow-config.json` 和
`current/workflow-center-spec.json`，`discover_workflows()` 也会自动登记。缺任一
文件都会被跳过，日志类似 `no workflow-config.json`。

注册成功后，registry 里应能看到你的 `workflow_run_id`，`status` 为可运行态，而不是
`suspended_accuracy_violation`。

## 8. 安装本机定时器

macOS：

```bash
bash qa-agents/scripts/install-sync-timer.sh
```

安装结果：

| 项 | 值 |
| --- | --- |
| 扫描间隔 | **30 秒**（`com.qa.sync-eight-card`） |
| Watchdog | **60 秒**，心跳超过 90 秒会 kickstart |
| 命令 | `workflow_monitor.py --registry generated/active-workflows.json scan` |
| 日志 | `/tmp/qa-sync-eight-card.out.log`、`.err.log` |
| Watchdog 日志 | `/tmp/qa-sync-eight-card-watchdog.out.log` |

脚本会检查 `multica` 是否在 PATH 里。launchd 的 PATH 只有
`/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin`，CLI 不在这些路径时每次都会崩。

卸载：

```bash
launchctl bootout gui/$(id -u)/com.qa.sync-eight-card
launchctl bootout gui/$(id -u)/com.qa.sync-eight-card-watchdog
```

手工立刻跑一轮（不等 30 秒）：

```bash
PYTHONPATH=qa-agents/src qa-agents/.venv/bin/python -u \
  qa-agents/scripts/sync_eight_card_progress.py \
  --config generated/<run>/workflow-config.json \
  --artifact-root generated/<run> \
  --spec generated/<run>/current/workflow-center-spec.json \
  --sync-output generated/<run>/sync-auto \
  --apply
```

或：

```bash
PYTHONPATH=qa-agents/src qa-agents/.venv/bin/python \
  qa-agents/scripts/workflow_monitor.py \
  --registry generated/active-workflows.json \
  scan
```

旧版 plist 曾指向已删除的 `--config generated/.../workflow-config.json`，每 120
秒 ENOENT。如果你机器上还是这个，必须重装 `install-sync-timer.sh`。

## 9. G01 审核协议（同事必读）

C2 是范围确认。同步器**不把 Issue 状态当审批**。只把卡片拖成 `done` 会被忽略，
必要时打回 `in_review`。

有效审批必须是白名单成员的人工评论，协议 `g01-comment-table/1.0`。推荐写法：

```text
A02:AMB-001：确认展示任意一个
A03:product-copy-result-filter：确认使用端无关文案
```

也可以逐项回复卡片正文里的建议原文。系统如果回了「缺项」清单，下一条评论请直接
引用剩余项的建议拷贝。

下面这些**不是**审批：

- 只改状态，不写评论
- 系统评论：`G01 审核提交未通过校验`、`G01 审核补充说明`、`待 QA Owner 确认`
- 非白名单成员的评论
- Agent 代批（`agent_approval_allowed=false`）

全部有效项确认后，同步器才会写 G01 decision，然后跑 N24，再派 A08。C2 变 `done`
之后下一张应是 C3（测试设计），不是再把 C2 打开。

简洁 G01 的 `test_rules` 经常是字符串。A08 要结构化规则时，在
`workflow-config.json` 里设 `prior_test_rules_paths`，或在审核卡里提供结构化表。

## 10. 首次接入检查清单

1. `make -C qa-agents test` 通过。
2. `command -v multica` 成功，且 `multica auth whoami` 是你自己。
3. 你的 member UUID 已写入 G01 白名单（若你要批 C2）。
4. `generated/<run>/workflow-config.json` 的 Project ID 来自**你的 live 卡片**，不是模板。
5. 同目录有 `current/workflow-center-spec.json`，schema 为 `requirement-workflow/1.0`。
6. `n24_workflow_input` / `n24_source_snapshot` / `n24_risk_policy` 都填了。
7. `workflow_monitor.py register` 成功，或 `scan` 的 `discovery.registered` 含本轮。
8. `bash qa-agents/scripts/install-sync-timer.sh` 后，`/tmp/qa-sync-eight-card.out.log`
   在 30 秒内有新行，且没有 ENOENT / `multica: command not found`。
9. 打开 C2，按第 9 节写评论，不要只改状态。

## 11. 排障

| 现象 | 先查 |
| --- | --- |
| 评论了 C2，下一项不动 | 1) 定时器是否活着 2) 本轮是否在 registry 3) 评论人是否在 G01 白名单 4) 评论是否带 `issue_id` 或建议原文 5) 是否只改了 `done` |
| 日志 `No such file or directory` / ENOENT `workflow-config.json` | 旧 LaunchAgent 仍指向已删目录。重装 `install-sync-timer.sh` |
| `no workflow-config.json` / 扫描跳过本轮 | 缺 `generated/<run>/workflow-config.json` 或 `current/workflow-center-spec.json` |
| N24 被跳过 | 缺 `n24_workflow_input` / `n24_source_snapshot` / `n24_risk_policy` |
| A08 报没有 structured `test_rules` | 配 `prior_test_rules_paths`，或在 G01 决策里给结构化表 |
| `Workflow sync returned another workflow run` / `suspended_accuracy_violation` | spec 的 `workflow_run_id` 和 registry 不一致，或扫到了别人的运行。先停掉冲突目录，再 `resume` |
| launchd 每次失败 | `multica` 不在 launchd PATH。把 CLI 放到 `/usr/local/bin` 或 `/opt/homebrew/bin` 后重装定时器 |
| G01 批了但绑定失败 | C2 所在 Project ≠ Adapter 默认 `project_id`。确认 spec 里本轮 G01 metadata 指向这张卡 |

看现场：

```bash
tail -n 80 /tmp/qa-sync-eight-card.out.log
tail -n 80 /tmp/qa-sync-eight-card.err.log
python3 -m json.tool generated/active-workflows.json | less
launchctl print gui/$(id -u)/com.qa.sync-eight-card | rg "state|program|interval"
```

恢复被挂起的运行（确认不是串了别人的 run 之后）：

```bash
PYTHONPATH=qa-agents/src qa-agents/.venv/bin/python \
  qa-agents/scripts/workflow_monitor.py \
  --registry generated/active-workflows.json \
  resume --run-id <workflow_run_id> \
  --acknowledge-accuracy-violation
```

## 12. 不要做的事

- 不要编辑 `fs-qa-knowledge`、业务仓、或把 Provider Case 当生产输入。
- 不要 `git add generated/`。
- 不要把别人的 `workflow_project_id` / `internal_project_id` 拷进自己的运行。
- 不要用本地 `--approve-g01` 代替 Multica 评论。
- 不要在沙箱或无 GUI 权限的环境里指望自动写入 `~/Library/LaunchAgents`；本机自己跑
  `install-sync-timer.sh`。

相关文档：

- 设计与试点状态：[README.md](../README.md)
- 实现进度：[IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md)
- Case Provider 边界：[FS_QA_KNOWLEDGE_INTEGRATION.md](FS_QA_KNOWLEDGE_INTEGRATION.md)
