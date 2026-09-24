---
symptom: CEP 错误码 / 前端报错 / reqId 反查
inputs:
 required: [error_code_or_reqid]
 optional: [screenshot_time, tenant_id, trace_id]
outputs:
 signals: [trace_id, company_name, tenant_ei_or_ea, uri, error_code, error_message, top_error_token]
 next_skills: [fx-ops-query, fx-ops-monitoring, code-search, resolve_tenant_cloud]
escalate_when:
 - 同 app + 租户 + token 在短时间集中爆发时，升级为完整深挖
 - 命中下游超时或资源异常时，交回 fx-ops 主控继续分发
---

# CEP 错误码 / 前端报错首轮诊断

输入：CEP 错误码（如 `1-a927cb`、`15-84f875`）或用户提供的报错截图。
输出：受影响企业、错误堆栈、首轮根因结论；必要时按 HND / 质量门禁继续深挖。

> 字段以现场 schema 为准：列名与 RCA 默认投影见 `fx-ops-query` 对应单表文档（字段定义 + 查询示例）；跨表易错见 query「高频表误用列名」。如查询报 "column not found"，先 `fx-ops idp --profile <profile> show columns biz-app-log <table> -j` 拿真实 schema，再调整。
>
> 查询口径：CEP、错误、慢请求、慢 SQL 和应用运行日志统一走 `biz-app-log`，并在 SQL 中指定真实表名，例如 `log_cep_dist`、`fs_cep_slow_error_dist`、`log_error_dist`、`slow_log_dist` / `sql_slow_dist`、`tomcat_access_slow_dist`、`app_log_dist`。
>
> **SQL 时间过滤**：时间条件必须用显式字面量 `'YYYY-MM-DD HH:MM:SS'`（或占位符 `<T0>`/`<T1>` 替换为算出的字面量）。`log_cep_dist` 用 `stamp`，`log_error_dist`/`app_log_dist` 等用 `_time_second_`。禁止 `toDateTime(...) - INTERVAL` / `toDateTime64` / `toDate`。

## 错误码识别门禁（静默执行）

按顺序逐项自检，不得跳步。默认不在对话中展开 Checklist；只有缺项、风险项、升级完整路径或用户要求审计时，才显式标注"未完成 / 不适用 / 已跳过原因"。

### S. 信号预判（`log_cep_dist` 命中后立即判断，决定执行路径）

`log_cep_dist` 首行命中后，根据以下信号组合选择执行路径，**避免在快速失败场景下跑无价值的慢查询表**：

| 信号组合 | 路径 | 并行查询 | 跳过 |
|---------|------|---------|------|
| request_time < 100ms + status ≥ 500 + error 含异常类名（NPE/ClassCast/NFE 等） | **快速失败路径** | `log_error_dist` | C2 `fs_cep_slow_error_dist`, C3 `slow_log_dist`, C4 `tomcat_access_slow_dist`, C5 `app_log_dist`, C6 `biz_log_function_dist`（请求仅 100ms，慢查询表无价值；APL/爆发仅在升级条件命中时补） |
| request_time < 100ms + status ≥ 500 + error 含业务错误码描述 | **快速业务失败路径** | 必要时 `log_error_dist` | C2-C6 全跳，直接从 CEP errorCode/error 得出结论 |
| 1000ms ≤ request_time < 5s + status ≥ 500 | **中速路径** | `log_error_dist` + `tomcat_access_slow_dist` | C2 `fs_cep_slow_error_dist`、C5 `app_log_dist`、C6 `biz_log_function_dist`（仅当证据不足、HND 或质量门禁要求时补） |
| request_time ≥ 5s | **慢请求路径** | 完整时间线四层：cep(入口耗时) → tomcat(应用层耗时) → `app_log_dist`(StopWatch分段) → `biz_log_function_dist`(APL函数耗时)。并行补充：`log_error_dist` + `slow_log_dist` + burst detection | 无跳过，按时间线逐层定位瓶颈跳 |
| status = 401/403/429 | **网关拦截路径** | 无 | C1-C6 全跳，直接看 CEP errorCode/error + sentinel-block-log |
| 四表全空 + request_time < 100ms | **fallback 路径** | `log_error_dist`（按 app+租户） | 只查 CEP errorCode/error 字段 + bizName→app 映射 |

**路径确定后，后续 Checklist 只需验证该路径要求的项，其余自动标记 N/A。**

### Checklist 分级

| 级别 | 适用场景 | 必验项 | 其余项处理 |
|------|---------|--------|-----------|
| **首轮路径** | NPE/ClassCast/NFE + request_time < 100ms | A1, B2, B4, C1；输出 `stop_reason` / `escalate_when` | D1/D2/D4 仅在 HND、质量门禁或用户要求时适用；其余自动标记 N/A，不逐项输出 |
| **扩展路径** | 慢请求 / 四表部分命中 / 需要判断是否深挖 | 全部 A/B/C/D 项 | 逐项确认 |
| **完整报告路径** | 继续深挖 / S1/S2 故障 / 多源关联 | 全部 A/B/C/D/E 项 | 逐项确认 + E 组门禁 |

### A. 输入归一化

