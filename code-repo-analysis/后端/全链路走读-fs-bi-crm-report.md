# fs-bi-crm-report 全链路走读手册（10 条主链路）

> 用法：每一条链路都从「API 接口文件 → 方法 → 服务 → 数据层/RPC」完整串联。你只需要按顺序打开文件、找到方法，一行行看。
> 仓库根：`/Users/muqingji/code/serve/fs-bi-crm-report`；主代码模块是 `fs-bi-crm-report-web/src/main/java/com/facishare/bi/`，下文路径都省略这个前缀。
> 行号为当前代码实际行号，找不到就按类名/方法名搜索。
> **跨服务跳转指引**：crm-report 是「门户/编排层」，自己不直接查 ClickHouse，而是把请求转发给下游三个报表计算服务（udf-report / dev-platform / fs-bi）。凡标注「跨服务」的地方，请跳到对应仓库的全链路文档继续走：
> - 调 udf-report → 看《全链路走读-fs-bi-udf-report.md》
> - 调 dev-platform → 看《全链路走读-fs-bi-dev-platform.md》
> - 调 fs-bi → 看《全链路走读-fs-bi.md》
> - 发 MQ 给 warehouse → 看《[全链路走读-fs-bi-warehouse.md](../大数据/全链路走读-fs-bi-warehouse.md)》（DWSViewChangeConsumer 链路）

---

## 链路速览表（先看这个：10 秒知道每个链路是干啥的）

| 链路 | 一句话说明（大白话） |
| --- | --- |
| 1 报表数据查询 | 门户打开分组报表：本地查报表定义，转发 udf-report 查数据 |
| 2 统计图数据查询 | 门户打开统计图：转发 fs-bi 查数据 |
| 3 大宽表查询 | 门户打开拼表（多张表拼成一张大表）：转发 dev-platform |
| 4 交叉表查询 | 门户打开透视表（行列都有维度）：转发 udf-report |
| 5 订阅定时触发 | 订阅任务触发：查订阅配置 → 按类型跑数据 → 存结果 → 推送邮件/企信 |
| 6 统计图保存→通知 warehouse | 保存统计图：存配置到 PG，发 MQ 让 warehouse 预建 ClickHouse 表 |
| 7 操作权限查询 | 判断「当前用户对这个图表能干什么」（查看/编辑/分享） |
| 8 报表权限查询 | 查「哪些人有权限看这个报表」（可见人列表） |
| 9 驾驶舱导出 | 把驾驶舱（一屏多图）导出成 Excel/CSV 文件 |
| 10 后台订阅数据导出 | 把订阅任务已存好的结果文件导出成 Excel（后台/运维用） |

---

## 链路 1：报表数据查询（核心链路，转发 udf-report）

> **这条链路是干什么的（大白话）**：**场景**：用户在门户打开一张「分组报表」并查询。**它做的事**：crm-report 相当于「前台接待」：①本地 PG 查报表定义（这张表有哪些字段/筛选器）②查筛选器默认值（转发 udf-report）③把查询请求转发给真正的计算服务 udf-report。**为什么这样设计**：crm-report 不碰数据计算，只做编排和转发，让 udf-report 专注算数。


**API 文件**：`portal/api/ViewDataQueryApiController.java`
**接口方法**：`POST /api/v1/view/data/query` → `query()`（第 35 行）

