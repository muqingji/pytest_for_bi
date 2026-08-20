# fs-bi-dev-platform 全链路走读手册（10 条主链路）

> 用法：每一条链路都从「API 接口文件 → 方法 → 服务 → 数据层/RPC」完整串联。你只需要按顺序打开文件、找到方法，一行行看。
> 仓库根：`/Users/muqingji/code/serve/fs-bi-dev-platform`；主代码模块是 `fs-bi-dev-web/src/main/java/com/facishare/bi/dev/web/`，下文路径都省略这个前缀。
> 行号为当前代码实际行号，找不到就按类名/方法名搜索。
> **跨服务跳转指引**：dev-platform 是「大宽表（LWT）拼表服务」，自己不直接算数，而是把宽表里的每一个数据源（报表/交叉表/统计图）分发给下游服务，然后在内存里 JOIN 成一张大表：
> - 数据源类型 1（报表）→ 调 udf-report `/rptUdfViewDataController/queryReportData`（见《全链路走读-fs-bi-udf-report.md》）
> - 数据源类型 2（交叉表）→ 调 udf-report `/rptUdfViewDataController/queryPivotReportData`
> - 其他（统计图）→ 调 fs-bi `/stat/data/query`（见《全链路走读-fs-bi.md》）
> - 上游 crm-report 调 dev-platform 的入口在《全链路走读-fs-bi-crm-report.md》链路 3。

---

## 链路速览表（先看这个：10 秒知道每个链路是干啥的）

| 链路 | 一句话说明（大白话） |
| --- | --- |
| 1 大宽表数据查询 | 查拼表数据：读配置 → 把每个数据源发给下游查 → 内存里 JOIN 成一张大表 |
| 2 大宽表查询（异步版） | 查询太慢时改用 MQ+Redis：先返回请求号，算好后前端再取结果 |
| 3 保存/编辑宽表 | 在拼表设计器里保存配置：把配置 JSON 存 PG + 注册报表名 + 设置权限 |
| 4 复制宽表 | 一键复制拼表：生成新 id 把配置再存一遍 |
| 5 数据源字段详情 | 设计器里选了一个数据源后，列出它的字段（转发下游拿字段定义） |
| 6 筛选器范围查询 | 宽表筛选器下拉的选项（静态字典 or 动态查数据） |
| 7 批量筛选范围 | 一次查多个宽表的筛选器选项（驾驶舱/批量场景用） |
| 8 获取宽表完整配置 | 把拼表配置（数据源+关系+字段）加载成内存对象，其他链路复用它 |
| 9 宽表数据导出 | 把查好的数据转 Excel；订阅场景从文件服务器拉结果文件再转 |
| 10 明细参数构建 | 宽表里点某个数字「看明细」：先拼出明细查询参数，再交给下游查 |

---

## 链路 1：大宽表数据查询（核心链路，同步直查）

> **这条链路是干什么的（大白话）**：**场景**：用户在门户打开一张「拼表」报表并查询。**它做的事**（dev-platform 是拼表服务）：①读拼表配置（哪些数据源、怎么关联、显示哪些字段）→ 本地 PG ②把每个数据源分发给对应下游：报表数据源→udf-report、交叉表数据源→udf-report、统计图数据源→fs-bi ③把各数据源结果在内存里按关联关系 JOIN 成一张大表 ④分页返回。**可以这样理解**：dev-platform 是个「拼接工人」，自己不算数，把别人算好的结果拼起来。


**API 文件**：`controller/LwtController.java`
**接口方法**：`POST /lwt/query` → `query()`（第 111 行）