- [ ] **A1 调用 extract_error_anchor**：**必须调用 `extract_error_anchor` / `parse_traceid`** 从截图或文本提取 `errorCode`、`service`、`timestamp`，不手动正则
- [ ] **A2 调用 resolve_tenant_cloud**：**必须调用 `resolve_tenant_cloud`** 从 errorCode 自动识别 source → 云环境映射，未识别时立刻停下
- [ ] **A3 截图时间提取**：截图场景必须读 `MM-dd HH:mm:ss` 字段，作为 `log_cep_dist` 收窄窗口的时间锚点；纯文本输入则用 "现在" 或用户指定时间
- [ ] **A4 服务名提取**（截图）：拿到 SFA / FLOW / UDOBJ 之类的缩写，作为 bizName→app 映射兜底输入
- [ ] **A5 多弹窗识别**：截图重叠时逐层识别；同码多弹窗当作 1 个错误码处理但保留所有时间戳

### B. 环境与租户锚定

- [ ] **B1 切换 ClickHouse profile**：根据 A2 的云环境结果切到对应 profile，**source≠0/1 时禁止用默认 foneshare profile 扫表**
- [ ] **B2 `log_cep_dist` 反查**：编排流下必须从 HND / `index.md` 锚点证据确认 `traceIdLookup.status=resolved` 后才能进入 B2。若 HND / 索引证据缺少 `traceIdLookup`，或状态为 `pending/ambiguous`，本 skill **立即中止 B 组，回抛主控**（`status=partial`、`need_further: reqId→traceId 反查`），由主控派 `fx-ops-query` 用 `has(reqId,'<code>')` 完成反查并回填 `resolved_traceId` 后再回到本 skill。

 **仅独立调用（无主控编排）时**，本 skill 才自行 `has(reqId,'<code>') ORDER BY status DESC, request_time DESC`（`reqId` 为 `Array(String)`，必须用 `has()`，禁止 `reqId =`）。**已 resolved 时**直接复用 `resolved_traceId`，不重复查 `log_cep_dist`。
- [ ] **B3 多命中消歧**：`log_cep_dist` 命中 >1 条且 traceId/ea 不唯一时，按"多命中消歧"小节收敛；首行 status<400 必须按空结果协议处理，不能直接当目标
- [ ] **B4 锁定单一报错行**：唯一确认 `traceId / rpcId / ea / ei / companyName / uri / status / request_time / errorCode / error`，落证据 `TRC-cep-target.json`
- [ ] **B5 提取 error 时间戳**：调用 `extract_error_anchor` / `parse_traceid` 解析 `error` 字段，自动提取 `errorCode`、`service`、`timestamp`。`extract_error_anchor` / `parse_traceid` 返回的时间戳已包含年份，直接作为后续查询的时间锚点。`error` 中的时间是错误发生时间，比 `stamp`（请求入口时间）更精确，后续并行查询优先用它 ±5min 作为窗口
- [ ] **B6 客户对象补全**（生产环境）：**调用 `resolve_tenant_cloud`** 查询 `AccountObj`，拿到客户级别（`UDSSel31__c`：`SVIP / VIP / 重要 / 标准 / 小微 / 其他`）、CSC（`field_o08uo__c`），喂给主控做 severity 修正

### C. 真实链路取证（四表 + 慢/超时增强）

- [ ] **C1 `log_error_dist`（按 traceId）**：高信号，命中即可拿堆栈与 token
- [ ] **C2 `fs_cep_slow_error_dist`（按 traceId）**：网关层是否慢
- [ ] **C3 `slow_log_dist` / `sql_slow_dist`（按 traceId）**：DB 层是否慢
- [ ] **C4 `tomcat_access_slow_dist`（按 trace_id 字段，注意 snake_case）**：应用层是否慢
- [ ] **C5 `app_log_dist` StopWatch 段**（仅当 request_time ≥ 5s 或主诉是慢/超时）：`positionCaseInsensitive(msg,'StopWatch')>0` + traceId 双过滤，**必须再加 app 过滤（取自 `CTX-app-discovery.json` 候选）与 `_time_second_` 时间窗**（窗口默认 ≤6h、最大 ≤24h；时间列固定 `_time_second_`，该表无 `stamp`）
- [ ] **C6 `biz_log_function_dist`**（同 C5 触发条件）：按 traceId 等值，识别 APL 自定义函数耗时是否主导
- [ ] **C7 数据包过大定量佐证**：若怀疑请求数据太大，必须基于 `log_cep_dist.request_length`、函数执行日志和 `tomcat_access_slow_dist` 做佐证和给出结论

### D. 升级与扩展

- [ ] **D1 `log_error_dist` 爆发判定**：补一条 `app + 租户 + token` 的 10 分钟聚合查询，命中爆发阈值才升级到"继续深挖"
- [ ] **D2 模块责任人补全（完整报告 / 责任归属场景）**：仅当 HND 要求报告、用户要求责任归属、或结论需要明确责任团队时调用负责人能力。首轮只输出已从 CEP / error 证据中直接得到的服务或 app。需要补全时，从 `server_ip` 提取服务名（或从堆栈/日志锁定问题模块），调用 `fx-ops-knowledge` 查 `object_xkBG2__c`（业务模块与相关负责人），按问题模块输出以下 5 个字段，缺失项标 `-`：
- **产品经理**：`field_ekZ9g__c`
- **开发（技术负责人）**：`field_Z4Hmn__c`
- **测试（QA 负责人）**：`field_15WPn__c`
- **体验设计师**：`field_designer__c`
- **产研第一责任人**：从客户对象 `AccountObj.field_CcZHz__c` 取（生产环境产研侧应急联系人）
- [ ] **D3 下游/资源/变更**（仅"继续深挖"）：依据异常 token 关键字进入对应下游 playbook，并行变更回溯（前后 30min）
- [ ] **D4 代码缺陷深挖（按 HND / 门禁触发）**：首轮可标注"代码异常强信号"；只有用户要求修复建议、HND 要求代码级根因，或 `QG-CODE-IN-REPORT` 被触发时，才调用 `code-search`。
- [ ] **D5 代码直接引用门禁**：对所有涉及的代码（源代码、APL 代码），**必须直接引用有问题的代码行及相关联的代码片段（而非全部内容），且引用内不得进行任何抽样摘要或简写**；对应的修复/优化建议也应是针对该片段重构后的完整代码。