```
ViewDataQueryApiController.query()
  → ViewDataQueryFacadeService.query()（portal/service/ViewDataQueryFacadeService.java，第 95 行）
      ├─ 1. 写链路追踪上下文：TraceContext 设置 ei/ea/employeeId/uid
      ├─ 2. 查报表定义：viewQueryRepository.getRptView(userInfo, viewId)
      │     → ViewQueryRepository.getRptView()（portal/repository/ViewQueryRepository.java，第 40 行）
      │         → rptViewRepository.getViewByID(viewId, ei)
      │             → RptViewRepository.getViewByID()（repository/RptViewRepository.java，第 398 行）
      │                 → rptViewMapper.getViewByID(id, ei)（dao/mapper/RptViewMapper.java，第 149 行）
      │                     → PostgreSQL（本地元数据库 rpt_view 表；多租户走 rptViewMapperTenant 带 schema）
      ├─ 3. 判断报表类型：rptType 必须是 RPT（分组表），否则抛异常
      ├─ 4. 绑定筛选器：bindRptFilterLists()
      │     → viewQueryRepository.getRptFiltersResult() → biudfResource.getRptFilterResult()
      │         → 跨服务 HTTP → udf-report /rptUdfViewEditController/getFiltersResult（见 udf-report 链路 8）
      ├─ 5. 组装 QueryReportDataArg（viewId + filterList + 分页 + 显示模式）
      ├─ 6. 真正查数据：viewDataQueryRepository.queryReportData(userInfo, arg)
      │     → ViewDataQueryRepository.queryReportData()（portal/repository/ViewDataQueryRepository.java，第 51 行）
      │         → biudfResource.queryReportData(arg, headerMap)
      │             → 跨服务 HTTP（@RestResource("BI-UDF-REPORT")，portal/rpc/BIUDFResource.java 第 40 行）
      │                 → udf-report POST /rptUdfViewDataController/queryReportData（见 udf-report 链路 2）
      └─ 7. 结果转换：viewDataBeanMapper.toDataSet / toPage / viewDisplayFieldBeanMapper.toDisplayFields
```

**底层落点**：本地 PostgreSQL（报表定义表）+ 跨服务 HTTP RPC → udf-report（最终查 ClickHouse）。

**新手要点**：这条链路是「查报表」的标准姿势：先查定义（本地库）→ 再查数据（转发下游）。重点看第 2 步和第 6 步，一个落本地 PG、一个打远程 HTTP。

---

## 链路 2：统计图数据查询（核心链路，转发 fs-bi）

> **这条链路是干什么的（大白话）**：**场景**：用户在门户打开一张统计图（柱状图/折线图）并查询。**它做的事**：和链路 1 一样的「接待」模式，只是目标换成统计图：本地 PG 查统计图定义（stat_view），转发 fs-bi 查数据和筛选器。**对比链路 1**：报表转发给 udf-report，统计图转发给 fs-bi，两个下游各管一类。


**API 文件**：`portal/api/ViewDataQueryApiController.java`
**接口方法**：`POST /api/v1/view/data/query` → `query()`（第 35 行，走统计图分支）

```
ViewDataQueryApiController.query()
  → ViewDataQueryFacadeService.query()（第 95 行）
      ├─ getRptView() 返回 null（viewId 不是报表，是统计图）
      └─ queryViewData(userInfo, arg)（ViewDataQueryFacadeService.java，第 418 行）
          ├─ 1. 查统计图定义：viewQueryRepository.getStatView()
          │     → ViewQueryRepository.getStatView()（第 49 行）
          │         → statViewRepository.getViewByID(viewId, ei)
          │             → StatViewMapper → PostgreSQL（stat_view 表）
          ├─ 2. 绑定统计图筛选器：bindStatFilterLists()
          │     → viewQueryRepository.getStatFiltersResult()
          │         → fsbiResource.queryFiltersResult()（跨服务 HTTP → fs-bi /stat/filters/getFiltersResult）
          ├─ 3. 组装 QueryChartDataArg（viewId + filterList + 图表参数）
          ├─ 4. 查数据：viewDataQueryRepository.queryChartData(chartDataArg, userInfo)
          │     → ViewDataQueryRepository.queryChartData()（第 56 行）
          │         → fsbiResource.queryChartData(...)（跨服务 HTTP → fs-bi POST /stat/data/query，见 fs-bi 链路 4）
          └─ 5. 结果转换 → ViewDataQueryResult（displayFields + dataSet）
```

**底层落点**：本地 PostgreSQL（统计图定义表）+ 跨服务 HTTP RPC → fs-bi（最终查 ClickHouse）。

