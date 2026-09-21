# 业务测试环境（pytest + Allure）

> 这是**业务测试**，不是单元测试。Go 单测走 `make test`，业务测试走 `make test-api` / `make test-report`，
> 两套环境互相隔离：业务测试只使用包内 `.testenv/` 的 Python 环境，不读仓库根 `.venv`，也不写系统目录。

## 1. 目录结构

| 路径 | 作用 |
| --- | --- |
| `tests/subjects/test_*.py` | **用例主体**：一个接口，或一组接口请求的组合场景。文件里只声明主体和运行方式 |
| `tests/cases/*.json` | **用例数据**：主体下的每条 case，含预期请求体与预期返回内容 |
| `tests/common/` | 用例加载、HTTP 客户端、字段断言、执行体、报告附件 |
| `tests/harness/` | **测试环境自检**：用本地桩服务验证整条管线，不代表业务结论 |
| `tests/cases/_harness/` | 自检用用例数据 |
| `testenv/config.json` | 运行配置（被测地址、令牌、调用方、超时） |
| `reports/` | Allure 原始结果与 HTML 报告产物（已 gitignore） |
| `.testenv/` | 包内独立 Python 环境（已 gitignore） |

## 2. 环境准备

```bash
make test-env                      # 等价于 bash scripts/bootstrap-test-env.sh
```

脚本会在包内创建 `.testenv/` 并安装 `requirements-test.txt`（pytest、pytest-xdist、allure-pytest、requests）。
pip 缓存也落在 `.testenv/.pip-cache`，不写用户目录。重建环境用 `bash scripts/bootstrap-test-env.sh --force`。

## 3. 运行方式

```bash
make test-selftest    # 测试环境自检（本地桩服务，不碰真实服务）
make test-api         # 业务测试（需要本机被测服务已启动）
make test-report      # 业务测试 + 生成 Allure HTML 报告
make test-open        # 浏览器打开最近一次报告
make test-clean       # 清理报告与缓存
```

直接透传 pytest 参数：

```bash
bash scripts/test-report.sh -k EVAL-001              # 只跑一条用例
bash scripts/test-report.sh -m subject -n 4          # 业务测试，4 进程并行
bash scripts/test-report.sh -m harness               # 只跑自检
./.testenv/bin/pytest -q -m subject                  # 不进报告，只看控制台
```

被测地址可在 `testenv/config.json` 修改，也可用环境变量或命令行覆盖：

```bash
REMINDER_BASE_URL=http://127.0.0.1:9090 ./.testenv/bin/pytest -m subject
./.testenv/bin/pytest -m subject --reminder-base-url=http://127.0.0.1:9090
```

## 4. 报告

- 原始结果（含附件）：`reports/allure-results`
- HTML 报告：`reports/allure-report/index.html`
- 报告里每条用例都带：预期请求与预期返回、每个步骤的实际请求与实际返回、预期与实际差异、`ac` / `fr` 标签
- `reports/allure-results/environment.properties` 记录本次运行的服务地址、调用方、Python 版本

生成 HTML 需要 Java（`brew install openjdk`）；脚本会自动探测 `/usr/local/opt/openjdk/bin` 等常见路径。
若 Java 或 `allure` CLI 缺失，脚本会保留 `allure-results` 并给出提示，不会伪造结论。

## 5. 用例数据格式

一个主体一个 JSON 文件（`tests/cases/<主体名>.json`），主体名必须与文件名一致：

```json
{
  "subject": "evaluate_reminder",
  "description": "提醒评估：POST /internal/v1/reminders/evaluate",
  "endpoint": { "method": "POST", "path": "/internal/v1/reminders/evaluate" },
  "cases": [ ... ]
}
```

单请求用例：

```json
{
  "id": "EVAL-001",
  "name": "被动型用户有未完成任务，生成 Push 排程",
  "priority": "P0",
  "ac": ["AC-001"],
  "fr": ["FR-001", "FR-002"],
  "scenario": { "fixture": "user-passive", "task_state": "PENDING" },
  "request": { "body": { "user_id": "user-passive", "task_date": "2026-09-20", "trigger": "DAILY_BATCH" } },
  "expected": {
    "status_code": 200,
    "headers": { "X-Request-ID": "$any" },
    "body": { "status": "CREATED", "reason_code": "ELIGIBLE", "decision_id": { "$regex": "^decision-[0-9a-f]{32}$" } }
  }
}
```

组合场景用例用 `steps`，可从上一步响应取值：

```json
{
  "id": "EVAL-013",
  "name": "同一 request_id 重复评估命中幂等",
  "steps": [
    { "name": "首次评估", "request": { "body": { "request_id": "idem-0001", "user_id": "user-snooze", "task_date": "2026-09-20", "trigger": "DAILY_BATCH" } },
      "expected": { "status_code": 200, "body": { "status": "CREATED" } } },
    { "name": "重复评估", "request": { "body": { "request_id": "idem-0001", "user_id": "user-snooze", "task_date": "2026-09-20", "trigger": "DAILY_BATCH" } },
      "expected": { "status_code": 200, "body": { "status": "REUSED", "decision_id": "{step1.body.decision_id}" } } }
  ]
}
```

字段约定：

| 字段 | 说明 |
| --- | --- |
| `match` | 比对模式。默认 `subset`：只校验预期中出现的字段，容忍响应新增字段（对应 IDL「字段只增不删」）；`exact` 连预期外字段一起校验 |
| `$any` | 通配任意非空值，用于每次不同的 ID、时间戳 |
| `{"$regex": "..."}` | 字符串正则匹配，用于锁定格式而不锁死取值 |
| `{stepN.body.<字段>}` / `{stepN.headers.<头名>}` | 引用第 N 步响应，可用于后续步骤的 `path` / `path_params` / `headers` / `body` / `expected` |
| `request_id` | 用例未显式给出时自动补 uuid4；幂等类用例必须显式写死 |
| `request.method` / `request.path` | 覆盖主体默认的 method/path；step 级同名字段优先级更高 |
| `pending` + `pending_reason` | 预期值尚未确认的用例，直接 `skip` 并写明原因，不猜、不伪绿 |

用例文件在**收集阶段**做结构校验：缺必填字段、`id` 重复、`match` 取值非法都会直接报错，
不会静默跳过。

## 6. 用例前置数据

用例里的 `scenario.fixture`（`user-passive`、`user-quiet`、`user-snooze` 等）是**前置种子数据**，
唯一事实源是 `测试方案/数据构造/数据构造说明.md`。被测服务必须按该说明加载同一批 Fixture，
否则用例的预期值不成立。

## 7. 服务不可达时的行为

`tests/subjects/` 下的主体在服务不可达时会**整体 skip 并说明原因**，不产生任何「通过」结论：

```text
SKIPPED 被测服务不可达（http://127.0.0.1:8080）。请先启动 reminder-service 的本地 HTTP 入口（技术方案 4.3.1）
```

此时想确认测试环境本身是否正常，跑 `make test-selftest`。

## 8. 自检的边界

`tests/harness/` 用本地桩服务证明「JSON 用例 → HTTP 请求 → 字段断言 → 报告附件」这条管线可用，
报告中会标注 `epic=测试环境自检` 且 `base_url` 指向桩服务（随机端口）。
**自检通过不等于业务通过**，两者在 Allure 报告中通过 `epic` 与 `base_url` 明确区分。
