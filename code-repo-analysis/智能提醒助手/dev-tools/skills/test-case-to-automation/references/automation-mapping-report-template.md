# 自动化映射报告模板

写入 `code-repo-analysis/智能提醒助手/测试方案/自动化映射报告.md`。
六节标题与表格列名是回查脚本的解析依据，不要改名。

~~~markdown
# 测试用例转自动化映射报告

> 状态：待门禁 A 审批 / 已通过门禁 A，待门禁 B 复核 / 已通过门禁 B
> 生成方式：test-case-to-automation
> 输入用例：测试方案/测试用例.md（共 N 条，其中可直译 X 条、需拆分 Y 条、条件可自动化 Z 条、不可自动化 W 条）
> 契约来源：docs/api/reminder-service.openapi.yaml

## 1. 映射表

| TC | case id | 主体 | 关键预期 | 依据 |
| --- | --- | --- | --- | --- |
| TC-001 | EVAL-001 | evaluate_reminder | reason_code=ELIGIBLE、should_remind=true | 测试方案/测试用例.md:120 |

## 2. 条件可自动化清单

| TC | 依赖 | 解锁条件 | 处理 |
| --- | --- | --- | --- |
| TC-016 | 服务端时钟不可控，候选时刻 19:30 | 被测服务支持 --now 或 REMINDER_TEST_NOW | 生成并标 pending，时钟到位后删字段转正 |

## 3. 不可自动化清单

| TC | 原因 | 证据 | 替代覆盖方式 |
| --- | --- | --- | --- |
| TC-030 | 需要断言事件表 | 三个接口没有事件查询入口（AC-011 在测试场景清单第 8 节登记为未覆盖） | Go 单测 + 库表断言 |

## 4. 数据缺口清单

| TC | 需要的前置状态 | 现有 fixture | 建议 |
| --- | --- | --- | --- |
| TC-009 | 已关闭提醒但当天已有未发送排程 | 无 | 需新增 fixture 用户（数据构造环节补） |

## 5. 契约核对表

| TC | 用例预期字段/枚举 | IDL 定位 | 结论 |
| --- | --- | --- | --- |
| TC-001 | reason_code=ELIGIBLE | components.schemas.ReasonCode.enum | 一致 |

## 6. 回查结论

- 命令：`python3 dev-tools/skills/test-case-to-automation/scripts/check_case_automation.py --project-root code-repo-analysis/智能提醒助手`
- 收集校验：`./.testenv/bin/pytest -m subject --collect-only -q`
- 管线自检：`make test-selftest`
- 结果：
- 仍为 pending 的用例：
- 未覆盖与依赖：
~~~

## 填写要求

- **映射表**：每条可执行的 TC 一行；一条 TC 拆成多条 case 时写多行，或在一行里用 `、` 分隔。
  「依据」必须是 `文件:行号`，回查脚本会解析并确认文件存在。
- **条件可自动化清单**：写清依赖什么、解锁条件是什么；不要写成“暂时不做”。
- **不可自动化清单**：必须给证据，指到具体的能力边界或文档条目，不能只写原因。
- **契约核对表**：只记录用例预期里出现的字段与枚举；发现 IDL 与用例文档冲突时在这里记录差异，
  不自行改任何一边。
- **回查结论**：命令与结果要照抄实际输出，失败就写失败，不写“基本通过”。
