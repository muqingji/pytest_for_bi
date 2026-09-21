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
    ├── test-case-design/            # 从 PRD 与技术方案推导场景、生成用例并按代码补全封板
    ├── test-case-review/            # 独立评审场景与用例：先重推导基线，再核验溯源与覆盖
    ├── test-case-to-automation/     # 把封板用例翻译成用例数据与主体文件
    ├── test-plan-to-test-report/    # 按测试方案执行测试并产出测试报告
    ├── code-review/                 # 只读评审后端代码与文档一致性
    └── bug-fix/                     # 缺陷修复闭环：复现 → 回归用例 → 最小修复 → 全量验证 → CR
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
| `tech-design-implementation` | 依据已确认的技术方案逐项实现后端功能，强制未决项、单测（覆盖率 100%）、模块集成测试全通过、联调、双文档回查和人工确认门禁 | 功能代码与迁移、单测与覆盖率证据、模块集成测试结果、联调记录、功能进度记录 |
| `test-case-design` | 依据 PRD、验收标准与技术方案推导测试场景，经场景审批、用例评审、按代码补全三道门禁生成并封板用例；每道门禁按“AI 评审 → 人工确认”两步走 | 测试场景清单、测试用例清单、封板记录、回查报告 |
| `test-case-review` | 以第三方评审者视角独立重推导基线，逐条实读原文核验溯源、等价类、可观测性与可复现性，输出分级评审意见；不修改被评审文档 | 测试用例评审报告 |
| `test-case-to-automation` | 把封板测试用例逐条翻译成 `tests/cases/*.json` 用例数据与 `tests/subjects/test_*.py` 主体文件，回填用例文档的自动化映射，并显式登记条件可自动化与不可自动化的用例 | 用例数据 JSON、主体文件、自动化映射报告 |
| `test-plan-to-test-report` | 依据测试方案和验收标准执行测试，建立 AC 到用例到结果的追踪关系，并如实声明未覆盖范围 | 测试代码与 Fixture、测试执行证据、测试报告 |
| `code-review` | 只读评审智能提醒助手后端代码：FR/AC/技术方案一致性、业务正确性、状态与持久化安全、并发幂等、事件链路、隐私与测试证据 | 分级 findings（P0~P3）与审查结论 |
| `bug-fix` | 先判定缺陷归属再复现，做最小根因修复并跑全量单测、竞态、静态检查与业务接口用例（覆盖率不得下降），经 `code-review` 复核后产出带验证范围的修复记录 | 修复代码、先红后绿的回归用例、含验证范围的修复记录 |

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

# 回查测试场景与用例：来源能否解析、场景与用例是否双向追踪、优先级是否越权
python3 dev-tools/skills/test-case-design/scripts/check_test_cases.py \
  --scenarios "code-repo-analysis/智能提醒助手/测试方案/测试场景清单.md" \
  --cases "code-repo-analysis/智能提醒助手/测试方案/测试用例.md" \
  --repo-root .
~~~

~~~bash
# 回查评审报告：意见字段是否完整、结论与级别是否一致、待裁定项是否越权替用户决定
python3 dev-tools/skills/test-case-review/scripts/check_review_report.py \
  --report "code-repo-analysis/智能提醒助手/测试方案/测试用例评审报告.md" \
  --repo-root .
~~~

~~~bash
# 回查用例转自动化：TC 是否全部落地、字段与枚举能否溯源到 IDL、fixture 是否存在
python3 dev-tools/skills/test-case-to-automation/scripts/check_case_automation.py \
  --project-root code-repo-analysis/智能提醒助手 \
  --stage mapping          # 门禁 A 前只查映射报告；省略该参数做全量检查
~~~

~~~bash
# 回查缺陷修复记录：归属、复现、回归用例、覆盖率、CR 处置、未验证是否齐全
python3 dev-tools/skills/bug-fix/scripts/check_fix_record.py \
  --record code-repo-analysis/智能提醒助手/docs/fixes/BUG-001-<简述>.md \
  --project-root code-repo-analysis/智能提醒助手
~~~

回查脚本只依赖 Python 标准库。校验 Skill 元数据的 `quick_validate.py` 需要 PyYAML，可用仓库内 `.venv/bin/python` 运行。

实现阶段使用 `tech-design-implementation`：一次实现一个 P0 垂直切片，先跑未决项门禁，再编码、跑单测并确认覆盖率 100%、跑模块集成测试并确认全部通过、做简单联调，最后运行上面两个回查脚本，并把结果写入 `docs/implementation/` 的功能进度记录。

测试设计阶段使用 `test-case-design`：从 PRD、验收标准与技术方案推导测试场景，先给用户审批场景清单，通过后再生成带前置条件、步骤与预期结果的用例交评审，业务代码完成后按代码补全并评估影响范围，最后封板留存。回查脚本按 `文件:行号` 校验来源可解析，避免出现无依据的臆想用例。

三道门禁都由 `test-case-review` 先做 AI 评审：门禁 A（场景）用 quick 强度只查覆盖缺口与错引用，门禁 B（用例）用 standard 全量评审，门禁 C（封板）只复审变更点与受影响项。存在未处理阻塞项时不得提交人工确认；AI 评审的“通过”不构成门禁通过。评审者先不看作者产物、独立重推导一份基线再比对，因此能抓出“整条 AC 漏了”这类缺口，而不是只做格式检查。评审只出报告、不改被评审文档，改动由作者走 `test-case-design` 的变更流程后复审。`check_review_report.py` 校验评审报告自身：每条意见是否有位置、证据与修复建议，结论与意见级别是否一致，待裁定项有没有越权替用户拍板。

用例封板后使用 `test-case-to-automation`：把 TC 逐条翻译成 `tests/cases/*.json` 与 `tests/subjects/test_*.py`，经映射表审批（门禁 A）与生成后复核（门禁 B）两道人工门禁，并用回查脚本校验 TC 全覆盖、预期字段与枚举可溯源到 IDL、fixture 存在、映射双向一致。

缺陷修复使用 `bug-fix`：先判定缺陷归属（业务代码 / 用例与测试资产 / 引擎脚本 / 契约文档），再复现、补一条先红后绿的回归用例、做最小根因修复，跑全量单测、竞态、静态检查与业务接口用例并确认覆盖率没有下降，随后用 `code-review` 审查本次改动并逐条处置 finding，最后产出含「验证范围」的修复记录。

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