```
LwtController.query()
  ├─ adjustUserInfoForEM6H() 处理外租户用户信息
  ├─ 灰度判断 lwtSync2async：命中→走异步（链路 2）；不命中→ originQuery()
  └─ originQuery()（LwtController.java，第 203 行）
      ├─ lwtQueryConsumer.preHandle(userInfo, queryLwtArg)   ← 解析请求，加载宽表配置
      │     → LwtQueryConsumer.preHandle()（mq/LwtQueryConsumer.java）→ largeWideTableService.getLwtArgs(...)
      │         → LargeWideTableService.getLwtArgs()（service/LargeWideTableService.java，第 5577 行）
      │             ├─ dataOpService.getConfig(lwtId, ei)（service/DataOpService.java，第 101 行）
      │             │     → LargeWideTableConfigRepository.getConfig → MyBatis Mapper → PostgreSQL（large_wide_table_config 表）
      │             ├─ dataOpService.getDataSources(ei, ids, ...)（第 134 行）→ PostgreSQL（large_wide_table_data_source 表）
      │             ├─ dataOpService.getRptInfoById(ei, viewId, viewType)（第 90 行）→ PostgreSQL（rpt_view 表）
      │             └─ 组装 LargeWideTableArgs（数据源列表 + 关联关系 relations + 计算列 + 显示字段）
      ├─ 判断是否自定义表（id 含 "cus"）：
      │     ├─ 是 → customTableService.doQuery()（自定义表查询）
      │     └─ 否 → largeWideTableService.doQuery(queryModel, outerUserInfo, queryLwtArg)（第 848 行）
      │           → LargeWideTableService.doQuery(重载，第 921 行)
      │               ├─ handleSpecailFilterByFunction / handleSpecialFilterField 预处理筛选器
      │               └─ queryLwtResult()（第 1043 行）
      │                   ├─ 处理下钻/计算列/度量字段，组装列头 Header
      │                   └─ processDataSource()（第 2534 行）★核心分发点★
      │                       ├─ viewType=1 → reportService.getReportDataSourceWithSimpleData()
      │                       │     → ReportService（service/ReportService.java，第 415 行）
      │                       │         → queryReportData()（第 158 行）
      │                       │             → HTTP POST udfApiHost + "rptUdfViewDataController/queryReportData"（跨服务 → udf-report 链路 2）
      │                       ├─ viewType=2 → pivotTableService.getReportDataSource()
      │                       │     → PivotTableService（service/PivotTableService.java，第 139 行）
      │                       │         → HTTP POST udfApiHost + "rptUdfViewDataController/queryPivotReportData"（跨服务 → udf-report 链路 3）
      │                       └─ 其他 → statService.getStatDataSource()
      │                             → StatService（service/StatService.java，第 291 行）
      │                                 → HTTP POST statApiHost + "fs-bi-stat/stat/data/query"（跨服务 → fs-bi 链路 4）
      │                       └─ 结果存 dfValuesMaps / dfDisplayColumnsMap（每个数据源一坨数据）
      │                   └─ 内存 JOIN：按 relations 把各数据源数据拼接成一张大表 → 分页 → QueryLwtResult
      └─ 返回 QueryLwtResult{data, columns, totalCount}
```

**底层落点**：PostgreSQL（宽表配置表）+ HTTP RPC → udf-report / fs-bi（真实数据计算）+ 内存 JOIN。

**新手要点**：这条链路是 dev-platform 的心脏。三个关键方法依次看：`getLwtArgs`（读配置）、`processDataSource`（分发各数据源查询）、JOIN 拼表。宽表 = 「配置在本地库、数据在别处」。

---

## 链路 2：大宽表数据查询（异步版：MQ + 缓存）

> **这条链路是干什么的（大白话）**：**场景**：拼表查询太慢（要等好几个下游），为了不让用户干等。**它做的事**：改成异步三步走：①提交查询请求，立刻返回 reqId（请求号）②后台通过 MQ（topic `BIDEV_QUERY_NOTIFY`）异步执行同样的查询，结果存 Redis ③前端拿 reqId 轮询「取结果」接口，算好了就返回数据。**好处**：用户先看到加载动画，不用一直挂连接。


**API 文件**：`controller/LwtController.java`
**接口方法**：`POST /lwt/query`（第 111 行，灰度命中异步分支）；`POST /lwt/async/sendRequest`（第 346 行）；`POST /lwt/async/loadResponse`（第 360 行）

```
【第一步 发请求】
LwtController.query()（异步分支）
  ├─ lwtQueryCache.getReqId() 生成 reqId
  ├─ lwtQueryCache.cacheIfAbsent(reqId) 登记状态（0 处理中）
  ├─ 同步执行：lwtQueryConsumer.preHandle() + largeWideTableService.doQuery()（同链路 1）
  ├─ preRefreshParamUnifyService.cacheQueryDataResult(reqId, ...) 结果写缓存
  └─ 若未完成则返回，前端稍后轮询

【第二步 显式异步提交】（可选）
LwtController.asyncSend()
  └─ asyncQueryLwtSerivce.asyncSend(userInfo, outerUserInfo, arg)
      → AsyncQueryLwtService（service/AsyncQueryLwtService.java）
          ├─ 组装 LwtQueryMessage{reqId, userInfo, queryLwtArg}
          └─ lwtQueryProducer.sendMsg(msg)（mq/LwtQueryProducer.java，第 35 行）
              → RocketMQ TOPIC "BIDEV_QUERY_NOTIFY"
                  → LwtQueryConsumer 消费（mq/LwtQueryConsumer.java）
                      ├─ 解析 LwtQueryMessage
                      ├─ largeWideTableService.doQuery()（同链路 1 的查询）
                      └─ preRefreshParamUnifyService.cacheQueryDataResult() 结果缓存（Redis）

【第三步 取结果】
LwtController.asyncLoad()
  └─ asyncQueryLwtSerivce.asyncLoad(userInfo, arg)
      → 从缓存按 reqId 取 QueryLwtResult（Kryo/JSON 反序列化）→ 返回
```

