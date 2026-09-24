---
name: fx-ops-k8s-app
description: 应用管理与发布命令行接入（fs-k8s-cli 接入发布系统 fs-k8s-app-manager）。只读操作无需确认：查服务运行镜像版本、Pod 状态、发布流程/部署模块、集群与运行环境、服务运行日志/启动日志/Pod 标准输出/落盘日志文件。变更操作必须先只读 plan（pipeline 状态/deploy-params/pod list）并落回滚点，再做五要素确认，未确认不得执行，禁止管道喂 y：镜像构建、应用发布、滚动重启、回滚（记录当前镜像后 deploy 上一版本，无独立回滚命令）、摘除/删除 Pod、Pod 内 exec（含非交互 --command）、上传日志文件、创建 Git Tag、取消构建/发布任务。环境显式 --profile：firstshare=测试/112，foneshare=生产/线上。
---

# fx-ops-k8s-app — 应用管理与发布命令行接入

两种模式：**read（默认）** 与 **change**。是否走变更门禁，按「这条命令会不会改变远端 / Pod / 本地状态」分类，不以五个动词白名单为准。命令字面以 `fs-k8s-cli skill show` 为准。

## 安装 fs-k8s-cli

当前本仓已验证版本：`26.07.30`。先检查：

```bash
fs-k8s-cli --version
```

命令不存在，或版本与已验证版本不一致时再安装。上游安装器是**无版本 URL、无 checksum、不支持版本参数**，因此**无法校验完整性**，不要把管道安装当成已核验交付。`curl | bash` 不再是唯一示例。

### 推荐：先下载再执行

```bash
# macOS / Linux — download then execute
curl -fsSL -o /tmp/fs-k8s-cli-install.sh \
  https://wuzh-public.oss-cn-beijing.aliyuncs.com/fs-k8s-cli/install.sh
# 上游无 checksum，无法核验；阅读脚本后再执行
bash /tmp/fs-k8s-cli-install.sh
fs-k8s-cli --version   # 应对齐 26.07.30
```

```powershell
# Windows PowerShell — download then execute
Invoke-WebRequest -Uri https://wuzh-public.oss-cn-beijing.aliyuncs.com/fs-k8s-cli/install.ps1 -OutFile "$env:TEMP\fs-k8s-cli-install.ps1"
# 上游无 checksum，无法核验；阅读脚本后再执行
& "$env:TEMP\fs-k8s-cli-install.ps1"
fs-k8s-cli --version
```

### 不推荐：管道直接执行

```bash
# macOS / Linux（无法中途核验脚本）
curl -fsSL https://wuzh-public.oss-cn-beijing.aliyuncs.com/fs-k8s-cli/install.sh | bash
```

```powershell
# Windows PowerShell（无法中途核验脚本）
irm https://wuzh-public.oss-cn-beijing.aliyuncs.com/fs-k8s-cli/install.ps1 | iex
```

### 上游依赖

在上游提供下列能力之前，本仓不能 pin 版本化安装包，也不能声称安装过程可校验：

1. 带版本号的安装器或 artifact（例如 `install-26.07.30.sh` 或版本化二进制）
2. checksum 清单（SHA-256）
3. 安装器支持版本参数

安装后只核对 `fs-k8s-cli --version` 是否为已验证版本，并明确告知用户完整性无法校验。分类表按 `26.07.30` 的 `skill show` 维护；CLI 升级后先重新执行 `skill show` 再更新本表。

## 命令信源：`fs-k8s-cli skill show`

本文档不重复 CLI 的命令、参数和工作流细节。触发后先执行：

```bash
fs-k8s-cli skill show
```

把输出当作本次任务的命令字面依据。本文档只补充本仓库必须遵守的规则：环境 profile、read / change 分类、变更门禁。

当前 CLI **没有 dry-run 参数**。plan 用只读命令解析当前镜像 / 目标镜像 / cluster / namespace / 受影响 Pod，展示后再等确认。

