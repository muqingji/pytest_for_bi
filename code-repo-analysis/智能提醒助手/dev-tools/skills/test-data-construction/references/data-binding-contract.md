# 测试数据绑定契约

## 1. Case 结构

测试数据直接放在对应 case 的 `test_data` 中，避免独立数据文件和 case 靠文件名猜关联。

```json
{
  "id": "EVAL-021",
  "scenario": {
    "fixture": "case-eval-021"
  },
  "test_data": {
    "fixture": "case-eval-021",
    "request": {
      "user_id": "case-eval-021",
      "task_date": "2026-09-20",
      "trigger": "DAILY_BATCH"
    }
  },
  "request": {
    "body": "{data.request}"
  }
}
```

`test_data` 是该 case 的私有数据命名空间。推荐按 `request`、`clock`、`expected_context` 等用途分组，不把所有值铺在顶层。

## 2. 运行时占位符

| 写法 | 结果 |
| --- | --- |
| `"{data.request}"` | 整个值替换为对象，保留原生类型 |
| `"{data.attempt}"` | 可替换为整数、布尔、数组或对象 |
| `"user-{data.suffix}"` | 字符串内插，结果为字符串 |
| `"{step1.body.decision_id}"` | 继续表示前一步响应字段，语义不变 |

数据占位符可用于请求 `body`、`path`、`path_params`、`headers`、`omit_headers` 和 `expected`。不得引用其他 case 的数据，也不得从后续步骤取值。

缺失路径在发送请求前抛错，例如 `{data.request.user_id}` 对应字段不存在时，case 直接 error，不允许替换为空字符串或 `null`。

## 3. Fixture 绑定

`test_data.fixture` 必须等于 `testenv/fixtures/users.json` 中某个 `users[].user_id`。该用户的 `covers` 必须包含当前 case id；新建的强绑定 Fixture 默认只允许覆盖一个 case。

```json
{
  "user_id": "case-eval-021",
  "description": "EVAL-021：被动型用户有未完成任务",
  "task_template": "PENDING",
  "behavior": {},
  "preference": {},
  "usage": {},
  "covers": ["EVAL-021"]
}
```

以下内容放置规则固定：

| 数据 | 放置位置 |
| --- | --- |
| API 允许的 user_id、task_date、trigger、request_id | `test_data.request`，再装配到请求 |
| 任务数量、完成状态、截止时间 | Fixture 的任务模板或用户任务覆盖 |
| 行为窗口、分层信号 | Fixture `behavior` |
| 提醒开关、Push 权限、免打扰、时区 | Fixture `preference` |
| 已发送次数、延后次数 | Fixture `usage` |
| 前一步产生的 decision_id、schedule_id | `{stepN.body.xxx}`，不写入 `test_data` |

## 4. 隔离规则

- 可能改变决策、排程、投递或用量的 case 必须使用独立用户。
- 同一 case 的多步骤必须使用同一用户，依靠步骤顺序构造状态。
- 纯参数校验且请求不会写业务状态时可以复用无状态 Fixture，但必须在绑定报告说明理由。
- 不允许通过执行顺序让后一个 case 依赖前一个 case 的数据库状态。
- 不允许使用姓名、手机号、真实设备 ID 或生产导出数据。

## 5. 时间数据

优先使用：

1. 固定测试时钟与固定 `task_date`；
2. `deadline_local` 等相对任务日期表达；
3. 相对测试时钟的明确偏移。

如果被测服务不能控制时钟，而预期会随真实运行时刻变化，保留 `pending` 并写明解锁条件。数据构造 skill 不通过扩大截止时间或修改预期绕过该问题。

## 6. 变更规则

修改用例前置条件时，同一变更必须检查四处：TC 文档、case `test_data`、Fixture、绑定报告。修改接口字段时先更新 IDL 和自动化映射，再调整绑定；不得由数据构造反向发明接口字段。