### E. 输出门禁

- [ ] **E1 证据落盘**：本轮所有 SQL 结果都已写入 `evidence_dir`
- [ ] **E2 结论引用证据**：结论文段每条断言都引用 evidence 文件
- [ ] **E3 标准输出骨架**：当前判断 / 归一化上下文 / 下一步动作 / 阶段证据 / 结论门禁 五段齐全
- [ ] **E4 取证完成度自检**：症状归类、时间窗、直接证据、伴随特征、主伴区分、备选证伪、根因层级、后续动作 — 缺哪项明确写"未取证"，**禁止编造**

> 任一项未完成就直接下结论 = 反模式。首轮只输出结论、证据和未完成项；完整报告、S1/S2、用户要求审计场景才输出可见 Checklist 尾段。

## 触发条件

- 用户说"帮我排查这个报错"并附截图。
- 用户说"前端报了个 15-84f875"。
- 客服反馈某个用户操作失败，给了 reqId / 错误码。

## 关键认知

- 错误码 = `reqId`，**不是** traceId。`log_cep_dist` 用 `reqId` 数组字段记录，不能直接 `=`，必须用 `has(reqId, '...')`。
- `log_cep_dist` 的时间字段是 `stamp`，**不是** `_time_second_`。
- 一个 reqId 通常对应一个 traceId，但不绝对。
- 错误码短横线前的数字是 source ID，可直接映射云环境；需要完整映射或环境识别时，调用 `resolve_tenant_cloud` skill。
- `s311…` 等非标准旧码已逐步废弃：**禁止向用户解释该码含义或写码表释义**；只作截图/`reqId` 弱线索反查 traceId，结论仅来自时间、租户、服务、traceId、URI、status、`error`/`errorCode` 与堆栈。
- 如果错误码来自截图，**优先使用截图里的时间字段**收窄查询窗口，减少数据扫描量。
- **先分层再下结论**：看到异常不要直接定性，至少拆成三层：应用 Pod → 下游服务（DB/Mongo/外部服务）→ 查询本身。排除法逐层确认。
- **不要把公共短错误码当成影响范围**：短错误码可能跨企业复用；以 `traceId + 时间 + 租户 + URI + status` 锁定具体故障。
- **`bizName` 只存在于 CEP 两张表**（`log_cep_dist`、`fs_cep_slow_error_dist`），`log_error_dist`、`slow_log_dist` / `sql_slow_dist`、`tomcat_access_slow_dist` 等**没有 `bizName` 字段**。四表扫描只能靠 `traceId` 跨表关联，**不要在四表查询的 WHERE 中使用 `bizName`**。
- **对象操作命令优先级**：`idp object describe`（查对象元数据定义）→ `idp object query`（查对象数据）→ `idp query`（深层 SQL 分析）。能用前两者解决的问题不要直接用 `idp query` 裸 SQL 查 `mt_field`/`mt_describe` 等元数据表。
- `log_error_dist` 的 `token` 字段是异常类名，判断某一类错误是否在短时间内集中爆发时，优先按 `token` 聚合，而不是按 `msg` 或 `content` 聚合。

## 默认执行策略

CEP 错误诊断默认从首轮取证开始。首轮只锁定目标 CEP 行、执行信号预判、按路径查询最小表组，并通过 `stop_reason` / `escalate_when` 回抛主控判断是否继续：

1. 查 `biz-app-log` 数据源下的 `log_cep_dist` 表，锁定 `traceId`、租户、报错时间、`errorCode/error`、`uri/status/request_time`
2. **信号预判**：根据 S 节规则判断走哪条路径（快速失败 / 慢请求 / 网关拦截 / fallback）
3. 按路径要求**并行**查询对应表组（参见 S 节表格）。首轮不默认做 burst detection；只有需要判断爆发、HND / 质量门禁要求、或用户关心影响面时，才补 `app + 租户 + token` 10 分钟聚合
4. 优先根据高信号表直接给出首轮原因
5. 默认在这里停止，不主动展开 `app_log_dist`、`eye_trace_dist`、监控、配置、变更、下游专项排查

> `biz_log_function_dist` 只在 request_time ≥ 5s、主诉慢/超时、CEP/app_log/error 明确出现函数信号，或 HND / 质量门禁要求时补查。
> burst detection 不等错误日志结果后再补的规则只适用于影响面判断、HND 或质量门禁要求；首轮已有直接证据时回抛 `stop_reason`，由主控决定是否继续。

出现以下任一情况时，自动进入**继续深挖**：

- 用户明确要求“继续深挖”“完整排查”“继续查下游/配置/监控”
- `log_error_dist` 按 `app + 租户 + token` 聚合后，显示同类异常在短时间内爆发
- 四张高信号表信息不足，无法给出可交付结论

## 提取错误信息

**截图输入** — 从截图中提取：

| 字段 | 识别方式 | 示例 |
| --- | --- | --- |
| 错误代码 | 正则 `(\d{1,2})-([a-f0-9]{6})` 或 `([a-z]\d{6,})` | `1-611f8d`、`s311030002` |
| 服务 | "服务" / "Service" 标签后的缩写 | `SFA`、`FLOW` |
| 时间戳 | `MM-dd HH:mm:ss` 格式 | `05-15 14:13:13` |