**底层落点**：RocketMQ（BIDEV_QUERY_NOTIFY）+ Redis 缓存（查询结果按 reqId 存）。

**新手要点**：异步的目的：大宽表查询慢（要查多个下游服务），先用 MQ/线程把数据算好放缓存，前端拿 reqId 轮询 `asyncLoad` 取结果。三步：发请求→算→取。

---

## 链路 3：保存/编辑大宽表配置（写配置）

> **这条链路是干什么的（大白话）**：**场景**：用户在拼表设计器里拖好数据源、字段、关联关系，点「保存」。**它做的事**：把整张拼表配置（数据源列表、关联关系、计算列、布局）序列化成 JSON 存 PostgreSQL 配置表；同时注册报表名（rpt_view）和设置权限（转发 crm-report 权限接口）。**理解**：拼表配置就是一张「蓝图」，查询时（链路 1）按蓝图执行。


**API 文件**：`controller/ManagerController.java`
**接口方法**：`POST /lwt/m/save` → `save()`（第 68 行）

```
ManagerController.save()
  → saveLwtService.doSave(arg, userInfo)（service/SaveLwtService.java，第 59 行）
      ├─ 1. 编辑 or 新建判断：
      │     ├─ 编辑（queryLwtArg.id 非空 且 saveType!=2）：
      │     │     ├─ dataOpService.getRptInfoByNameWithCateGoryId() 查重名 → PostgreSQL
      │     │     ├─ dataOpService.deleteConfig(lwtId, ei) 删老配置 → PostgreSQL
      │     │     └─ dataOpService.updateRptView(...) 更新报表名/分类 → PostgreSQL
      │     └─ 新建：paasLicenseService.validateLwtViewQuota() 校验配额（License 服务）
      ├─ 2. 写配置：configService.insertConfig(arg, ei, lwtId)
      │     → ConfigService.insertConfig → LargeWideTableConfigRepository.insert
      │         → MyBatis Mapper → PostgreSQL（large_wide_table_config 表，JSON 存全部配置）
      ├─ 3. 新建时：dataOpService.insertRptView(...) → PostgreSQL（rpt_view 表，注册报表）
      ├─ 4. 权限：crmReportWebService.getReportPermission / setReportPermission / updateReportPermission
      │     → HTTP 调 crm-report 的权限接口（/bi/report/...）
      ├─ 5. dataOpService.upsertPermission / upsertPermissionGray → PostgreSQL（权限表）
      ├─ 6. 国际化词条：upInsertLwtConfigI18nEntry / upInsertLwtViewName → PostgreSQL
      ├─ 7. pointReportService.sendRptPoint() 埋点
      └─ 返回 lwtId
```

**底层落点**：PostgreSQL（large_wide_table_config / rpt_view / 权限表）+ HTTP RPC → crm-report（权限）。

**新手要点**：保存 = 把整张宽表的「拼表配置」（数据源、关联关系、字段、布局）序列化成 JSON 存 PostgreSQL，同时注册报表名和权限。

---

## 链路 4：复制大宽表

> **这条链路是干什么的（大白话）**：**场景**：用户想「复制一份拼表」再改，不用从零搭。**它做的事**：读取源拼表配置 → 生成新的 id → 把配置原样再存一遍 → 注册新报表名 → 复制权限。**本质**：和链路 3 的保存共用同一个写配置的方法，只是先读后写。


**API 文件**：`controller/ManagerController.java`
**接口方法**：`POST /lwt/m/copyLwtView` → `copyLwtView()`（第 78 行）

