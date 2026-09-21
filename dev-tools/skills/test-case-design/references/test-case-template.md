# 场景清单与用例清单的写法

## 1. 场景清单

~~~markdown
# 测试场景清单

> 状态：待审批 / 已审批（审批日期）
> 来源：PRD、验收标准、技术方案
> 编号规则：SC-0NN，全局唯一、不回收

## 1. 决策规则

### SC-001 被动型用户有未完成任务时生成提醒
- 优先级：P0
- 来源：code-repo-analysis/智能提醒助手/智能提醒助手PRD(9稿).md:301
- 关联需求：AC-001、FR-001
- 覆盖维度：正常路径
- 判定点：should_remind=true；生成一条 Push 排程；原因码为 ELIGIBLE
- 优先理由：直接对应 P0 需求的主路径
~~~

字段约定：

| 字段 | 要求 |
| --- | --- |
| 优先级 | `P0` / `P1` / `P2`，不得高于其来源需求的优先级 |
| 来源 | `文件:行号`，多个用顿号分隔；允许补充章节名 |
| 关联需求 | 关联的 `AC-xxx` 与 `FR-xxx`；纯工程场景可只写技术方案来源 |
| 覆盖维度 | 正常、前置不满足、终止或取消、幂等与并发、频控上限、失败与异常、时间边界、数据边界、设置变更 |
| 判定点 | 一句话说清“看到什么算通过”，必须是可观察量 |
| 优先理由 | 为什么给它这个优先级，避免优先级凭感觉 |

## 2. 用例清单

~~~markdown
### TC-001 被动型用户有未完成任务时生成 Push 排程
- 场景：SC-001
- 优先级：P0
- 前置条件：
  - 用户类型：被动型（PASSIVE）
  - 任务状态：PENDING；required_count=5、completed_count=2；截止时间为任务日期当天 23:30（用户本地）
  - 行为信号：history_days_available=7、inactive_days=0、complete_days_7d=2、reminder_attributed_complete_days_7d=1
  - 提醒设置：reminder_enabled=true、push_enabled=true、quiet_hours=21:30-07:00、timezone=UTC、daily_push_cap=1
  - 当日用量：push_sent_count=0、snooze_sent_count=0
  - 外部依赖：固定测试时钟（否则候选时刻会落到当前时间之前）
  - 已有 fixture：user-passive（复用）
- 测试步骤：
  1. 以 trigger=DAILY_BATCH 调用提醒评估接口
  2. 读取响应中的决策字段
- 预期结果：
  1. status=CREATED
  2. reason_code=ELIGIBLE
  3. should_remind=true、channel=push
  4. scheduled_at 为任务日期当天的 19:30（用户本地时区）
- 来源：code-repo-analysis/智能提醒助手/智能提醒助手PRD(9稿).md:338
- 自动化映射：待实现
- 来源类型：文档推导 / 代码补充（阶段五填）
~~~

要求：

- 一条用例一个判定点；同一场景的多分支拆成多条用例。
- 前置条件用**字段**而不是句子，字段名与数据构造说明对齐，让数据构造 skill 能直接照着造。
- 前置条件不写具体取值以外的实现细节（不写 SQL、不写表名、不写内部函数名）。
- 预期结果是可观察值；禁止“正常”“符合预期”“无异常”“功能可用”这类空话。
- 依赖未决项的预期结果，写明依赖哪条待确认，不写临时假设。

## 3. 用例优先级

| 优先级 | 判定标准 |
| --- | --- |
| P0 | 来源需求是 P0，且用例覆盖主路径或会阻断主路径的拒绝/异常分支 |
| P1 | 来源需求是 P1，或来源是 P0 但属于边界、边界组合、非主路径异常 |
| P2 | 体验类、文案类、探索性、长期观察项 |

用例优先级可以低于场景，不可以高于。降级要在用例里写一句理由。

## 4. 前置条件字段字典

固定字段名，不随需求变化随意发明；确实需要新字段时先补进数据构造说明再引用。

| 分组 | 字段 |
| --- | --- |
| 用户 | `用户类型`（PASSIVE / SELF_DRIVEN / INACTIVE / RETURNING）、`user_id` |
| 任务 | `任务状态`（PENDING / COMPLETED / EXPIRED / COMPLETED_BEFORE_SEND / NO_TASK）、`required_count`、`completed_count`、`estimated_minutes`、`截止时间` |
| 行为 | `history_days_available`、`inactive_days`、`complete_days_7d`、`reminder_attributed_complete_days_7d`、`data_degraded` |
| 设置 | `reminder_enabled`、`push_enabled`、`quiet_hours`、`timezone`、`daily_push_cap` |
| 用量 | `push_sent_count`、`snooze_sent_count` |
| 环境 | `外部依赖`（固定时钟、渠道桩、实验分组）、`已有 fixture`（复用 / 需新增） |

## 5. 数据缺口清单

阶段三必须单独输出一节，直接交给数据构造 skill：

~~~markdown
## 数据缺口

| 用例 | 需要的前置数据 | 现有 fixture | 建议 |
| --- | --- | --- | --- |
| TC-009 | 免打扰区间覆盖全天以保证任意时刻可复现 | 无 | 新增 fixture 用户，或引入固定测试时钟 |
~~~