> 如果截图分辨率低或文字模糊，用图像识别工具辅助提取。

**直接给错误码** — 用户直接提供错误码和（可选的）时间信息。

## 识别云环境

取错误代码中短横线前面的数字作为 source ID：

| source | type | 环境 |
| --- | --- | --- |
| 0, 1 | EI | 纷享-腾讯云（fxiaoke.com） |
| 4 | EI_KSY | 香港 AWS（hk.sharecrm.com） |
| 8 | EI_ALI | 阿里云（ale.fxiaoke.com） |
| 9 | EI_AWS | 法兰克福 AWS（eu.sharecrm.com） |

完整 source 映射与环境识别交给 `resolve_tenant_cloud` skill 处理。

> source ≠ 0/1 时，`biz-app-log` 的 `log_error_dist` 和 slow 表可能在独立 ClickHouse 实例；如果四表扫描返回全空，优先读 CEP 的 `errorCode`/`error` 字段；如需继续排查，需切换到对应环境的 ClickHouse profile。

## CEP 日志反查

用 `has(reqId, '<ERROR_CODE>')` 查 CEP 日志。时间窗口按以下优先级确定：

1. **错误消息中的时间戳**：CEP 的 `error` 字段常包含 `MM-dd HH:mm:ss` 格式时间（如 `05-22 16:12:16`），以此为中心 ±5 分钟起查
2. **截图中的时间戳**：`A3` 步骤提取的 `MM-dd HH:mm:ss`
3. **用户指定的时间**
4. **默认**：当前时间向前 1 小时

空结果按 ±5min → ±30min → ±1h → ±6h → ±24h 阶梯扩窗（权威声明见 fx-ops SKILL.md「扩窗阶梯权威声明」）；每次扩窗记录原因。

**排序必须是 `ORDER BY status DESC, request_time DESC`，不要用 `stamp DESC`**：错误码（特别是 6 位短 hex）会在不同请求的 reqId 数组里复用，按时间倒序极易把同码的 200 流量当成目标。按 `status DESC` 让 5xx/4xx 排到前面、`request_time DESC` 把同 status 中耗时最长的（最可能真出问题）排到前面，可以一步锁定真实报错行。

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT stamp, bizName, serverName, server_ip, ei, ea, companyName, traceId, rpcId,
     reqId, uri, status, request_time, request_length, errorCode, error
 FROM log_cep_dist
 WHERE has(reqId, '<ERROR_CODE>')
  AND stamp BETWEEN '<TIME_MINUS_5MIN>' AND '<TIME_PLUS_5MIN>'
 ORDER BY status DESC, request_time DESC LIMIT 20" -j
```

### 多命中消歧（公共短码场景）

当 `has(reqId, X)` 命中超过 1 条且 `uniq(traceId) > 1` 时，按以下顺序收敛到真实报错的那条 traceId：

1. **首选 status ≥ 400 的记录**：上面的 `ORDER BY status DESC` 已经保证它们排在前面；若首行 status < 400，说明该窗口内没有任何真实报错，按空结果协议处理（扩窗或回退到 errorCode 查询）
2. **同 status 内按 request_time DESC**：耗时长的更可能是真出问题的请求；若同样耗时极短（< 100ms）但 status=4xx/5xx，看 `errorCode/error` 字段是否非空
3. **`errorCode != '' OR error != ''` 兜底**：少数 200 状态但业务层抛错的情况，由 errorCode/error 字段识别
4. 多条 status≥400 候选时，按截图时间戳 ±2min 或用户给的租户线索（ea/companyName）二次过滤
5. 仍多于 1 条 → 列出候选清单（ea/uri/stamp/status）向用户确认目标

**绝不允许在多命中场景下"按 stamp DESC 取第一条"作为目标 traceId。**

**没有截图时间戳时**，按问题发生时间点附近 1 小时查询；如果问题就是当前时间，先算出起止字面量，再使用 `stamp BETWEEN '<TIME_MINUS_1HOUR>' AND '<TIME_PLUS_1HOUR>'`。不要默认查最近 2 小时。

时间窗口扩展规则：±5min → ±30min → ±1h → ±6h → ±24h → 停（数据可能过期）；统一扩窗阶梯见 fx-ops SKILL.md「扩窗阶梯权威声明」。

需要确认 `log_cep_dist` 字段定义时，调用 `fx-ops-query` skill 做单表字段校验。

从结果中提取：

| 关键信息 | 字段 |
| --- | --- |
| 租户 ID / 账号 / 企业名称 | `ei` / `ea` / `companyName` |
| traceId | `traceId` |
| 接口 / HTTP 状态码 | `uri` / `status` |
| 内部错误码 / 错误消息 | `errorCode` / `error` |
| 请求体大小 / 响应时间 | `request_length` / `request_time` |
| 服务端地址 | `server_ip` |

### server_ip → 服务名 + 负责人

CEP 日志的 `server_ip` 通常是 K8s 服务 DNS 格式：`<服务名>.<namespace>.lb-<hash>.tke70-k8s1.foneshare.cn:<port>`。

```bash
# 从 DNS 格式提取服务名和 namespace
echo "<server_ip>" | awk -F'.' '{print $1, $2}'
# 例：fs-flow.foneshare.lb-xxx → fs-flow foneshare
```

少数场景 server_ip 是 `IP:port` 格式，用 k8s API 反查：

```bash
curl -s "https://k8s-app.foneshare.cn/api/v1/tool/find-app-by-address?address=<IP:PORT>" | jq -r '.data | "\(.cluster) \(.namespace)/\(.name)"'
```

拿到服务名后，如需定位负责人，调用 `fx-ops` skill 的服务注册表能力查询模块负责人。

## traceId 首轮诊断（默认）

拿到 traceId 后，**并行查四张表**。`<ERROR_TIME>` 从 CEP 日志的 `stamp` 字段获取，默认查前后 5 分钟，空结果逐步扩大。

### 四表并行扫描

```bash
# log_error_dist：错误堆栈 + 程序位置（信号最强，优先看）
fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT _time_second_, app, pod, level, loggerName, token, traceId, rpcId, ei, ea, msg, error
 FROM log_error_dist
 WHERE traceId = '<TRACE_ID>'
  AND _time_second_ BETWEEN '<ERROR_TIME_MINUS_5MIN>' AND '<ERROR_TIME_PLUS_5MIN>'
 ORDER BY _time_second_ ASC LIMIT 10" -j

