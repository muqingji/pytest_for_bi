# reqId / traceId / rpcId 三层标识与精准诊断策略

> **适用 biz**: `biz-app-log`（ClickHouse）
> **核心语义（目标态）**:
> - **traceId** = **一次点击 / 打开页面** 等用户操作（不是「单次 RPC」）
> - **rpcId** = 该操作下的 **一次 RPC 请求**（目标形态为字符串 ID；旧 `x.y.z` 层级形态逐步废弃）
> - **reqId** = CEP/网关入口键（字段为 Array；弹窗/CLI 用短码 `N-xxxxxx` 反查 traceId）
>
> **核心问题**: 1 个 traceId 下常有多个 rpcId；仅按 traceId 查日志会被无关 RPC 误导；且不是所有表都有 rpcId 字段。

---

## 1. 三层标识语义

| 标识 | 含义（目标态） | 生命周期 | 来源 / 用法 |
| --- | --- | --- | --- |
| **reqId** | CEP 入口键；字段为 **Array**；日常入口用短码（如 `15-84f875`、`1-9f0e07`） | 反查用；**不是**跨表主锚点 | `log_cep_dist.reqId`；`has(reqId, '<短码>')` / CLI `--code` |
| **traceId** | **一次用户操作**（点击 / 开页）的链路 ID | 一次操作 → 可触发多次 RPC | 各表 `traceId` 列；反查成功后的 **主锚点** |
| **rpcId** | **一次 RPC 请求** 的标识 | 1 个 traceId → N 个 rpcId | 各表 `rpcId` / `rpc_id` 列；精查时 `AND rpcId = '<R>'` |

```
一次点击 / 打开页面
    └── traceId  （操作级）
            ├── rpcId₁  （一次 RPC）
            ├── rpcId₂
            └── rpcIdₙ
```

**关键关系**:

- **1 个 reqId 短码 → 多个 CEP 行 / 多个 traceId**：须配合时间窗 + `status` 消歧（见 `context-normalization` reqId 反查规则）
- **1 个 traceId → 多个 rpcId**：同一次点击可能并发/串行多个 RPC；**禁止**把 traceId 当成「单次 RPC 请求」
- **1 个 rpcId → 一次 RPC 请求**：缩小故障分支的主键；有列则优先 `traceId + rpcId` 精查

### 1.1 `log_cep_dist.reqId` 是数组

- 类型：`Array(String)`，**禁止** `reqId = '…'`，必须用 `has(reqId, '<短码>')`
- 常见形态：`["<16位hex>", "N-xxxxxx"]`（短码即弹窗「错误代码」/ CLI `--code`）
- 数组内偶发的长 hex：**非诊断入口**，勿称为 traceId / rpcId；日常 RCA **不必**单独输出
- **CEP 弹窗错误码**（如 `15-84f875`）存在于该数组中；反查后以 **traceId**（及行上 **rpcId** 若有）继续

### 1.2 rpcId 两种形态（混用 → 收敛）

| 形态 | 示例 | 状态 | 判读 |
| --- | --- | --- | --- |
| **A. 层级路径** | `0` / `0.1` / `1.2.3` | **旧形态，逐步废弃** | 曾用数字递进表达调用树；`ORDER BY length(rpcId), rpcId` **仅对此形态**有意义 |
| **B. 字符串 ID** | 非 `x.y.z` 的字符串（后续标准） | **目标形态** | **标志一次 RPC 请求**；等值匹配；排序用时间 / span，**禁止** `length(rpcId)` 建树 |

> **纪律**: 见到哪种形态就按哪种读，不要用「是不是带点号」否定对方。新逻辑与报告默认按 **形态 B（一次 RPC 的字符串 ID）** 表述；形态 A 仅兼容历史数据。
>
> **旧习惯纠偏**: 以前常用 traceId「当一次请求」查找。目标态下 traceId 只代表 **一次操作**；要定位失败的那一次 RPC，必须用 **rpcId**（或按 rpcId 分组后说明选了哪一个）。

---

## 2. 诊断策略：先窄后宽