**新手要点**：和链路 1 结构一模一样，只是「定义表」换成 stat_view、「数据服务」换成 fs-bi。对比着看能很快理解 crm-report 的转发职责。

---

## 链路 3：大宽表（LWT）查询（转发 dev-platform）

> **这条链路是干什么的（大白话）**：**场景**：用户打开「拼表」（大宽表）类型的报表，比如把《客户表》《订单表》《销售表》拼成一张大表看。**它做的事**：crm-report 只做参数翻译，把查询转发给 dev-platform（HTTP `/lwt/query`），由 dev-platform 负责真正拼表查询。**注意**：拼表的筛选器配置也是转发 dev-platform 查的。


**API 文件**：`portal/api/ViewDataQueryApiController.java`
**接口方法**：`POST /api/v1/view/data/queryLwtViewData` → `queryLwtViewData()`（第 42 行）

```
ViewDataQueryApiController.queryLwtViewData()
  → ViewDataQueryFacadeService.queryLwtViewData()（第 338 行）
      ├─ 1. 查宽表配置：viewQueryRepository.getLwtFiltersResult()（跨服务 → dev-platform /lwt/getFiltersResult）
      ├─ 2. 组装 QueryLwtArg（viewId + filterList + 分页）
      ├─ 3. 查数据：viewDataQueryRepository.queryLwtData(lwtArg, userInfo)
      │     → ViewDataQueryRepository.queryLwtData()（第 60 行）
      │         → bidevResource.queryLwtData(...)（跨服务 HTTP @RestResource("BI-DEV-PLATFORM")，
      │             portal/rpc/BIDEVResource.java 第 37 行 → dev-platform POST /lwt/query，见 dev-platform 链路 1）
      └─ 4. 结果转换 → LwtQueryResult（dataset + totalCount + columns）
```

**底层落点**：本地 PostgreSQL（宽表配置）+ 跨服务 HTTP RPC → dev-platform（最终查 PG/ClickHouse）。

**新手要点**：LWT = Large Wide Table（大宽表），是「把很多张表拼成一张大表」的报表类型。crm-report 只做参数翻译和转发。

---

## 链路 4：交叉表（透视表）查询（转发 udf-report）

> **这条链路是干什么的（大白话）**：**场景**：用户打开交叉表（透视表）——行是维度、列也是维度、中间是数值，比如「产品×月份×销售额」。**它做的事**：和链路 1 类似，把查询参数转发给 udf-report 的交叉表接口（`/queryPivotReportData`），由它做行列转置的计算。


**API 文件**：`portal/api/ViewDataQueryApiController.java`
**接口方法**：`POST /api/v1/view/data/queryPivotReportData` → `queryPivotReportData()`（第 49 行）

```
ViewDataQueryApiController.queryPivotReportData()
  → ViewDataQueryFacadeService.queryPivotReportData()（第 238 行）
      ├─ 1. 查报表定义（同链路 1 的 getRptView → PostgreSQL）
      ├─ 2. 绑定筛选器（同链路 1）
      ├─ 3. 组装 QueryPivotDataArg（行列维度 + 指标 + 筛选）
      ├─ 4. 查数据：viewDataQueryRepository.queryPivotData(userInfo, arg)
      │     → ViewDataQueryRepository.queryPivotData()（第 101 行）
      │         → biudfResource.queryPivotData(...)（跨服务 HTTP → udf-report POST /rptUdfViewDataController/queryPivotReportData，见 udf-report 链路 3）
      └─ 5. 结果转换 → PivotViewDataQueryResult
```

**底层落点**：本地 PostgreSQL + 跨服务 HTTP RPC → udf-report（交叉表 SQL 引擎）。

**新手要点**：交叉表 = 行列都有维度的透视报表，比分组表多「列维度」概念。链路本身与链路 1 几乎一致。

---

## 链路 5：订阅定时触发（报表/统计图/驾驶舱统一触发）