**禁止**用 `echo y | fs-k8s-cli ...`（或等价管道）绕过 CLI 自带确认，也禁止在用户未确认时向 CLI 的 `[y/N]` 喂 `y`。

## 模式：read（默认）vs change

- 用户只说「查一下 / 看看 / 日志 / 版本 / 状态 / 发布记录」→ **read**，查完直接给结果，不走变更门禁。
- 用户要「发布 / 构建 / 重启 / 回滚 / 删 Pod / 摘除 / exec / 上传 / 打 tag / 取消任务」→ **change**，先走变更门禁；未确认不得执行。
- 用户说「发布 / 重启」但**没给环境或应用名**：先问环境和应用名，禁止带默认 profile 进入 change。

### 分类表（按是否改变远端 / Pod / 本地状态）

维护依据：已验证 CLI `26.07.30` 的 `skill show`。判定标准不是动词白名单，而是「会不会改变远端发布系统、集群、Pod、Git 仓库或本机状态」。`module build-params` / `module deploy-params` 只是查询参数和可用镜像，属于 read。

| 命令 | 改变远端/Pod | 改变本地 | 模式 |
| --- | --- | --- | --- |
| `pipeline list` / `pipeline running` | 否 | 否 | read |
| `module list-by-app` / `list-by-pipeline` | 否 | 否 | read |
| `module build-params` / `deploy-params` | 否 | 否 | read（查构建参数 / 可用镜像） |
| `gitlab refs` | 否 | 否 | read |
| `app list` / `app pod list` | 否 | 否 | read |
| `app pod logs`；`logfile list` / `tail` / `grep` | 否 | 否 | read |
| `app pod logfile download` | 否 | 是（写 `--dest`） | read（本机落盘；覆盖已有文件前确认 dest） |
| `cluster list` / `detail` / `list-namespaces` | 否 | 否 | read |
| `parent-pom list` | 否 | 否 | read |
| `ops pipeline/app/autoscaler/cronscaler list` | 否 | 否 | read |
| `job status` / `job logs` | 否 | 否 | read |
| `config get` / `profile list` | 否 | 否 | read |
| `skill show` | 否 | 否 | read |
| `config set` / `profile use` / `profile remove` | 否 | 是（本机 CLI 配置） | 本机配置；不要静默改写已有 profile |
| `build` | 是（构建任务 / 镜像） | 否 | change |
| `deploy` | 是（发布运行镜像） | 否 | change |
| 回滚（无独立 `rollback` 动词） | 是 | 否 | change：先记录当前镜像，再用 `deploy` 发回上一镜像 |
| `app restart` | 是（滚动重启） | 否 | change |
| `app pod deregister` | 是（从负载摘除） | 否 | change |
| `app pod delete` | 是（删除 Pod） | 否 | change |
| `app pod logfile upload` | 是（写 Pod 文件系统） | 否 | change |
| `app pod exec`（`-ti` 交互 **与** 非交互 `--command`） | 是（任意 shell，风险最高） | 可能 | change（两种都进门禁；本仓严于上游「非交互无需确认」） |
| `gitlab create-tag` | 是（Git 仓库打 tag） | 否 | change |
| `job cancel` | 是（取消构建 / 发布任务） | 否 | change |

表中未列出的新命令：先看 `skill show` / `--help` 判断会不会改状态；会改就当 change。

当前 CLI **没有** `rollback` 动词，不要发明 `--rollback` 或同名子命令。回滚 = 变更前记下当前镜像，再 `deploy` 上一镜像。

## 环境 profile

`fx-ops` 与 `fs-k8s-cli` 各自维护一套 profile，互不感知，只是环境命名恰好一致。每次调用都显式传 `--profile <name>`，不要依赖 CLI「当前激活 profile」。

| profile | 用户可能的叫法 | 确认提示必须写出的对照 |
| --- | --- | --- |
| `firstshare` | 测试环境、112 环境、112 测试环境、线下环境、firstshare 环境 | `firstshare` = 测试/112 |
| `foneshare` | 生产环境、线上环境、foneshare 环境 | `foneshare` = 生产/线上 |