```
ManagerController.copyLwtView()
  → saveLwtService.copyLwtView(arg, userInfo)（service/SaveLwtService.java，第 155 行）
      ├─ 1. dataOpService.getRptInfoById() 查源宽表 → PostgreSQL
      ├─ 2. 查重名（同文件夹下）
      ├─ 3. 生成新 lwtId
      ├─ 4. 复制配置：configService.insertConfig(...)（深拷贝 datasource/relation 等）→ PostgreSQL
      ├─ 5. dataOpService.insertRptView(...) → PostgreSQL（注册新报表）
      └─ 6. 复制权限 → 返回 newLwtId
```

**底层落点**：PostgreSQL（宽表配置 + 报表注册表）。

**新手要点**：复制 = 读取源配置 → 换新 ID 再写一遍。和链路 3 的保存共用 `insertConfig`。

---

## 链路 5：数据源字段详情（拼表设计器用）

> **这条链路是干什么的（大白话）**：**场景**：拼表设计器里用户添加一个数据源（比如加一张报表），系统要立刻列出这张报表有哪些字段可以拖。**它做的事**：按数据源类型转发下游拿字段定义：报表→udf-report、交叉表→udf-report（getPivotQueryArg）、统计图→fs-bi，然后汇总返回字段列表。


**API 文件**：`controller/ManagerController.java`
**接口方法**：`POST /lwt/m/getDataSourceFieldsDetail` → `getDataSourceFieldsDetail()`（第 44 行）

```
ManagerController.getDataSourceFieldsDetail()
  → largeWideTableDataSourceService.getDsFieldsDetail(userInfo, outerUserInfo, arg)
      → LargeWideTableDataSourceService.getDsFieldsDetail()（service/LargeWideTableDataSourceService.java，第 95 行）
          ├─ 遍历 arg.dataSourceArgs（每个数据源）
          ├─ dataOpService.getRptInfoById(ei, viewId, viewType) → PostgreSQL（rpt_view 表）
          ├─ 按 viewType 分派查字段：
          │     ├─ 1（报表）：reportService.getDataSourceDisplayFields(...)
          │     │     → HTTP 调 udf-report 取报表字段定义
          │     ├─ 2（交叉表）：pivotTableService.getPivotQueryArg(...)
          │     │     → HTTP 调 udf-report /rptUdfViewDataController/getPivotQueryArg（PivotTableService 第 122 行）
          │     └─ 其他（统计图）：statService 取统计图字段 → HTTP 调 fs-bi
          └─ 组装 DataSourceFields{viewId, viewName, fieldList} 返回
```

**底层落点**：PostgreSQL（本地报表注册）+ HTTP RPC → udf-report / fs-bi（字段定义）。

**新手要点**：拼表设计器里「选择数据源后自动列出字段」就是调这个接口。字段本身存在下游服务里，这里只是聚合展示。

---

## 链路 6：筛选器范围查询（单个宽表）

> **这条链路是干什么的（大白话）**：**场景**：拼表上有个筛选器（比如「选择销售区域」「选择日期」），用户点开下拉框时。**它做的事**：算这个筛选器有哪些可选值：静态选项直接读配置/字典；动态选项（如「去重后的销售区域列表」）要构造查询去下游/数据库取。**理解**：这就是筛选器下拉「有什么可选」的来源。


**API 文件**：`controller/LwtController.java`
**接口方法**：`POST /lwt/getFiltersResult` → `getFiltersResult()`（第 387 行）

```
LwtController.getFiltersResult()
  ├─ dataOpService.getRptInfoById(ei, arg.getId())（DataOpService 第 48 行）→ PostgreSQL（校验宽表存在，rpt_view 表）
  ├─ filterService.getFilterResult(userInfo, outerUserInfo, arg)
  │     → FilterService.getFilterResult()（service/FilterService.java，第 183 行）
  │         ├─ 加载宽表配置（同链路 1 的 getLwtArgs）
  │         ├─ 对每个筛选器（日期/枚举/人员/部门等）计算可选范围：
  │         │     ├─ 简单枚举 → 直接查 PostgreSQL（本地字典）
  │         │     └─ 数据驱动的筛选（如「取字段的去重值」）→ 按数据源类型调下游
  │         │           ├─ udf-report（报表字段去重）/ fs-bi（统计图字段去重）
  │         └─ 组装 FilterResult{filterLists}
  ├─ handleFilterUIDisabled() / handleEmptyValueWithSelectRange() 结果微调
  └─ 返回 FilterResult
```

**底层落点**：PostgreSQL（宽表配置/字典）+ HTTP RPC → udf-report / fs-bi（数据驱动筛选值）。