> **这条链路是干什么的（大白话）**：**场景**：订阅定时触发——每天早上定时把报表/统计图/驾驶舱数据算好发给订阅人。**它做的事**：①查订阅配置（sch_run 表，PG）②按订阅类型分派：报表→转发 udf-report 查数据并上传文件、统计图→转发 fs-bi、驾驶舱→专门线程 ③存运行快照（sch_run_storage，PG）④把结果文件推送给订阅人（邮件/企信）。


**API 文件**：`portal/api/SubscriptionController.java`
**接口方法**：`POST /schedule/single/trigger/{schId}/{ei}` → `runSingleSch()`（第 97 行）

```
SubscriptionController.runSingleSch()
  ├─ 1. 从 Spring 容器取一堆 Bean：SchRunService / SchRunStorageService / ReportService / ScanAndSendJobService / RptViewService / StatChartViewDataService / StatViewService
  ├─ 2. 查订阅任务：schRunService.getTriggerSchRunBySchId(ei, schId)
  │     → SchRunService.getTriggerSchRunBySchId()（service/SchRunService.java，第 577 行）
  │         → schRunRepository.getTriggerSchRunBySchId(ei, schId)（repository/SchRunRepository.java，第 246 行）
  │             → schRunMapper.getTriggerSchRunBySchId(schId)（多租户走 schRunMapperTenant）
  │                 → PostgreSQL（sch_run 订阅任务表）
  ├─ 3. 按 schType 分派执行线程：
  │     ├─ schType 1/3/4（报表）→ SchRunScanThread.run()
  │     │     → viewDataQueryRepository.innerUdfQueryReportDataAndUploadByPage()（第 758 行调用）
  │     │         → 跨服务 HTTP → udf-report POST /rptUdfViewDataController/innerUdfQueryReportDataAndUploadByPage（见 udf-report 链路 5）
  │     ├─ schType 2（统计图）→ SchRunScanChartThread.run()
  │     │     → 跨服务 HTTP → fs-bi /stat/data/queryAndUploadByPage
  │     └─ schType 5（驾驶舱）→ SchRunScanDashBoardThread.run()
  ├─ 4. 写运行快照：schRunStorageService.getSchRunStorageBySchId(schId, start, now, ei)
  │     → SchRunStorageService → SchRunStorageRepository → PostgreSQL（sch_run_storage 表）
  ├─ 5. 立即发送：ScanAndSendJobService.addSchRunStorage()（上传文件到文件服务器）
  │     → 邮件/企信推送（SendMailTestService / SendQiXinMessageService / QixinService）
  └─ 返回 ApiResult<String>（触发结果）
```

**底层落点**：PostgreSQL（sch_run / sch_run_storage）+ 跨服务 HTTP → udf-report/fs-bi + 文件服务器 + 邮件/企信。

**新手要点**：订阅 = 定时任务。入口只负责「查出订阅配置 → 分类型跑数据生成 → 存储结果 → 推送」。重点跟第 3 步，看不同 schType 走不同线程。

---

## 链路 6：统计图保存/变更 → 发 MQ 通知 warehouse（跨仓库联动）

> **这条链路是干什么的（大白话）**：**场景**：用户在 BI 门户保存/编辑了一个统计图（改了个字段、加了个筛选）。**它做的事**：crm-report 先把统计图配置存到本地 PG（stat_view 等表），然后发一条 RocketMQ 消息（topic `bi-warehouse-event`、tag `dws_view_event`）告诉 warehouse：「这个图配置变了，帮我在 ClickHouse 里预建好聚合表」。**关键**：发消息是异步的，warehouse 收到后再建表（见 warehouse 链路 4）。


**API 文件**：`stat/api/controller/StatCreateController.java`（FCP 内部 RPC 接口，`@FcpService("statCreateController")`）
**接口方法**：`createStatView` → 实现类 `stat/api/impl/StatCreateControllerImpl.createStatView()`