# CEP 慢请求（网关层慢）
fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT _time_second_, traceId, rpcId, reqUrl, status, errorCode, cost, tenantId, ea
 FROM fs_cep_slow_error_dist
 WHERE traceId = '<TRACE_ID>'
  AND _time_second_ BETWEEN '<ERROR_TIME_MINUS_5MIN>' AND '<ERROR_TIME_PLUS_5MIN>'
 ORDER BY _time_second_ DESC LIMIT 20" -j

# 慢 SQL（数据库层慢）
fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT _time_second_, app, ei, ea, traceId, rpcId, cost, dbName, substring(query, 1, 500) AS query
 FROM slow_log_dist
 WHERE traceId = '<TRACE_ID>'
  AND _time_second_ BETWEEN '<ERROR_TIME_MINUS_5MIN>' AND '<ERROR_TIME_PLUS_5MIN>'
 ORDER BY _time_second_ DESC LIMIT 20" -j

# Tomcat 慢接口（应用层慢）
fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT _time_second_, app, ei, ea, trace_id, uri, code, time_cost
 FROM tomcat_access_slow_dist
 WHERE trace_id = '<TRACE_ID>'
  AND _time_second_ BETWEEN '<ERROR_TIME_MINUS_5MIN>' AND '<ERROR_TIME_PLUS_5MIN>'
 ORDER BY _time_second_ DESC LIMIT 20" -j
```

> **所有 ClickHouse 查询必须带时间过滤**。`_time_second_` / `stamp` 使用显式时间字面量或 `BETWEEN '<T0>' AND '<T1>'`；禁止 `toDateTime(...) - INTERVAL` 与未展开的 `now() - INTERVAL` 作为 time_guard 主路径。
>
> **rpcId 精准过滤**：**traceId = 一次点击/开页**，其下常有多个 **rpcId（各一次 RPC）**；四表扫描勿把同操作下其他正常 RPC 当根因。若 `context_updates.traceIdLookup.resolved_rpcId` 已回传，有 `rpcId` 列的表（`log_error_dist`、`app_log_dist`、`slow_log_dist`、`eye_trace_dist`、`tomcat_access_slow_dist` 等）可 `AND rpcId = '<R>'` 精查。无 rpcId 列的表保持 traceId + 窄时间窗。多 rpcId 时结论必须写明选择与排除理由。rpcId 目标形态为字符串 ID（旧 `x.y.z` 层级逐步废弃）；语义与覆盖矩阵见 `fx-ops-query` → `reqId-traceId-rpcId.md`。
>
> **兼容旧合同**：如未提供 `resolved_rpcId`，仍按 `traceId + 窄时间窗` 查询并按 rpcId 分组判读即可，不视为错误或阻塞条件。

### 慢 / 超时场景必跑：`app_log_dist`（StopWatch）+ `biz_log_function_dist`

只要 `log_cep_dist` 命中行的 `request_time` 偏长（≥ 5s 经验阈值），或主诉就是"慢 / 超时 / latency 高"，必须并行追加这两张表，不要等四表收敛后再补：

```bash
# Spring StopWatch 分阶段耗时（只在 app_log_dist 中）
fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT _time_second_, app, pod, level, logger, rpcId, substring(msg, 1, 1500) AS msg
 FROM app_log_dist
 WHERE traceId = '<TRACE_ID>'
  AND positionCaseInsensitive(msg, 'StopWatch') > 0
  AND _time_second_ BETWEEN '<ERROR_TIME_MINUS_5MIN>' AND '<ERROR_TIME_PLUS_5MIN>'
 ORDER BY _time_second_ ASC LIMIT 50" -j

# APL 自定义函数执行（按 traceId 等值，不需要租户过滤）
fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT createTime, apiName, type, version, fail, cost, totalCost,
     bindingObjectApiName, substring(error, 1, 500) AS error
 FROM biz_log_function_dist
 WHERE traceId = '<TRACE_ID>'
  AND createTime BETWEEN '<ERROR_TIME_MINUS_5MIN>' AND '<ERROR_TIME_PLUS_5MIN>'
 ORDER BY createTime ASC LIMIT 50" -j