诊断和操作如果落在不同环境，会出现「在 foneshare 排查，却操作了 firstshare」这类错配。生产 / 测试叫法与 profile 不一致时必须阻断并重问，禁止混用。

### read：环境解析（HND 可直接用 env）

1. **本次任务由 fx-ops 主控派发**（收到 HND 分发上下文）：直接用 `anchor_context.env` 作为 `--profile`，不要重新询问或推断。
2. **没有派发上下文，但用户已明确说了环境**：按对照表映射到 profile 名。
3. **以上都没有**：先看 `FX_OPS_PROFILE`（高于配置文件里的 current profile）；没设置再跑 `fx-ops config info`。仍不确定就问用户，不要猜。

### change：环境解析（HND 不豁免确认）

**HND 不跳过确认。** 上节「直接用 `anchor_context.env`、不要重问」**只适用于 read**。change 即使 HND 已给 env，也必须做五要素复述，确认提示里写出 `firstshare`=测试/112、`foneshare`=生产/线上。

用户说「发布 / 重启」但未给环境或应用名：停在询问，禁止带默认 profile 进入 change。

本机若还没为该环境配置过 fs-k8s-cli profile，按 `skill show` 的配置方式创建，profile 名用同一个环境名（`firstshare` / `foneshare`）。Agent 用非交互 `config set`，不要用会阻塞的 `config onboard`。

## 变更门禁（AI 调度层）

确认逻辑写在本文档，由 Agent 执行。禁止用 Python if/else 脚本做 gate 或编排。所有命令仍走 `fs-k8s-cli`。

### 1. 只读 plan（代替 dry-run）

执行任何 change 前，先用只读命令解析并展示：

- 当前运行镜像 / 版本：`pipeline running`
- 目标镜像（deploy / 回滚）：`module deploy-params`
- cluster / namespace：`pipeline list -o json`
- 受影响 Pod：`app pod list`

没有这组事实不得执行 change。CLI 无 dry-run，这组只读解析就是 plan。

### 2. 五要素复述

确认提示必须同时给出：

| 要素 | 含义 |
| --- | --- |
| `--profile` | 必须附对照：`firstshare`=测试/112；`foneshare`=生产/线上 |
| 集群 | cluster |
| 应用 | app 名；Pod 级动作还要 Pod 名 |
| 动作 | 即将执行的 CLI 命令与关键参数 |
| 影响面 | 哪些 Pod / 模块 / 流量 / Git 仓库会变 |

```text
即将变更（未执行）：
- profile: foneshare（生产/线上）
- 集群: tke70-k8s1
- 应用: foo-service
- 动作: app restart（滚动重启，不换镜像）
- 影响面: namespace=foneshare 下该应用全部 Pod
当前镜像: <pipeline running 记录>
请明确回复确认后才执行。未确认则 status: pending_approval, executed: false。
```

### 3. 未确认

用户未明确确认（沉默、含糊、「先看看」、只问影响）：

- **不得**执行 change 命令
- **不得**用 `echo y |` 向 CLI 喂确认
- 返回 `status: pending_approval, executed: false`

### 4. 回滚点（变更前）

执行前把当前版本 / 镜像落到 `output/evidence/<case>/`（例如 `k8s-prechange.json`），来源优先 `pipeline running`。没有回滚点不得 `deploy` / `restart` / 回滚式 `deploy`。

回滚：记录当前镜像后，用 `deploy` 把上一镜像重新发布。

### 5. 审计（变更后）

动作、参数、退出码、验证查询（`pipeline running` / `app pod list`）落到 `output/evidence/<case>/`。

### 6. `app pod exec` 特别条款

交互 (`-ti`) 与非交互 (`--command`) **都必须**进变更门禁。上游 CLI 写明非交互无需确认；本仓更严：任意 shell 都可能改变 Pod 状态。Agent 环境不要开交互 `-ti`。