```
StatCreateController.createStatView（FCP 远程调用入口）
  → StatCreateControllerImpl.createStatView()
  → StatViewService.createStatViewResult(arg)（stat/service/StatViewService.java）
      ├─ 1. prepareCreateStatViewArg() 校验参数
      ├─ 2. 查主题对象/字段：statViewRepository / statFieldTenantMapper → PostgreSQL
      ├─ 3. 生成新视图 ID：newViewId = IdGenUtils 生成
      ├─ 4. 保存 stat_view 定义：statViewRepository.createStatView(...) → PostgreSQL
      ├─ 5. 保存字段映射 stat_view_field：statViewFieldRepository → PostgreSQL
      ├─ 6. 灰度开关判断：useChAggGray(ei) 命中后
      │     → warehouseEventProducer.sendMessage(String.valueOf(ei), newViewId)（第 542 行）
      │         → WarehouseEventProducer.sendMessage()（service/WarehouseEventProducer.java，第 44 行）
      │             ├─ 消息体 AsyncWarehouseEventMsg{tenantId, sourceId, sourceType=0}
      │             ├─ TOPIC = "bi-warehouse-event"，TAG = "dws_view_event"
      │             ├─ delayTimeLevel = 2（延迟消费）
      │             └─ producer.send(msg)（RocketMQ AutoConfMQProducer）
      └─ 7. 返回 CreateStatViewResult{viewID, status}
```

**跨服务落点（必看）**：warehouse 端消费这条消息：
```
RocketMQ bi-warehouse-event / dws_view_event
  → warehouse DWSViewChangeConsumer.consumeMessage()（warehouse-dws/.../mq/consumer/DWSViewChangeConsumer.java，第 55 行）
      ├─ 解析 ViewChangeMessage{tenantId, sourceId, sourceType}
      ├─ 灰度/租户状态校验（userCenterService.isValidateStatus）
      ├─ tag 判断：case "dws_view_event" → clickHouseService.checkAndAddChRouter(tenantId)
      │     → 有 sourceId：statTopologyService.doCreateTopology(tenantId, sourceId, sourceType, Prepared)   ← 创建/更新该统计图的 CH 拓扑表
      │     → 无 sourceId：statTopologyService.batchCreateTopologyByEi(tenantId, ...)                      ← 重建整个租户拓扑
      └─ 后续由 DWSComputeConsumer 消费计算事件执行聚合（见 warehouse 链路 4）
```

**底层落点**：PostgreSQL（stat_view 定义）+ RocketMQ（bi-warehouse-event）→ warehouse 创建 ClickHouse 拓扑表。

**新手要点**：这是「保存统计图 → 异步让 warehouse 预建 ClickHouse 表并计算」的典型事件驱动链路。注意 crm-report 只发消息，真正建表/算数在 warehouse。StatViewService 里还有多处 sendMessage：第 1125 行（编辑）、第 1201 行（批量变更）、第 2339/2397 行（启用/停用视图）；RptViewService 第 972 行（报表批量变更，sourceType=3）；DashBoardLinkageService 第 185 行（驾驶舱联动）。

---

## 链路 7：操作权限查询（图表/报表权限校验）

> **这条链路是干什么的（大白话）**：**场景**：前端页面加载一个图表时，要判断「当前登录用户能不能看/能不能编辑/能不能分享这个图」。**它做的事**：查本地 PG 的图表权限表（chart_permission），拿到该图表的权限配置，再和用户的基础权限合并，计算出用户对这个图的具体操作权限返回前端。


**API 文件**：`api/rest/PermissionRestController.java`
**接口方法**：`POST /bi/perm/getNewOpPermission` → `getNewOpPermission()`（第 55 行）

```
PermissionRestController.getNewOpPermission()
  ├─ ContextUtils.setContextInfo(ei, null, userId)  写入线程上下文
  ├─ 1. 基础权限：permissionUtil.getFullPermission()（util/PermissionUtil.java）→ 拿用户全量功能权限
  ├─ 2. 图表权限：chartPermissionRepository.getChartPermission(String.valueOf(ei), viewId)
  │     → ChartPermissionRepository.getChartPermission()（repository/ChartPermissionRepository.java，第 34 行）
  │         ├─ 灰度 isReadSys：chartPermissionMapper.getChartPermission(tenantId, viewId)
  │         └─ 默认：chartPermissionMapperTenant.setTenantId(tenantId).getChartPermission(...)
  │             → MyBatis Mapper → PostgreSQL（chart_permission 图表权限表）
  ├─ 3. 计算操作权限：permissionUtil.getMyOpPermission(chartPermission, false) + getOpPermission(...)
  └─ 返回 Permission（可执行的操作集合：查看/编辑/分享/删除...）
```