**新手要点**：筛选器范围 = 用户点「筛选」下拉时看到哪些选项。分两种：静态选项（配置里写死）和动态选项（去数据库查）。

---

## 链路 7：批量筛选范围查询（驾驶舱/订阅批量用）

> **这条链路是干什么的（大白话）**：**场景**：驾驶舱或批量场景下，一个页面同时有多个拼表，需要一次性拿到所有拼表的筛选器选项。**它做的事**：批量循环链路 6 的单表逻辑，返回 Map<拼表 id, 筛选器列表>。**对比链路 6**：一个是一张表，一个是多张表。


**API 文件**：`controller/LwtController.java`
**接口方法**：`POST /lwt/batchGetFiltersResult` → `batchGetFiltersResult()`（第 439 行）

```
LwtController.batchGetFiltersResult()
  └─ filterService.batchGetCommonFilters(viewIds, userInfo)
      → FilterService.batchGetCommonFilters()（service/FilterService.java，第 79 行）
          ├─ 批量加载多个宽表的配置（getLwtArgs 循环）
          ├─ 批量查询每个宽表的筛选器范围（复用链路 6 的单表逻辑）
          └─ 返回 Map<viewId, List<LwtCommonFilterList>>
```

**底层落点**：PostgreSQL + HTTP RPC → udf-report / fs-bi。

**新手要点**：和链路 6 一样，只是把「一个宽表」变成「一批宽表」，驾驶舱（一个页面多个宽表）用得多。

---

## 链路 8：获取宽表完整配置（getLwtArgs）

> **这条链路是干什么的（大白话）**：**场景**：任何需要「拼表完整配置」的地方（查询、筛选、导出）。**它做的事**：把配置表里的 JSON 反序列化，加上每个数据源的字段信息，组装成一个完整的内存对象 LargeWideTableArgs（数据源+关系+计算列+显示字段+汇总设置）。**理解**：它是链路 1/6/9 的「前菜」，查询前都要先调它把配置加载好。


**API 文件**：`controller/LwtController.java`
**接口方法**：`POST /lwt/getLwtArgs` → `getLwtArgs()`（第 450 行）

```
LwtController.getLwtArgs()
  └─ largeWideTableService.getLwtArgs(arg.getId(), ei, ea, true)
      → LargeWideTableService.getLwtArgs()（第 5577 行）★配置装配大方法★
          ├─ dataOpService.getConfig(lwtId, ei) → PostgreSQL（large_wide_table_config）
          ├─ 解析 datasource 字段 → dataOpService.getDataSources(...) → PostgreSQL
          ├─ 逐个数据源：dataOpService.getRptInfoById(ei, viewId, viewType) → PostgreSQL（rpt_view）
          │     → 按 viewType 调下游拿显示字段（reportService / pivotTableService / statService）
          ├─ 反序列化 relations / rowRelation / colRelation / calColumns / layout 等 JSON
          └─ 组装完整 LargeWideTableArgs（数据源 + 关联 + 计算列 + 显示字段 + 汇总配置）返回
```

**底层落点**：PostgreSQL（配置表）+ HTTP RPC → udf-report / fs-bi（字段信息）。

**新手要点**：`getLwtArgs` 是「宽表配置的完整内存形态」，链路 1 的查询、链路 6/7 的筛选都复用它。字段、关系、计算列全在这一步装好。

---

## 链路 9：宽表数据导出（Excel / 文件流）

> **这条链路是干什么的（大白话）**：**场景**：用户点「导出」把拼表数据存成 Excel；或订阅任务跑完把结果文件发出来。**它做的事**：两种方式：①前端已经查好的数据直接转 Excel 返回；②订阅场景从文件服务器下载「已算好的结果文件」，反序列化后再转 Excel 返回。


**API 文件**：`controller/LwtController.java`
**接口方法**：`POST /lwt/exportLwtData`（第 530 行）；`POST /lwt/exportLwtDataByPath`（第 540 行）