### 默认流程（CEP → rpcId 精查）

```
用户报错 / CEP 错误码
       │
       ▼
Step 1: log_cep_dist 反查 traceId + rpcId
       │  WHERE has(reqId, '<错误码>') AND stamp BETWEEN ...
       │  → 拿到 traceId 和 对应的 rpcId
       ▼
Step 2: 用 traceId + rpcId 精准查询（避免噪声）
       │  app_log_dist:     WHERE traceId = '<T>' AND rpcId = '<R>'
       │  log_error_dist:   WHERE traceId = '<T>' AND rpcId = '<R>'
       │  eye_trace_dist:   WHERE traceId = '<T>' AND rpcId = '<R>'
       ▼
Step 3: 若目标表无 rpcId 列 → 退化策略（见 §3）
```

### 查询示例

**Step 1 — CEP 反查 traceId + rpcId**:

```bash
fx-ops idp --profile <profile> query biz-app-log --sql \
  "SELECT stamp, traceId, rpcId, bizName, uri, status, request_time, errorCode, error
   FROM log_cep_dist
   WHERE has(reqId, '15-84f875')
     AND stamp BETWEEN '2026-07-15 10:00:00' AND '2026-07-15 10:30:00'
   ORDER BY status DESC, request_time DESC LIMIT 20" -j
```

**Step 2 — 用 rpcId 精准查 app_log_dist**:

```bash
fx-ops idp --profile <profile> query biz-app-log --sql \
  "SELECT _time_second_, app, level, msg
   FROM app_log_dist
   WHERE traceId = '<TRACE_ID>'
     AND rpcId = '<RPC_ID>'
     AND _time_second_ BETWEEN '<T-10min>' AND '<T+10min>'
   ORDER BY _time_second_ ASC LIMIT 50" -j
```

**Step 2 — 用 rpcId 精准查 log_error_dist**:

```bash
fx-ops idp --profile <profile> query biz-app-log --sql \
  "SELECT _time_second_, app, pod, substring(msg, 1, 500) AS content
   FROM log_error_dist
   WHERE traceId = '<TRACE_ID>'
     AND rpcId = '<RPC_ID>'
     AND _time_second_ BETWEEN '<T-10min>' AND '<T+10min>'
   ORDER BY _time_second_ DESC LIMIT 20" -j
```

**Step 2 — 用 rpcId 精准查 eye_trace_dist（后端链路）**:

```bash
fx-ops idp --profile <profile> query biz-app-log --sql \
  "SELECT _time_second_, app, iface, method, cost, fail
   FROM eye_trace_dist
   WHERE traceId = '<TRACE_ID>'
     AND rpcId = '<RPC_ID>'
     AND _time_second_ BETWEEN '<T-10min>' AND '<T+10min>'
   ORDER BY _time_second_ ASC LIMIT 50" -j
```

---

## 3. 目标表无 rpcId 时的退化策略

当需要查询的表没有 `rpcId` 列时（见 §4 矩阵），按以下优先级退化：

| 优先级 | 策略 | 适用场景 |
| --- | --- | --- |
| **P1** | 先查有 rpcId 的表（如 `app_log_dist`）定位出错 app + 时间窗，再用 **traceId + 窄时间窗（≤5min）+ app** 查目标表 | 目标表有 `app` 列 |
| **P2** | 用 **traceId + 窄时间窗** 查目标表，人工排除时间上不属于问题窗口的记录 | 目标表无 `app` 列 |
| **P3** | 仅用 traceId 查，但**必须交叉验证**：将结果与 Step 1 中的出错 rpcId 对应的 URI/bizName 对比，排除明显无关的记录 | 最后手段 |

> **纪律**: 当 P2/P3 策略下发现多条记录时，**禁止直接取第一条作为根因**。必须说明存在多条记录、并给出排除/选择的理由。
>
> **兼容性约束**：下游 playbook 必须兼容以下情况：
> - `log_cep_dist` 行本身无 `rpcId`；
> - 上游未在 `context_updates.traceIdLookup.resolved_rpcId` 中回填 rpcId。
>
> 这两种情况均不视为错误或阻塞条件，只意味着无法使用 rpcId 做精确过滤，应按上述 P1/P2/P3 退化策略执行。