**底层落点**：PostgreSQL（chart_permission 表）。

**新手要点**：权限 = 「用户能对这个图表干什么」。第 2 步查数据库里的权限配置，第 3 步和用户基础权限合并。旁边还有 `/bi/perm/setViewAccessPerm`（第 91 行）→ `PermissionService.setViewAccessPerm()`（permission/PermissionService.java，Dubbo 写权限）。

---

## 链路 8：报表权限查询（谁有权限看这个报表）

> **这条链路是干什么的（大白话）**：**场景**：报表的「权限设置」页，要显示这个报表有哪些可见人/负责人。**它做的事**：查报表的授权信息（谁有权限看这张报表），返回人员清单（UserOwner 列表）。**和链路 7 的区别**：链路 7 问「我能干什么」，链路 8 问「谁能看这张报表」。


**API 文件**：`api/rest/ReportRestController.java`
**接口方法**：`POST /bi/report/getReportPermission` → `getReportPermission()`（第 38 行）

```
ReportRestController.getReportPermission()
  ├─ ContextUtils.setContextInfo(ei, ea, userId)
  └─ reportPermissionReadFacade.getReportPermission(viewId)
      → ReportPermissionReadFacade.getReportPermission()（api/rest/ReportPermissionReadFacade.java，第 21 行）
          ├─ 查询报表授权人/可见人列表（rpt_view 相关权限字段）
          └─ → MyBatis Mapper → PostgreSQL（rpt_view / 权限关联表）
      → 返回 List<UserOwner>（报表可见用户/负责人清单）
```

**底层落点**：PostgreSQL（报表表 + 权限关联）。

**新手要点**：这是「报表的可见人员列表」查询，和链路 7 的区别：链路 7 是「我能干什么」，链路 8 是「谁可以看」。同一个 Controller 还有 `/bi/report/sendPoint`（第 47 行）→ `rptViewService.sendUdfReportPoint()`（埋点上报）和 `/sendAuditLog`（审计日志）。

---

## 链路 9：驾驶舱导出（Excel/CSV）

> **这条链路是干什么的（大白话）**：**场景**：用户把驾驶舱（一屏多个图表的看板）导出成 Excel/CSV 文件。**它做的事**：把驾驶舱的每个图表数据都查出来（内部复用统计图查询→fs-bi），拼成一个 Excel 文件上传文件服务器，返回文件地址，用户下载。


**API 文件**：`api/rest/DashBoardRestController.java`
**接口方法**：`POST /bi/dashboard/getDashBoardExcelDateInfo` → `getDashBoardExcelDateInfo()`（第 37 行）

```
DashBoardRestController.getDashBoardExcelDateInfo()
  ├─ ContextUtils.setContextInfo(ei, ea, userId, outEI, outUserId, appId)
  └─ scanAndSendJobService.getDashBoardExcelDateInfo(viewId, receiverId)
      → ScanAndSendJobService.getDashBoardExcelDateInfo()（service/ScanAndSendJobService.java，第 1052 行）
          ├─ creatExportDashboardArg(viewId, null, receiverId)  组装驾驶舱导出参数
          ├─ dashBoardExportService.exportDashBoardData(arg, receiverId)
          │     → 驾驶舱内各图表查询（内部复用统计图查询链路 → fs-bi）
          │     → 生成 Excel 文件 → 上传文件服务器 → 返回文件 URL
          └─ 组装 PushFile{filePath, fileSize, fileType}
```

**底层落点**：文件服务器 + 跨服务查询 fs-bi（驾驶舱内图表数据）。

