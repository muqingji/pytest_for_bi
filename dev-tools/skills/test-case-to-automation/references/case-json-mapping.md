# 用例文档到用例数据的映射规则

## 1. 落地形式判定（阶段一）

| 分类 | 判定问题 | 处理 |
| --- | --- | --- |
| 可直译 | 用例步骤只调用一个接口，预期值与运行时刻、库内状态无关？ | 一条 TC → 一条 case |
| 需拆分 | 一条 TC 的预期里有多个独立判定点，或覆盖多个等价类？ | 拆成多条 case，case 名各自说清差异 |
| 条件可自动化 | 预期值依赖固定测试时钟、或依赖“库里已有到期排程”这类种子状态？ | 生成并标 `pending` + `pending_reason` |
| 不可自动化 | 需要断言事件表 / Push 文案 / 渠道失败链路，或需要跨用例共享状态？ | 只登记，不生成 |

拆分时不要合并无效等价类：每个无效等价类单独一条 case，避免一条失败遮蔽另一条。

## 2. 字段映射

| 用例文档字段 | 用例数据字段 | 说明 |
| --- | --- | --- |
| 用例编号（TC-xxx） | `tc` | 追溯用；`id` 仍用主体前缀编号 |
| 用例名称 | `name` | 直接用，不改写业务含义 |
| 优先级 | `priority` | 只允许 P0 / P1 / P2 |
| 关联需求 | `ac[]` / `fr[]` | 只填能溯源到的编号 |
| —— | `scenario.fixture` | 前置条件里的 `user_id`；必须已存在于 `testenv/fixtures/users.json` |
| 前置条件（结构化字段） | `scenario.*` | fixture 之外的额外前置（如 `test_clock`、`quiet_hours`）照实写 |
| 测试步骤 1..N | `steps[]` | 单步用例直接写 `request` + `expected`，不套 `steps` |
| 预期结果 | `expected.status_code` / `expected.headers` / `expected.body` | 只写用例文档明确写出的字段 |
| 来源 | —— | 写进映射报告的「依据」列，不写进用例数据 |

主体级字段固定为：

```json
{
  "subject": "evaluate_reminder_quiet_hours",
  "description": "提醒评估：免打扰场景（POST /internal/v1/reminders/evaluate）",
  "endpoint": { "method": "POST", "path": "/internal/v1/reminders/evaluate" },
  "cases": []
}
```

`subject` 必须与文件名一致；跨接口组合场景的 `endpoint` 取第一步的接口，后续步骤用
`request.method` / `request.path` 覆盖。

## 3. 预期值写法

| 场景 | 写法 |
| --- | --- |
| 每次运行都不同的 ID（decision_id、schedule_id） | `{"$regex": "^decision-[0-9a-f]{32}$"}`，或 `"$any"` |
| 只校验类型、不校验取值的计数 | `{"$type": "integer"}` |
| 可能为空的字段 | `"$any"`（要求非空） |
| 要锁定完整契约、不允许新增字段 | 该用例加 `"match": "exact"` |
| 默认 | 不加 `match`，按 `subset` 只校验写出的字段 |

字段名与枚举取值一律从 `docs/api/reminder-service.openapi.yaml` 复制，不凭记忆拼写。

## 4. pending 的用法

条件可自动化的用例必须同时写清两件事：

```json
{
  "pending": true,
  "pending_reason": "依赖固定测试时钟：被动型候选时刻为任务日 19:30（本地），跑在该时刻之后会返回 INSUFFICIENT_TIME"
}
```

`pending_reason` 要写**依赖什么 + 为什么不稳定 + 解锁条件**，不写“暂不执行”这类空话。
时钟到位后删掉这两个字段即可转正，其余数据不动。

数据缺口（缺 fixture 或种子状态）与时钟是两件事，各自登记一行，不要合并成一条原因。

## 5. 主体命名

- 主体名 = `<接口>_<业务场景>`，业务场景取用例文档里的功能分组标题，例如
  `evaluate_reminder_quiet_hours`、`dispatch_due_retry`。
- 跨接口组合场景单独一个主体，按调用顺序串接口名，例如 `evaluate_snooze_idempotency`。
- 已有主体（`evaluate_reminder` / `dispatch_due` / `snooze_reminder`）不迁移、不重命名。
- case id 前缀取接口缩写（`EVAL` / `DISP` / `SNZ`），序号在该前缀内全局唯一。

## 6. 常见坑

- **多步场景漏写 step 级 path**：主体 endpoint 决定默认路径，第一步调用的是别的接口时必须写
  `request.path`，否则请求会打到错接口（现有 `DISP-007`、`SNZ-001` 就是这个缺陷）。
- **幂等用例自动补 uuid**：未写 `request_id` 时引擎会补 uuid4，幂等断言会永远命中不了，必须写死。
- **401 用例**：用 `request.omit_headers: ["Authorization"]`，不要伪造无效令牌。
- **路径参数**：`snooze` 的路径含 `{decision_id}`，真实 decision_id 只能靠 `{step1.body.decision_id}` 占位符，
  不能写死。
- **`request.body: null`**：`body` 键必须存在，可为 `null`（如 dispatch 不带请求体）。
- **一次只改一件事**：新增 case 不要顺手改已有 case 的预期，已有数据的问题单独登记。