---

## 4. rpcId 覆盖矩阵（biz-app-log 常用表）

> **verified_at**: 2026-07-25 | platform: v4.37.3 | 来源: platform tenant-filters 多环境 query 列交集

### 有 rpcId / rpc_id 的表（当前快照 21 张）

| 表名 | 字段名 | 字段类型 | 说明（摘要） |
| --- | --- | --- | --- |
| `apibus_log_dist` | `rpc_id` | Nullable(String) | RPC 调用 ID |
| `app_log_dist` | `rpcId` | String | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `biz_log_crm_syncdata_dist` | `rpcId` | Nullable(String) | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `biz_log_dingtalk_coolapp_dist` | `rpcId` | Nullable(String) | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `biz_log_erpdatamem_dist` | `rpcId` | Nullable(String) | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `biz_log_sfa_web_log_dist` | `rpcId` | Nullable(String) | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `crm_syncstage_dist` | `rpcId` | Nullable(String) | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `eye_trace_dist` | `rpcId` | Nullable(String) | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `fs_flow_executions_log_dist` | `rpcId` | Nullable(String) | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `function_execute_stage_log_mv_dist` | `rpcId` | Nullable(String) | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `job_schedule_event_log_dist` | `rpcId` | Nullable(String) | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `log_cep_dist` | `rpcId` | String | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `log_error_dist` | `rpcId` | String | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `nginx_access_slow_dist` | `rpcId` | Nullable(String) | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `organization_security_dist` | `rpcId` | Nullable(String) | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `paas_agent_audit_log_dist` | `rpcId` | Nullable(String) | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `sentinel_block_dist` | `rpcId` | Nullable(String) | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `tomcat_access_daily_dist` | `rpcId` | Nullable(String) | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `tomcat_access_dist` | `rpc_id` | Nullable(String) | RPC 调用 ID（可空） |
| `tomcat_access2_dist` | `rpcId` | Nullable(String) | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `www_log_dist` | `rpcId` | Nullable(String) | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |

### 常见无 rpcId 的表（查询前仍以单表 schema 为准）

| 表名 | 诊断角色 | 退化策略建议 |
| --- | --- | --- |
| `rpc_dist` | RPC 统计汇总（聚合表） | 无 traceId/rpcId，按 app+module+`_time_second_` 短窗查 |
| `rpc_daily_dist` | RPC 按天（platform_gap 404） | 按 app+module+day 查 |
| `service_dist` | 服务调用汇总（聚合表） | 无 traceId/rpcId，按 app+module+stamp 短窗查 |
| `service_daily_dist` | 服务按天（platform_gap 404） | 按 app+module+day 查 |
| `rpc_slow_dist` | RPC 慢调用（聚合表） | 按 app+module+`_time_second_` 短窗查 |
| `mongo_slow_dist` | MongoDB 慢查询 | P2: traceId + 窄时间窗 |
| `biz_log_pg_lock_dist` | PG 锁监控 | P2: traceId + 窄时间窗 |
| `fs_flow_instance_log_dist` | 流程实例 | P2: traceId + 窄时间窗 |
| `fs_flow_execution_log_dist` | 流程节点执行 | P2: traceId + 窄时间窗 |
| `biz_log_workflow_v2_dist` | 工作流 V2 | P1: traceId + app |
| `biz_log_function_dist` | APL 函数执行 | 用 logId 关联，非 traceId |
| `biz_log_function_user_execute_dist` | APL 执行明细 | 用 logId 关联 |
| `biz_log_inner_function_api_dist` | APL 内部 API | 用 funcInstanceId 关联 |
| `biz_log_function_user_api_dist` | APL 用户 API | 用 logId 关联 |
| `sync_data_error_dist` | 数据同步错误 | P2: traceId + 窄时间窗 |
| `biz_log_erp_sync_log_dist` | ERP 同步日志 | P2: traceId + 窄时间窗 |
| `biz_job_log_dist` | 业务定时任务 | P2: traceId + 窄时间窗 |
| `page_dist` | 页面日志 | P2: traceId + 窄时间窗 |
| `paas_oplog_dist` | PaaS 操作日志 | P2: traceId + 窄时间窗 |
| `data_auth_log_dist` | 数据权限 | P2: traceId + 窄时间窗 |
| `object_data_bulk_log_dist` | 批量操作 | P2: traceId + 窄时间窗 |
| `k8s_events_dist` | K8s 事件 | P2: traceId + 窄时间窗 |
| `fs_k8s_app_scaler_metrics_dist` | K8s 扩缩容 | P2: traceId + 窄时间窗 |
| `elastic_search_log_dist` | ES 集群日志 | P2: traceId + 窄时间窗 |
| `log_center_dist` | 中间件原始日志 | 按 service_name + 时间窗过滤 |
| `notifier_broadcast_ack_dist` | 广播通知确认 | P2: traceId + 窄时间窗 |
| `biz_log_ai_dist` | AI 业务日志（**runtimeQueryable=false**，无 traceId 列） | **platform_gap**；勿 `SELECT *`；见 ai-log.md |