**新手要点**：驾驶舱 = 多个图表拼在一起的大屏。导出时先把每个图表数据查出来，再拼成一个 Excel 文件。旁边 `getDashBoardCsvDateInfo()`（第 1068 行）是 CSV 版。

---

## 链路 10：后台订阅数据导出（从运行快照文件导出 Excel）

> **这条链路是干什么的（大白话）**：**场景**：后台/运维把订阅任务已经跑好、存在文件服务器的结果快照，导出成 Excel 供下载。**它做的事**：Controller 只负责收请求，通过 EventBus 事件机制交给 BackstageReporter 真正干活：查后台查询记录 → 读订阅结果文件 → 转 Excel → 上传文件服务器 → 回写任务状态。


**API 文件**：`backstage/controller/impl/BackendQueryExportJobController.java`
**接口方法**：`POST /bi/backstageExport/exportBackstageQueryDataFromStorage` → `exportSchRunStorage()`（第 71 行）

```
BackendQueryExportJobController.exportSchRunStorage()
  └─ BackstageExportExecutionEventBus.post(BackstageExportExecutionEvent.builder()
          .exportType(XLSX).exportSchRunStorageArg(arg).build())
      → BackstageExportExecutionEventBus.post()（backstage/event/BackstageExportExecutionEventBus.java，第 15 行）
          → ExecutionEventBusFactory.getInstance("backstage_report_export").post(event)（Guava EventBus）
              → BackstageReporter.execution(event)（backstage/export/BackstageReporter.java，@Subscribe，第 67 行）
                  ├─ 1. iBiReportHelper.generateMockFcpContext(...) 伪造登录上下文
                  ├─ 2. backendQueryViewService.queryViewBackstageQueryInfoById(arg.getId())
                  │     → BackendQueryViewService → MyBatis → PostgreSQL（后台查询记录）
                  ├─ 3. getExportReportResult(arg, result, doneResult, info)
                  │     → 按报表类型读取订阅运行快照文件（SchRunStorage 存的数据文件）
                  │     → 导出 XLSX → 上传文件服务器
                  └─ 4. doJobDoneCallback(doneResult, result) 回写任务结果
```

**底层落点**：PostgreSQL（后台查询记录）+ 文件服务器（订阅快照文件）+ 文件导出。

**新手要点**：订阅任务（链路 5）跑完会把结果存成文件；这条链路是「把已经存好的订阅结果文件导出成 Excel」。用 EventBus 解耦了 Controller 和真正干活的 BackstageReporter。

---

## 附录：crm-report 跨服务调用清单（速查）

| 下游服务 | REST 客户端接口 | 被调 HTTP 接口 | 对应全链路文档 |
| --- | --- | --- | --- |
| udf-report | `portal/rpc/BIUDFResource.java`（BI-UDF-REPORT） | `/rptUdfViewDataController/queryReportData`、`/queryPivotReportData`、`/innerUdfQueryReportDataAndUploadByPage`、`/backstageQueryReportDataByPage`、`/rptUdfViewEditController/getFiltersResult` | 全链路走读-fs-bi-udf-report.md |
| dev-platform | `portal/rpc/BIDEVResource.java`（BI-DEV-PLATFORM） | `/lwt/query`、`/lwt/getFiltersResult`、`/lwt/getLwtArgs`、`/lwt/getReportDetailArg` | 全链路走读-fs-bi-dev-platform.md |
| fs-bi | `thirdparty/rpc/FSBIResource.java`（FS-BI） | `/stat/data/query`、`/stat/filters/getFiltersResult`、`/stat/chartConfig/query`、`/stat/detail/data/query` | 全链路走读-fs-bi.md |
| warehouse（MQ） | `service/WarehouseEventProducer.java` | RocketMQ TOPIC `bi-warehouse-event` / TAG `dws_view_event` | [全链路走读-fs-bi-warehouse.md](../大数据/全链路走读-fs-bi-warehouse.md)（DWSViewChangeConsumer） |
