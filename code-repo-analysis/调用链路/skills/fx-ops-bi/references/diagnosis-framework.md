# BI 诊断编排骨架

诊断流程：`BI 输入归一化 → 30 秒模块选择 → 模块首轮快照 → 模式核对 → 模块取证（跨域需求回抛主控） → 三段式结论`

## 1. 归一化输入

至少整理以下字段，缺失时先补齐：

- `tenant_id`：哪个租户的 BI 数据
- `symptom`：同步延迟 / 数据不准 / 加载慢 / 计算错误 / 拼表异常 / 渲染失败 / 字段问题 / 导出失败 / 权限不可见 / 目标值异常 / 订阅未推送
- `occurred_time`：问题发现时间或"数据应该是几点但没更新"的时间
- `channel`：报表 ID / 驾驶舱 ID / copier 任务 ID / traceId / 字段名
- `bi_module`：sync-delay / data-consistency / slow-query / join-splice / aggregation / render-failure / field-issue / export-failure / permission-issue / goal-management / subscription（以 references/playbooks/index.md 为唯一事实源）

## 2. 输入门禁

进入模块取证前，以下至少满足最低可执行状态：

- `tenant_id`：非 `pending`
- `bi_module`：非 `pending`
- `occurred_time`：给出绝对时间或"最近 N 小时"
- `evidence_dir`（双轨）：
  - **handoff 场景**（主控 fx-ops 派发）：使用主控分配的 `evidence_dir`
  - **standalone 场景**（机制咨询直进）：自建 `output/evidence/<YYYYMMDD-Issue>/`，本模块证据放其下 `bi-<bi_module>/` 子目录（对齐 AGENTS.md 全局格式）

不满足时先向用户补齐。

权限 / 对数 / 字段 / 目标 / 导出 / 订阅：必须先过对应 playbook 的 Step 0 产品口径，再进 dt_auth / CH。FAQ 互殴、未过缓存窗口、过期口径 → `排查结论：设计如此`，不升级研发。收口按模块类别：产品口径类（权限/对数/字段/目标/导出/订阅）必须 `排查结论：设计如此` 或 `排查结论：需要研发处理` 二选一；运维性能类（同步延迟/慢查询/聚合/拼表/渲染）用 `排查结论：需要研发处理` / `排查结论：需要基础设施或运维处理` / `排查结论：已定位，建议动作如下`。