```

判读规则：
- StopWatch 中 `running time (millis) = N` + 各 task 占比，占比 ≥ 50% 的 task 是首要嫌疑
- `biz_log_function_dist` 命中即代表请求经过 APL Runtime；按 `cost` / `totalCost` 倒序找最慢函数
- `biz_log_function_dist` 累计 `cost` 占 cep `request_time` ≥ 30% → 根因高度可能在 APL 自定义函数（循环/N+1/穿透缓存），转 trace-end-to-end 的 Step 2 拉源码深挖
- 二者全空 + 四表也未命中慢点 → 慢点不在应用层，转下游依赖排查

### APL 函数排查（条件化）

**不要主动查 `mt_udef_function`**。`biz_log_function_dist` 是 APL 函数执行的专用日志表，数据量小、查询精准，优先用它判断是否有 APL 参与：

**Step 1：查 `biz_log_function_dist` 确认 APL 是否参与**

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT createTime, apiName, type, version, fail, cost, totalCost,
     bindingObjectApiName, substring(error, 1, 500) AS error
 FROM biz_log_function_dist
 WHERE traceId = '<TRACE_ID>'
  AND createTime BETWEEN '<ERROR_TIME_MINUS_5MIN>' AND '<ERROR_TIME_PLUS_5MIN>'
 ORDER BY createTime ASC LIMIT 50" -j
```
- 将查询结果写入 `evidence_dir/APL-execution.json`，格式：`{"meta":{"source":"cep-error-code","traceId":"<TRACE_ID>","time":"<ISO_TIMESTAMP>"},"data":<查询结果数组>}`

- **命中** → APL 函数参与了请求，从日志直接拿到 apiName、cost、error
- **未命中** → 确认"无 APL 参与"，跳过后续步骤

**Step 2：按需查函数定义（源码深挖）**

Step 1 命中且需要源码分析时，调用 `fx-ops-query` 的 idp-function 能力：

```bash
fx-ops idp --profile <profile> query paas --tenant-id <EI> --sql "
 SELECT api_name, function_name, binding_object_api_name, parameters, return_type, body, version, is_current
 FROM mt_udef_function
 WHERE tenant_id = '<EI>' AND api_name = '<API_NAME>'
  AND is_current = true" -j
```
- 将结果写入 `evidence_dir/APL-source.json`，格式：`{"meta":{"source":"cep-error-code","traceId":"<TRACE_ID>","time":"<ISO_TIMESTAMP>"},"data":{"apiName":"...","body":"...","version":"..."}}`

### `log_error_dist` 爆发判定（与四表并行发出）

burst detection 只在需要判断爆发、HND / 质量门禁要求、或用户关心影响面时执行；不要作为首轮默认动作。查询同 `app + 租户 + 时间窗口` 的聚合，判断某类异常是否集中爆发。

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT token,
     count(*) AS error_count,
     uniqExact(pod) AS pod_count,
     min(_time_second_) AS first_seen,
     max(_time_second_) AS last_seen
 FROM log_error_dist
 WHERE app = '<APP>'
  AND (ei = '<EI>' OR ea = '<EA>')
  AND _time_second_ BETWEEN '<ERROR_TIME_MINUS_10MIN>' AND '<ERROR_TIME_PLUS_10MIN>'
 GROUP BY token
 ORDER BY error_count DESC
 LIMIT 10" -j
```

满足以下任一条件，进入扩展取证或完整报告路径：

- 同 `app + 租户 + token` 在 10 分钟内 `error_count >= 10`
- 同一 `token` 涉及 `pod_count >= 3`
- 同 `app + 租户` 的 `log_error_dist` 总量 `>= 20`，且 Top1 `token` 占比 `>= 50%`

升级后，才继续做变更、监控、配置、下游依赖等完整排查。

快速判读：

| 表命中 | 说明 | 下一步 |
| --- | --- | --- |
| `log_error_dist` 命中 | 异常类型 + 程序位置 | 见下方错误日志消息解析 |
| `slow_log_dist` / `sql_slow_dist` 命中 + cost 高 | 慢 SQL | 调用 `fx-ops` skill 进入 SQL 下游排查 |
| `slow_log_dist` / `sql_slow_dist` 命中 + cost 不高但条数多 | 累积 SQL 慢 | 统计总 cost |
| `tomcat_access_slow_dist` 命中 + time_cost 高 | 应用层处理慢 | 看调用链，定位瓶颈 |
| `fs_cep_slow_error_dist` 命中 + cost 高 | 网关层慢 | 看下游哪个服务慢 |
| `log_error_dist` + `NPE`/`IOOBE`/`NFE` | 代码 Bug | 标注"代码异常强信号"；仅 HND 要求、用户要求修复建议或 `QG-CODE-IN-REPORT` 触发时调用 `code-search` |
| `log_error_dist` + `column .* does not exist` | 元数据/DB Schema 不同步 | 调用 `fx-ops` skill 进入字段缺失 / Schema 不同步排查 |
| 四张表都没命中 | 见 fallback | ↓ |

首轮只要已经能从 `log_error_dist`、`fs_cep_slow_error_dist`、`slow_log_dist` / `sql_slow_dist`、`tomcat_access_slow_dist` 给出明确原因，就输出结论、证据、`stop_reason` 与 `escalate_when`，不自行展开更多数据源。

### 四表全空 fallback

**快速失败（request_time < 100ms）**：检查 CEP 的 `errorCode`/`error` 字段，有明确描述可直接得出结论。

**用 bizName → app 映射查 `log_error_dist`**：bizName 只存在于 CEP 表，其他表只有 `app` 字段。映射表见 **fx-ops-knowledge** skill 的 `biz-name-mapping.md`，映射后用 `app + 租户 + 时间窗口` 查 `log_error_dist`：

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT _time_second_, app, pod, level, loggerName, token, traceId, rpcId, ei, ea, msg, error
 FROM log_error_dist
 WHERE app = '<映射后的 app 名>'
  AND (ei = '<EI>' OR ea = '<EA>')
  AND _time_second_ BETWEEN '<TIME_MINUS_5MIN>' AND '<TIME_PLUS_5MIN>'
 ORDER BY _time_second_ DESC LIMIT 20" -j
```

