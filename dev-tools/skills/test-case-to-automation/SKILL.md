---
name: test-case-to-automation
description: 把智能提醒助手的测试用例文档（测试方案/测试用例.md 的 TC-xxx）逐条翻译成仓库既有的 pytest 数据驱动结构，产出或更新 tests/cases/*.json（请求与预期）与 tests/subjects/test_*.py（主体声明），回填用例文档的「自动化映射」字段，并把条件可自动化与不可自动化的用例连同原因、证据、替代覆盖方式分别登记。当用户要求“把测试用例转成自动化脚本”“用例落成 JSON 用例”“按用例补主体文件”“这些用例哪些能自动化”时使用；不用于设计或评审测试用例、实现业务代码、改造被测服务、执行测试或写测试报告。
---

# 测试用例转自动化用例数据与主体

把测试用例文档翻译成 `tests/cases/*.json` + `tests/subjects/test_*.py`，只覆盖智能提醒助手
（reminder-service 的三个 HTTP 接口），不做通用框架改造。

## Goal

一份封板用例经过本 skill，要达到“能被 pytest 收集、能跑、跑不出结论时有明确原因”的状态。产出：

1. `tests/cases/<主体>.json`：请求与预期数据。
2. `tests/subjects/test_<主体>.py`：主体声明与运行方式（缺主体才新建）。
3. `测试方案/测试用例.md`：回填每条用例的「自动化映射」字段。
4. `测试方案/自动化映射报告.md`：映射表、两张清单、数据缺口、契约核对与回查结论。

三条不变式，与上游 `test-case-design` 保持一致：

- **不臆想**：响应字段名、枚举取值、必填性、状态码只从 `docs/api/reminder-service.openapi.yaml` 取。
  用例文档没写的预期不补，IDL 里不存在的字段不写。
- **不越权**：不改 Go 代码、不改 `tests/common/` 引擎、不改 `testenv/fixtures/users.json`、不改 IDL。
  缺前置数据只出缺口清单。
- **不静默**：条件可自动化与不可自动化的用例逐条登记 TC 编号、原因、证据，不丢弃、不用松断言凑绿灯。

## When to Use

适用：

- “把测试用例转成自动化脚本 / 自动化用例”。
- “按用例生成 `tests/cases/*.json`”“按用例补 `tests/subjects/` 主体文件”。
- “这些用例哪些能自动化、哪些不能”。

不适用：

- 设计、评审、封板测试用例 → `test-case-design`。
- 执行测试、生成 Allure 报告、写 `docs/test-report.md` → `test-plan-to-test-report`。
- 实现业务代码、加固定测试时钟、搭渠道桩 → `tech-design-implementation`（属被测服务改造）。
- 构造业务数据取值本身 → 数据构造环节；本 skill 只判断“现有 fixture 够不够”。

## ToolsList

| 工具 | 用途 |
| --- | --- |
| 读文件 | 读用例文档、IDL、验收标准、现有用例数据与主体文件 |
| 写文件 | 只写上面「产出」列出的四类目标，其他文件一律不改 |
| `scripts/check_case_automation.py` | 确定性回查，退出码当闸门；不靠模型自评 |
| `./.testenv/bin/pytest -m subject --collect-only -q` | 收集校验：JSON 结构能否被 `case_loader` 接受、主体文件能否导入 |
| `make test-selftest` | 证明用例管线本身没被改坏 |

## 输入与权威顺序

| 来源 | 用途 | 冲突时的地位 |
| --- | --- | --- |
| `测试方案/测试用例.md`（TC-xxx） | 用例编号、前置条件、测试步骤、预期结果、优先级、来源 | 主输入 |
| `docs/api/reminder-service.openapi.yaml` | 字段名、枚举、必填性、错误信封、示例 | **契约唯一来源**，与用例文档冲突时以 IDL 为准并在报告里记录差异 |
| `测试方案/测试场景清单.md` | 场景归属、场景类型、本期是否覆盖 | 覆盖核对 |
| `需求拆解/验收标准/验收标准.md` | `ac` 标签取值来源 | 标签合法性校验 |
| `docs/test-report.md`、`技术方案/技术方案.md` | 本期范围、已知未实现项 | 判断“现在能不能跑” |
| `tests/common/` | 引擎已支持的能力 | 判断“写法上能不能表达” |
| `testenv/fixtures/users.json` | 现有前置数据的事实源 | 判断前置条件是复用还是缺口 |

`测试方案/测试用例.md` 不存在时**直接停下并说明缺输入**，不从场景清单降级推导用例。

## Workflow

### 阶段一：逐条映射（只出表，不写文件）

1. 解析用例文档，列出全部 TC 编号。缺编号的用例先报错，不自行编号。
2. 逐条判定落地形式，四类之一：

   | 分类 | 含义 | 处理 |
   | --- | --- | --- |
   | 可直译 | 一条 TC → 一条 case，预期值与运行环境无关 | 直接生成 |
   | 需拆分 | 一条 TC 覆盖多个等价类或多个判定点 | 拆成多条 case，写明拆分依据 |
   | **条件可自动化** | 脚本能写、能被收集，但预期值依赖未决项（固定测试时钟等）或缺少种子状态 | 生成并标 `pending` + `pending_reason` |
   | 不可自动化 | 引擎表达不出来（命中「能力边界」里做不到的项） | 只登记，不生成 case |

3. 判定主体归属：按 **接口 + 业务场景** 命名，业务场景取用例文档里的功能分组标题，例如
   `evaluate_reminder_quiet_hours`。跨接口的组合场景单独开主体，名称按调用顺序串起来，
   例如 `evaluate_snooze_idempotency`。已有主体不迁移、不重命名，新主体才按本规则。
4. 产出五张表，写入 `测试方案/自动化映射报告.md` 并把状态标为「待门禁 A 审批」，
   然后交用户确认（**门禁 A**）：

   | 表 | 内容 |
   | --- | --- |
   | 映射表 | TC → case id → 主体 → 关键预期 → 依据（`文件:行号`） |
   | 条件可自动化清单 | TC、依赖的未决项或缺失种子状态、解锁条件 |
   | 不可自动化清单 | TC、原因、证据（命中哪条能力边界）、替代覆盖方式 |
   | 数据缺口清单 | TC、需要的前置状态、现有 fixture、复用 / 需新增 |
   | 契约核对表 | 用例预期里的字段与枚举能否在 IDL 中找到；差异只记录，**不自行改 IDL** |

用户确认后才进入阶段二。用户增删改后重新提交门禁 A。

### 阶段二：生成文件

1. 新建或增量更新 `tests/cases/<主体>.json`：
   - 已存在的 `case.id` 一律不覆盖，冲突直接停下。
   - case id 用「接口前缀-三位序号」（`EVAL` / `DISP` / `SNZ`），序号在该前缀内**全局唯一**，
     新用例接着已有最大号往下排，不按主体重新从 001 开始。
   - 用 `tc` 字段记录来源用例编号；`case_loader` 只校验必填字段，额外的追溯字段安全。
   - 字段与预期值的写法见 `references/case-json-mapping.md`。
2. 主体文件缺失才新建 `tests/subjects/test_<主体>.py`；已有主体文件不动。
   内容与现有主体一致：主体加载 + `@pytest.mark.subject` + `parametrize` + `decorate` + `execute`。
3. 回填 `测试方案/测试用例.md` 每条的「自动化映射」：
   可执行的写 `tests/cases/<主体>.json#<case id>`；条件可自动化的写同一路径并注明 pending；
   不可自动化的写明原因与替代覆盖方式。
4. 把 `测试方案/自动化映射报告.md` 的状态改为「已通过门禁 A，待门禁 B 复核」。

### 阶段三：回查与门禁 B

1. 跑确定性回查：

   ```bash
   python3 dev-tools/skills/test-case-to-automation/scripts/check_case_automation.py \
     --project-root code-repo-analysis/智能提醒助手
   ```

   有阻塞项就修完再重跑，不带着阻塞项进入门禁 B。
2. 跑收集校验，确认结构能被引擎接受：

   ```bash
   cd code-repo-analysis/智能提醒助手 && ./.testenv/bin/pytest -m subject --collect-only -q
   ```

3. 跑 `make test-selftest`，证明用例管线本身没被改坏。
4. 把改动摘要交用户复核（**门禁 B**）：文件清单、新增 case 数、`pending` 数、两张清单、
   回查与收集结论。复核清单见 `references/gate-b-checklist.md`。
   通过后把报告状态改为「已通过门禁 B」并写入回查结论；不通过则回到阶段二改，重新走门禁 B。

被测服务不可达时业务用例会整体 skip，这是预期行为，不代表失败；本 skill 不代替执行测试。

## 能力边界

引擎已支持、直接可用，不要自己发明写法：

| 需求 | 写法 |
| --- | --- |
| 单请求 | `request` + `expected` |
| 组合场景 / 多步 | `steps[]`，每步 `name` / `request` / `expected` |
| 从上一步响应取值 | `{step1.body.decision_id}`、`{step1.headers.X-Request-ID}`，可用于后续 `path` / `path_params` / `headers` / `body` / `expected` |
| 覆盖默认 method/path | `request.method` / `request.path`，step 级优先级更高 |
| 路径参数 | `request.path_params` |
| 免鉴权用例 | `request.omit_headers: ["Authorization"]` |
| 自动补 `request_id` | 未显式给出时补 uuid4；**幂等用例必须写死** |
| 通配预期 | `"$any"`、`{"$regex": "..."}`、`{"$type": "integer"}` |
| 比对模式 | `match: subset`（默认）/ `exact` |
| 预期未确认 | `pending` + `pending_reason`，用例被 skip 并写明原因 |
| Allure 标签 | `priority` / `ac[]` / `fr[]` / `scenario` 自动进报告 |

引擎做不到、命中即进「不可自动化清单」：

- 断言非 JSON 响应体，断言数据库、outbox 或事件表。
- 观测 Push 文案（AC-014），观测渠道发送失败与重试链路（缺可控渠道桩）。
- 跨用例共享状态、setup / teardown、状态重置接口。
- 事件链路完整性（AC-011，三个接口没有事件查询入口）。

**注意区分**：预期值依赖运行时刻（时钟）或缺少种子状态的用例**属于条件可自动化**，
不放进不可自动化清单；它们照样生成，标 `pending` 并写明解锁条件。

## Resources

| 资源 | 何时读 |
| --- | --- |
| `references/case-json-mapping.md` | 阶段一分类判定与阶段二写字段时：字段映射、预期值写法、主体命名、常见坑 |
| `references/automation-mapping-report-template.md` | 阶段一产出报告时：五张表与结论的固定格式 |
| `references/gate-b-checklist.md` | 阶段三交复核前：门禁 B 逐项确认清单 |
| `scripts/check_case_automation.py` | 阶段三回查；`--stage mapping` 只查报告，`--stage delivered` 全量 |

## Output

| 产物 | 路径 |
| --- | --- |
| 用例数据 | `tests/cases/<主体>.json`（新建或增量更新） |
| 主体文件 | `tests/subjects/test_<主体>.py`（缺主体才新建） |
| 用例文档回填 | `测试方案/测试用例.md` 的「自动化映射」字段 |
| 映射与回查报告 | `测试方案/自动化映射报告.md` |

报告与用例数据必须一致：报告里引用的 case id 必须真实存在，带 `tc` 字段的用例必须能在映射表里找到。

## Related Skills

- 上游：`test-case-design`（产出 `测试方案/测试用例.md` 与 `测试方案/测试场景清单.md`）。
- 下游：`test-plan-to-test-report`（执行用例、生成 Allure 报告、写 `docs/test-report.md`）。
- 不进入：`tech-design-implementation` 的范围（引擎与被测服务改造）。