```
【方式一：直接把查询结果转 Excel】
LwtController.exportLwtData()
  ├─ 接收前端已经查好的 QueryLwtResult（前端先把数据查出来再导出）
  └─ LargeWideTableReportExport.export(queryLwtResult, userInfo)
      → 报表导出工具：把 data（行数据）+ columns（列头）拼成 Excel 字节
      → copyBytesToResponseStream() 写回 HTTP 响应流

【方式二：从文件服务器拉数据再导出（订阅场景）】
LwtController.exportLwtDataByPath()
  ├─ fileService.downloadFile(filePath, ...) 从文件服务器下载（订阅任务存的结果文件）
  ├─ 反序列化：Kryo（readCompressObjectWithKryo）或 JSON → QueryLwtResult
  └─ LargeWideTableReportExport.export() → 写回响应流

【配套订阅上传链路】
POST /lwt/innerExportLwtData / /lwt/innerExportLwtDataWithNotice（第 507/519 行）
  → 查询宽表数据 → 转文件 → 上传文件服务器 → 通知（订阅推送）
```

**底层落点**：文件服务器 + Excel 导出工具（无数据库）。

**新手要点**：导出分两种：前端已有数据直接转 Excel；订阅场景从文件服务器把「算好的结果文件」下载回来再转 Excel。

---

## 链路 10：明细参数构建（报表/统计图下钻）

> **这条链路是干什么的（大白话）**：**场景**：用户在拼表里点某个数字「看明细」——比如拼表汇总行的「销售额 100 万」，点进去看是哪几笔订单。**它做的事**：把拼表的上下文（当前筛选、当前维度值）翻译成下游能用的明细查询参数：报表明细→QueryReportDataArg（给 udf-report）、统计图明细→QueryStatDetailInfoArg（给 fs-bi）。**理解**：它只「拼参数」，不查数据。


**API 文件**：`controller/LwtController.java`
**接口方法**：`POST /lwt/getReportDetailArg`（第 570 行）；`POST /lwt/getStatDetailArg`（第 579 行）

```
【报表明细】
LwtController.getReportDetailArg()
  └─ reportService.createQueryReportDataArg(userInfo, arg, outerUserInfo)
      → ReportService.createQueryReportDataArg()（service/ReportService.java，第 1274 行）
          ├─ 查宽表/报表配置（dataOpService）
          ├─ 把「宽表的某个格子/某行」的上下文（筛选、维度值）翻译成报表查询参数
          └─ 返回 QueryReportDataArg（可直接调 udf-report /queryReportData）

【统计图明细】
LwtController.getStatDetailArg()
  └─ statService.createQueryStatDetailInfoArg(userInfo, outerUserInfo, arg)
      → StatService（service/StatService.java）→ 返回 QueryStatDetailInfoArg
          → 上游拿这个 arg 调 fs-bi /stat/detail/data/query 查明细
```

**底层落点**：PostgreSQL（配置）+ 参数组装（最终调 udf-report / fs-bi 查明细数据）。

**新手要点**：宽表里点某个数字「看明细」，就是先由这两个接口把「明细查询参数」拼出来，再交给下游真实查询。

---

## 附录：dev-platform 下游调用清单（速查）

| 下游服务 | 调用位置 | 被调 HTTP 接口 | 对应全链路文档 |
| --- | --- | --- | --- |
| udf-report | `service/ReportService.java` 第 158 行 | `/rptUdfViewDataController/queryReportData` | 全链路走读-fs-bi-udf-report.md 链路 2 |
| udf-report | `service/PivotTableService.java` 第 141/150 行 | `/rptUdfViewDataController/queryPivotReportData`、`/innerQueryPivotReportData` | 全链路走读-fs-bi-udf-report.md 链路 3 |
| udf-report | `service/PivotTableService.java` 第 122 行 | `/rptUdfViewDataController/getPivotQueryArg` | 全链路走读-fs-bi-udf-report.md |
| fs-bi | `service/StatService.java` 第 291 行 | `/stat/data/query`（statApiHost + fs-bi-stat 前缀） | 全链路走读-fs-bi.md 链路 4 |
| fs-bi | `service/StatService.java` 第 258/274/386 行 | `/stat/chartConfig/query`、`/stat/filters/getFiltersResult`、`/stat/data/dataQueryByPaging` | 全链路走读-fs-bi.md |
| crm-report | `service/SaveLwtService.java`（crmReportWebService） | 权限接口（getReportPermission/setReportPermission） | 全链路走读-fs-bi-crm-report.md 链路 8 |
| 外部 LWT 服务 | `service/LwtService.java` | `http://172.31.100.247:10091`（外部大宽表服务，旧版） | — |
| fs-bi-sqlengine | `service/SqlEngineService.java` | `http://127.0.0.1:31025/`（SQL 引擎，当前未被注入使用） | 全链路走读-fs-bi.md 链路 10 |