**检查下游依赖类型**：
- USEREXT、QIXIN → 大概率 MongoDB → 调用 `fx-ops` skill 进入 MongoDB 下游排查
- 涉及搜索/报表 → 可能 Elasticsearch → 调用 `fx-ops` skill 进入 Elasticsearch 下游排查

### 错误日志消息解析

从 `log_error_dist.msg` 中提取关键信息：

| 模式 | 提取内容 |
| --- | --- |
| `<N>ms <Service>.<method>(<args>)` | 耗时 + 调用的服务方法 + 参数 |
| `java.lang.<Exception>: <message>` | 异常类型 + 错误信息 |
| `### The error may involve <Mapper>.<method>` | MyBatis Mapper 方法 |
| `### SQL: <sql>` | 完整 SQL 语句 |
| `pg-metadata:<host>:<port>/<db>` | DB 连接信息 |
| `provider: dubbo://<ip>:<port>/<interface>` | Dubbo 接口 + Provider 地址 |
| `request url: <url>` | REST 调用目标 |
| `context:RequestContext(tenantId=<id>...)` | 请求上下文 |

### 首发异常判定规则

四表并行扫描返回多个异常时，按以下规则判断首发异常：
1. **时间序优先**：stamp / `_time_second_` 最早的异常为首发（**默认**；适配字符串形态 rpcId）
2. **调用深度（仅旧层级 rpcId）**：若 rpcId 仍是 `x.y.z`，前缀更浅者更可能首发（如 `1` 比 `1.2` 浅）；**字符串形态 rpcId 不适用此条**
3. **异常类型优先**：NPE / ClassCast / StackOverflow 等代码级异常优先于 Timeout / ConnectException 等运行时异常判定为首发

## 继续深挖（升级后执行）

以下步骤只在两种情况下进入：

- 用户明确要求“继续深挖”
- `log_error_dist` 按 `token` 聚合后确认同类异常在短时间内爆发

### 变更排查（大面积报错时优先检查）

大面积报错、多 bizName 同时异常时，优先排查是否有发布、配置变更或 K8s 事件（OOM、Pod 重启等）。以报错时间为中心，前后各 30 分钟；需要查变更记录时调用 `fx-ops` skill。

重点关注：
- 报错服务的模块名是否出现在发布记录中
- 发布结果是否为"发布失败"
- 配置变更中是否涉及报错服务的相关配置
- 变更人与报错服务负责人是否一致（需要时调用 `fx-ops` skill 查询服务负责人）

### 网关层拦截

同一 reqId 只对应一条 CEP 记录、查不到下游 trace 和 `log_error_dist` → 错误在网关层（鉴权、路由、限流）。

- 看 CEP 的 `status`（HTTP 状态码）、`errorCode`/`error` 字段。
- 看 sentinel-block-log 是否有限流记录。
- 常见原因：鉴权失败 / 限流 / 路由不存在 / 请求体过大。

### Pod 状态检查

从 `log_error_dist` 拿到 `pod` 后，查 Prometheus 确认 Pod 状态。以错误时刻为中心前后各 10 分钟，查 CPU、CPU throttling、内存、重启次数。如有异常（CPU 打满、heap 高、GC 频繁），转交给 `fx-ops` skill 做 Pod 资源排查。

### 下游服务检查

根据异常类型关键字，进入对应下游 playbook：

| 异常类型关键字 | 下游服务 | 进入 |
| --- | --- | --- |
| `INVOKE_ERROR`、`DubboRestException`、`timeout`、`CircuitBreaker`、`CallNotPermittedException` | Dubbo / REST | 调用 `fx-ops` skill 进入 Dubbo / REST 下游排查 |
| `PSQLException`、`ERROR: column .* does not exist` | 无（元数据/DDL 同步） | 调用 `fx-ops` skill 进入字段缺失 / Schema 不同步排查 |
| `PSQLException`（其他）、`SQLException`、`concurrent update`、`Connection is not available` | PostgreSQL / MySQL | 调用 `fx-ops` skill 进入 SQL 下游排查 |
| `MongoSocketReadTimeout` | MongoDB | 调用 `fx-ops` skill 进入 MongoDB 下游排查 |
| `Jedis`、`Lettuce`、`RedisConnectionException` | Redis | 调用 `fx-ops` skill 进入 Redis 下游排查 |
| `ElasticsearchStatusException`、`index_not_found_exception` | Elasticsearch | 调用 `fx-ops` skill 进入 Elasticsearch 下游排查 |
| `CHJDBCService`、`jdbc-support.query` | ClickHouse | 调用 `fx-ops` skill 进入 ClickHouse 下游排查 |
| `NPE`、`DuplicateKey`、`NumberFormatException` | 无 | 根因在应用代码，无需检查下游 |
| `resource_bundle`、`i18n`、`ResourceBundle`、`locale`、`LocalizedMessage`、`MissingResourceException` | 无（多语言数据问题） | **禁止使用 `code-search` 搜索多语言 key**；**禁止**建议补 properties 文件（properties 仅是遗留默认值）。**抛异常带 i18n key 是正确架构**，不是代码缺陷。词条可能在两个库下，**都要查**：（1）`paas-i18n` 系统库 `i18n_entry`（查 `tenant_id = 0` 与租户自己）；（2）`paas` 租户业务库 `i18n_entry`（查租户自己）。排查重点是"为什么报错"而非"key 是否缺失"。详见 `fx-ops-metadata` 的 i18n-multilingual 模块 |

## 已知系统级故障点

