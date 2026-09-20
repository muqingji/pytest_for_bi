# 开发工具（dev-tools）

本目录是项目自建的 Codex 开发工具集，以本地 plugin 形态承载可复用的 Skill。

## 目录结构

~~~text
dev-tools/
├── README.md                  # 本文件：工具集说明与 Skill 编写规范
├── .codex-plugin/plugin.json   # plugin 清单，用于后续注册
└── skills/
    ├── prd-refinement/        # 按 9 稿模板改造 PRD
    ├── prd-to-acceptance-criteria/  # 从 PRD 生成并回查验收标准
    ├── prd-to-tech-design/    # 从 PRD 生成并回查后端技术方案
    ├── tech-design-implementation/  # 按技术方案逐项实现代码并回查
    └── test-plan-to-test-report/    # 按测试方案执行测试并产出测试报告
        ├── SKILL.md           # 每个 Skill 必有
        ├── agents/openai.yaml # 展示与默认提示
        ├── references/        # 模板与检查清单，按需读取
        └── scripts/           # 确定性回查脚本，按需
~~~

每个 Skill 目录结构相同：`SKILL.md` 必有，`agents/`、`references/`、`scripts/` 按需创建。

## 现有 Skill

| Skill | 作用 | 主要产出 |
| --- | --- | --- |
| `prd-refinement` | 依据产品方案与实际诉求改造 9 稿 PRD，控制来源、范围和数据真实性 | 符合 9 稿结构与事实要求的 PRD |
| `prd-to-acceptance-criteria` | 依据 9 稿 PRD 生成或审查验收标准 | 按颗粒度规范拆分的 AC 文档 + 回查报告 |
| `prd-to-tech-design` | 依据 9 稿 PRD 与产品方案 5 稿生成或审查后端技术方案 | 按模板 1~9 章的技术方案 + 回查报告 |
| `tech-design-implementation` | 依据已确认的技术方案逐项实现后端功能，强制未决项、单测、联调、双文档回查和人工确认门禁 | 功能代码与迁移、单测、联调记录、功能进度记录 |
| `test-plan-to-test-report` | 依据测试方案和验收标准执行测试，建立 AC 到用例到结果的追踪关系，并如实声明未覆盖范围 | 测试代码与 Fixture、测试执行证据、测试报告 |

## 快速开始

~~~bash
# 回查一份技术方案：无阻塞项时退出码为 0，可作为交付闸门
python3 dev-tools/skills/prd-to-tech-design/scripts/check_tech_design.py \
  --design "code-repo-analysis/智能提醒助手/技术方案/技术方案.md" \
  --prd "code-repo-analysis/智能提醒助手/智能提醒助手PRD(9稿).md" \
  --prd "code-repo-analysis/智能提醒助手/需求拆解/验收标准/验收标准.md"

# 回查验收标准
python3 dev-tools/skills/prd-to-acceptance-criteria/scripts/check_acceptance_criteria.py \
  --ac "code-repo-analysis/智能提醒助手/需求拆解/验收标准/验收标准.md" \
  --prd "code-repo-analysis/智能提醒助手/智能提醒助手PRD(9稿).md"

# 回查测试报告：AC 是否都有追踪关系、命令是否都有结果、结论是否越界
python3 dev-tools/skills/test-plan-to-test-report/scripts/check_test_report.py \
  --report "code-repo-analysis/智能提醒助手/docs/test-report.md" \
  --ac "code-repo-analysis/智能提醒助手/需求拆解/验收标准/验收标准.md"
~~~

回查脚本只依赖 Python 标准库。校验 Skill 元数据的 `quick_validate.py` 需要 PyYAML，可用仓库内 `.venv/bin/python` 运行。

实现阶段使用 `tech-design-implementation`：一次实现一个 P0 垂直切片，先跑未决项门禁，再编码、跑单测、做简单联调，最后运行上面两个回查脚本，并把结果写入 `docs/implementation/` 的功能进度记录。

测试阶段使用 `test-plan-to-test-report`：按测试方案的分层补齐用例、执行并记录证据，再用 `check_test_report.py` 回查 AC 追踪与结论边界，最后把结果写入 `docs/test-report.md`。

## Skill 编写规范

每个 Skill 至少包含 `SKILL.md`，正文按以下模块组织。

| 模块 | 作用 | 是否必须 |
| --- | --- | --- |
| YAML `name` | 定义 Skill 的唯一名称，用于识别 Skill，本身也会影响理解边界 | 必须 |
| YAML `description` | 定义 Skill 做什么、什么时候触发，是 Skill 的主要触发入口 | 必须 |
| 正文 `Goal` | 说明 Skill 的任务目标、产出方向和执行边界 | 必须 |
| 正文 `When to Use` | 补充说明用户会提出哪些请求时使用本 Skill，帮助 Agent 更准确理解适用范围 | 推荐 |
| 正文 `ToolsList` | 说明执行本 Skill 时允许或优先使用哪些工具、CLI、MCP | 推荐 |
| 正文 `Workflow` | 说明执行任务的主流程，指导 Agent 按步骤完成任务 | 必须 |
| 正文 `Resources` | Skill 所使用资源的速查表，列出 reference、scripts、assets 在何时被使用 | 推荐 |
| 正文 `Output` | 定义最终输出格式、命名规则、内容要求 | 必须 |
| 正文 `Related Skills` | 说明和哪些 Skill / Sub Agent 有协同关系，帮助复杂任务串联执行 | 可选 |

编写约定：

- `description` 要同时写清"做什么"和"何时触发"，并给出必要的不适用边界，避免误触发。
- 正文只写会影响判断的内容：约束、流程顺序、产出要求。不写通用常识和重复的政策复述。
- 详细清单、检查表、模板映射放到 `references/`，只在需要时读取，避免 SKILL.md 过长。
- 重复执行且要求确定性的检查用 `scripts/` 实现，不要每次让模型重新推导。
- 资源目录按需创建，不建空目录和无用途占位文件。

## 注册与使用

开发阶段直接按路径引用即可（例如 `dev-tools/skills/prd-to-tech-design`）。

需要让 Codex 自动发现时，二选一：

1. 将 `dev-tools` 作为本地 plugin 注册，plugin 清单已包含 `"skills": "./skills/"`。
2. 把 `dev-tools/skills/<skill-name>` 复制或软链到项目 `.codex/skills/<skill-name>`。

新增 Skill 时保持"一个 Skill 一个目录"，并在本文件的"现有 Skill"表中补一行。