### foneshare 上不可用的表（show columns 报错，待确认）

| 表名 | 诊断角色 | 说明 |
| --- | --- | --- |
| `biz_log_flow_dist` | 流程日志 | show columns 报错，可能未部署或表名不同 |
| `hulian_log_dist` | 互联日志 | show columns 报错 |
| `integration_log_dist` | 集成日志 | show columns 报错 |
| `xxl_job_schedule_log_dist` | XXL-Job 调度 | show columns 报错 |
| `rocketmq_client_log_dist` | RocketMQ 客户端 | show columns 报错 |
| `egress_log_dist` | 出口日志 | show columns 报错 |

> **注意**: 字段名不统一——`tomcat_access_dist` 和 `apibus_log_dist` 使用 `rpc_id`（下划线），其余表使用 `rpcId`（驼峰）。拼 SQL 时注意区分。

---

## 5. 常见陷阱

| 陷阱 | 正确做法 |
| --- | --- |
| 把 **traceId** 当成「单次 RPC / 单次请求」 | traceId = **一次点击/开页**；其下可有多个 rpcId，须分组或 `AND rpcId` |
| 只按 traceId 查 app_log_dist，拉到多个 rpcId 后误判根因 | 有目标 rpcId 则加 `AND rpcId = '<R>'`；否则按 rpcId 分组并写明选择理由 |
| 把 reqId 数组里的 **长 hex** 叫成 rpcId / traceId | 长 hex 非入口；rpcId 看**列** `rpcId`/`rpc_id`；入口短码用 `has(reqId, …)` |
| 把弹窗短码 `N-xxxxxx` 当列 rpcId 做 `AND rpcId=` | 短码是 **reqId 查找键**；列 rpcId 是 RPC 请求 ID（形态 A 或 B） |
| 假定 rpcId **必须是** `0.1.2`，否则非法 | 双形态并存；**目标为字符串 ID**；`length(rpcId)` 建树仅兼容形态 A |
| `log_cep_dist.reqId` 用 `=` 比较 | reqId 是 `Array(String)`，必须用 `has(reqId, '<code>')` |
| 假设所有表都有 rpcId | 查 §4 矩阵或 `show columns` 确认，无 rpcId 时用 §3 退化策略 |
| `tomcat_access_dist` 用 `rpcId` 查询 | 该表字段名是 `rpc_id`（下划线），不是 `rpcId` |
| 从 reqId 短码直接当唯一 traceId | 1 短码可能对应多个 traceId，须时间窗 + status 消歧后从 log_cep_dist 反查 |

---

## 相关文档

- [biz-app-log.md](./biz-app-log.md) — biz-app-log 总览与常用表速查
- [diagnostic-scenarios.md](./diagnostic-scenarios.md) — 按诊断场景选表
- [log-cep.md](./log-cep.md) — CEP 事件日志字段与查询示例
- [known-gaps.md](./known-gaps.md) — 聚合表运行时缺口
