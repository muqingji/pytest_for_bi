# 智能提醒助手

这是“AI 每日学习任务智能提醒”面试题的独立交付目录。

当前状态：FR-001 提醒资格判断已完成本地单测、SQLite 迁移、构建和 Mock 联调；后续 P0 切片仍未实现。

## 目录说明

| 路径 | 内容 | 状态 |
| --- | --- | --- |
| 智能提醒助手PRD(9稿).md | 根据产品方案重新生成的 PRD | 已建立 |
| 业务诉求原文.md | 业务背景、现状数据、用户画像、业务目标和需求概要 | 已完成，作为需求输入源 |
| 需求拆解/需求分析/需求分析与评审视角.md | 题目事实、评审视角和指标分析 | 已完成 |
| 需求拆解/产品方案/产品方案.md | 完整产品分析、候选需求和取舍依据 | 已完成，持续评审 |
| 需求拆解/产品方案/智能提醒助手产品方案5稿.md | 从产品方案提炼出的评审汇总和 MVP 候选 | 已建立，待冻结 |
| 需求拆解/全流程实施步骤.md | 从需求到提交的实施顺序 | 已完成 |
| 需求拆解/验收标准/验收标准.md | Given/When/Then 验收场景 | 已建立 |
| 技术方案/技术方案.md | 架构、模型、决策引擎和工程约束 | 已确认本地交付边界 |
| 测试方案/测试方案.md | Demo 流程、测试分层和验证场景 | 已建立，待编码执行 |
| 测试方案/数据构造/数据构造说明.md | 测试用户、任务、行为和边界数据 | 已建立，待编码落地 |
| 交付物与留档/交付物与过程留档规划.md | 各阶段需要留档的内容 | 已完成 |
| AI_USAGE.md | AI 协作、人工决策和验证记录 | 持续更新 |
| Makefile | 本地开发入口（build / run / test / smoke / debug） | 已建立 |
| scripts/go-env.sh | 接入仓库内本地 Go 工具链 | 已建立 |
| docs/implementation/本地Go环境与调试.md | 工具链位置、运行命令、IDE 调试配置与故障排查 | 已建立 |
| tests/ | 自动化测试 | 按 Go 包分布，FR-001 已建立 |
| demo-data/ | 演示用户、任务、行为和设置数据 | FR-001 被动型场景已提供；后续切片继续补充 |
| cmd/、internal/ | 项目源代码 | FR-001 已建立 |
| migrations/ | 版本化数据库迁移 | FR-001 迁移内嵌于 `internal/adapter/storage/migrations/` |
| docs/test-report.md | 测试结果和质量准出记录 | FR-001 已更新 |

## 目标交付结构

编码完成后，建议目录达到以下结构：

~~~text
智能提醒助手/
├── README.md
├── 智能提醒助手PRD(9稿).md
├── AI_USAGE.md
├── go.mod 或 package.json
├── src/ 或 internal/
├── tests/
├── demo-data/
├── docs/
│   └── test-report.md
├── 需求拆解/
├── 技术方案/
├── 交付物与留档/
└── 业务诉求原文.md
~~~

## 当前运行方式

需要 Go 1.22+。本机工具链安装在仓库根目录 `.cache/` 内（不写系统目录、无需 sudo），`Makefile` 会自动注入环境；直接用 `go`、`dlv` 命令前先启用环境：

~~~bash
source scripts/go-env.sh
~~~

~~~bash
make env      # 查看当前生效的 Go / Delve 版本
make tidy     # 整理依赖（首次或改依赖后执行）
make test     # 运行自动化测试
make run      # 执行 FR-001 本地 Demo，SQLite 文件默认写入 data/reminder.db
make smoke    # 冒烟验证断点调试链路
make debug    # 交互式调试 reminder-service
~~~

VS Code 与 IntelliJ IDEA Ultimate 的调试配置、以及 `dlv` 在 macOS 上的签名问题，见 [docs/implementation/本地Go环境与调试.md](docs/implementation/本地Go环境与调试.md)。

当前 Demo 使用本地 Fixture 和 Mock/进程内适配器，已验证提醒资格决策、SQLite 落库和事件幂等；本期只使用 Push 单渠道，站内提醒承接已移入 P1；不代表真实 Push、App 站内提醒或线上指标结果。

## 设计原则

- MVP 首先服务有未完成任务、且提醒后可能回来的被动型学生。
- 首版使用可解释、可测试的规则引擎，不为了体现 AI 而强行接入大模型。
- 每次提醒都能解释是否发送、何时发送、通过什么渠道以及为什么。
- 频控、免打扰、Push 未授权或发送失败时的未触达处理、任务完成、幂等和失败重试属于核心质量要求。
- 任务完成率是业务结果指标，Push 到达率和打开率是渠道过程指标，不能混为一谈。