| 故障点 | 模式 | 影响范围 |
| --- | --- | --- |
| `fs-paas-license` | 超时 / CircuitBreaker OPEN | NCRM、CRM-SFA、OPEN 等多个 bizName |
| `fsdb052071005` | DB 连接池耗尽 `Connection is not available` | CRM-MAKER、CRM-SFA-O2C 批量操作 |
| `fs-paas-auth-provider` | 慢响应（5s+）/ SQL 查询异常 | CRM-UDOBJ、CRM-FLOW layout/权限操作 |
| `fs-feeds-next-provider` | Dubbo 调用超时 | CRM-FEED、FEED |
| `fs-crm-fmcg-service` | 超时 / s311030117 / 1-272bcd | TPM 费用核销明细加载等 APL 函数 N+1 慢查询耗时超 20s 强杀，网关 15s 提前断连。 |

## 输出格式

默认分两段输出：**报错信息摘要** + **首轮诊断结论**。只有进入继续深挖后，才追加深挖结论或待验证项。

### 报错详细信息

```
⚠️ 已为您找到报错详细信息

所属应用：<namespace>/<app>
报错时间：<timestamp>
报错企业：<companyName>（<ei>, <ea>）
云环境：<type>（<domain>）

接口 URL：> <uri>
接口耗时：<request_time>ms | HTTP 状态：<status>

链路追踪：TraceId=<traceId> | ReqId=<reqId> | Pod=<pod> (<serverIp>)

责任分工（完整报告 / 责任归属场景，按问题模块查 object_xkBG2__c）：
 产品经理：<field_ekZ9g__c>
 开发（技术负责人）：<field_Z4Hmn__c>
 测试（QA 负责人）：<field_15WPn__c>
 体验设计师：<field_designer__c>
 产研第一责任人：<AccountObj.field_CcZHz__c>
```

> 首轮不输出完整责任分工；只有 HND 要求报告或责任归属时，才从 server_ip 提取服务名（或按堆栈定位模块），调用 `fx-ops-knowledge` 查 `object_xkBG2__c` 拿到上面 4 项；产研第一责任人从客户对象 `AccountObj.field_CcZHz__c` 取。缺失项填 `-`，不要省略整行。

### 首轮诊断结论

```
🔍 首轮诊断

错误堆栈：
<异常类型>: <异常 message>
 at <关键堆栈行>

高信号日志：log_error_dist <命中|未命中> | fs_cep_slow_error_dist <命中|未命中> | slow_log_dist <命中|未命中> | tomcat_access_slow_dist <命中|未命中>
结论：<故障层> / <故障因> — <一句话描述>
置信度：<高|中|低>
建议：<下一步行动>
```

**根因类型**使用两层分类：`故障层 / 故障因`。需要对齐根因分类体系时，委托 `fx-ops-knowledge` 的根因分类能力，由该 skill 自行选择内部参考文档。

输出时注意:
- 首轮只输出已从 CEP / error 证据中直接得到的服务或 app；完整责任分工只在 HND 要求报告或责任归属时补齐。
- 堆栈只贴关键行（异常类型 + message + 2-3 行调用栈），不要贴完整堆栈。
- 基础设施正常时一句话带过，异常时附具体数值。
- 不要堆原始 JSON 日志，用户看的是结论不是原始数据。
- 首轮优先说明“为什么当前证据支持该结论”，不要顺手展开完整端到端故事线。
- 只有进入继续深挖后，才追加监控、配置、变更、下游专项验证结果。

## 反模式

### 致命（必须避免，会导致排查方向错误）

- ❌ 用 `traceId = '1-a927cb'` 查 — 错误码不是 traceId。
- ❌ 用 `reqId = '<errorCode>'` 查 — `reqId` 是数组，必须用 `has()`。
- ❌ 多命中场景下直接取首行（不区分 status）作为目标 traceId — 见"多命中消歧"小节。
- ❌ 用 `_time_second_` 过滤 `log_cep_dist` — 它的时间字段是 `stamp`。
- ❌ 忽略 CEP 的 `errorCode`/`error` 字段 — 快速失败场景可直接得出结论。
- ❌ 拿到 traceId 后还在 `log_cep_dist` 反复查，不切到 `log_error_dist` 等高信号表。

### 风格（建议避免，会影响排查效率）

- ❌ 慢 / 超时场景不查 `biz_log_function_dist` — 大量慢请求根因是 APL 自定义函数执行慢或循环 N+1，必须按 traceId 同步排查。
- ❌ 用 `app_log_dist` 判断 APL 是否参与 — 直接查 `biz_log_function_dist` 更精准。
- ❌ 慢 SQL 单条 cost 不高就跳过 — 多条中等速度 SQL 累积也会导致超时。
- ❌ 证据攒到最后一次性落盘 — 每步查询结果必须即时保存到 evidence_dir，防止上下文压缩后丢失。
- ❌ 快速失败场景仍跑完全部五路并行 — 根据 S 节信号预判跳过无价值的慢查询表。
- ❌ 首轮追求完整故事线 — 首轮不以"完整"为目标，以"直接证据是否足够解释当前失败"和 HND `stop_when` 为停止条件。

## 与其他 Playbook 的关系

本 playbook 是**CEP 场景的顶层编排**，默认先做首轮诊断，必要时按 HND / 质量门禁继续深挖：

- 四表全空且 CEP 自身字段不足 → trace-end-to-end.md
- `slow_log_dist` / `sql_slow_dist` 命中 → 调用 `fx-ops` skill 进入 SQL 下游排查
- Pod 资源异常 → 调用 `fx-ops` skill 进入 Pod 资源排查
- 下游分发 → 调用 `fx-ops` skill，让它选择对应的 downstream 场景
