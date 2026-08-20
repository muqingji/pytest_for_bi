# bi-xkcharts 全链路走读手册（10 条主链路）

> 用法：每一条链路都从「入口文件 → 方法 → 服务 → 渲染/后端接口」完整串联。前端组件库没有「数据库」这一层，链路的终点是**后端 HTTP 接口**或**渲染引擎**，请按顺序打开文件、找到方法，一行行看。
> 仓库根：`/Users/muqingji/code/FE/bi-xkcharts`；行号为当前代码实际行号，找不到就按类名/方法名搜索。
> **跨服务跳转指引**：组件库的数据来自后端，凡标注「后端接口」的地方，可跳到对应后端文档看服务端实现：
> - `/FHH/EM1HBISTAT/fs-bi-stat/stat/chartConfig/query`、`/stat/data/query`、`/stat/chart/query` → fs-bi（见《[全链路走读-fs-bi.md](../后端/全链路走读-fs-bi.md)》链路 3/4）
> - `/EM1HBICRM/...`（老门户接口）→ crm-report（见《[全链路走读-fs-bi-crm-report.md](../后端/全链路走读-fs-bi-crm-report.md)》链路 2）
> - `/EM1HBIUDF/...`（销售过程/商机）→ udf-report

---

## 链路速览表（先看这个：10 秒知道每个链路是干啥的）

| 链路 | 一句话说明（大白话） |
| --- | --- |
| 1 实例创建与初始化 | 页面 `new BIXkcharts(options)` 建图表实例：初始化 DOM、主题、绑定事件 |
| 2 数据查询主链路 | 核心链路：查配置 → 查数据 → 存数据 → 交给渲染（对应后端 fs-bi） |
| 3 合并查询 | 新灰度路径：配置+数据+筛选一次接口拉完，少一次往返 |
| 4 异步查询 | 数据量大的图：先发请求拿任务号，后台算完再轮询取结果 |
| 5 图表渲染 | 把数据翻译成 ECharts 配置并画出来（柱/线/饼/地图等 20+ 种图） |
| 6 表格渲染 | 统计表/透视表/Canvas 大表的渲染（图+表同屏场景） |
| 7 下钻 | 点击图表柱子/单元格，按维度逐级钻取，重新查数据画更细的图 |
| 8 查看明细 | 点击某个数值，弹出该数值对应的明细列表 |
| 9 主题与类型切换 | 换主题色（深/浅色）、切换图表类型（柱↔线↔表）并重新渲染 |
| 10 自适应与销毁 | 窗口大小变化自动缩放图表；离开页面销毁实例释放资源 |

---

## 链路 1：实例创建与初始化（所有图表的第一步）

**入口文件**：`src/xkcharts.js`
**入口方法**：`new BIXkcharts(options)` → 构造函数（第 56 行）→ `this.init()`（第 211 行）

```
宿主页面（门户/客户端/第三方）
  → new BIXkcharts({$el, id, from, scene, queryParamsObj, ...})（src/xkcharts.js，第 56 行）
      ├─ 1. 默认 options 合并：接口 URL、超时、loading、下钻开关、主题配置等（第 120 行起）
      ├─ 2. 若外部直接传 chartConfig / chartData，则跳过请求直接用（第 192/199 行）
      ├─ 3. 初始化监控：this.monitor = new MonitorService()
      └─ 4. this.init()（第 211 行）
          ├─ 终端判断：terminalJudge() / util.detectEnv()（PC / H5 / 企微 / 云之家 / 纷享 App）
          ├─ 初始化主题：initTheme()
          ├─ 建 DOM 容器：_initDom() → renderCntr()（render.js）创建 .tablechartcntr 容器
          ├─ 挂附属组件：LastTime（更新时间）/ SubTitle（副标题）/ AverageTotal（平均合计）/ ChartTypeSelect（类型切换器）
          └─ onReplyLibReady()：若 echarts 未加载则从 libs 目录异步加载脚本
              → _init() → bindEvents()（events.js，第 6 行）★绑定窗口 resize + 图表点击事件★
```

**底层落点**：DOM 容器 + 事件绑定（无后端调用）。
**新手要点**：一个图表 = 一个实例。构造函数只做「准备动作」，真正查数据要宿主再调用 `showDetail()`（链路 2）。

---

## 链路 2：数据查询主链路（核心链路：配置 → 数据 → 渲染）

**入口文件**：`src/core/instance/server.js`
**入口方法**：`showDetail()`（第 106 行）→ `queryChartConfig()`（第 137 行）→ `queryData()`（第 316 行）

```
宿主调用实例.showDetail(opt)（server.js，第 106 行）
  ├─ 有 chartConfig（外部直传）→ 直接 this.queryData(opt)
  ├─ 合并查询灰度（enableMergedQuery）→ MergedQuery.queryMergedAll()（见链路 3）
  └─ 默认路径 ★：
      → queryChartConfig(opt, params, cb)（第 137 行）
          ├─ 组装参数：{id, isView, dashboardId} + _addQueryParams()
          ├─ this.ajax({url: _getQueryChartConfigUrl(), data: params})
          │     → server.js 第 72 行 _getQueryChartConfigUrl()
          │         → 默认 '/FHH/EM1HBISTAT/fs-bi-stat/stat/chartConfig/query'（fs-bi 统计图配置接口）
          │     → ajax.js this.ajax()（src/core/instance/ajax.js）
          │         ├─ 组装 traceId（getTraceId，含端/浏览器/企业信息）
          │         ├─ 附 fs_token（cookie）
          │         ├─ 优先 window.BI.util.FHHApi（统一 API），否则 $.ajax
          │         └─ 完成后上传日志（util.uploadLogBySas）
          └─ success：校验配置（chartType 必须有）→ 存 this.chartConfig → 回调执行 queryData()
      → queryData(opt)（第 316 行）★数据查询核心★
          ├─ 1. 组装查询参数：getQueryParams(chartType)（第 597 行）= queryParamsObj + 分页 + 图表类型
          │     └─ 含 chartType、queryLimit、筛选、isShowDimension、全局筛选等
          ├─ 2. 显示 loading：this.showLoading()
          ├─ 3. 发起请求（第 530 行起）：
          │     ├─ 异步轮询灰度（isNeedAsyncLoad / pollingType）→ HybridPolling（见链路 4）
          │     └─ 同步：this.ajax({url: _getQueryChartDataUrl(), data})
          │           → server.js 第 46 行 _getQueryChartDataUrl()
          │               → 默认 '/FHH/EM1HBISTAT/fs-bi-stat/stat/data/query'（fs-bi 统计图数据接口）
          │               →（老门户 from=base 时）'/FHH/EM1HBICRM/statChartController/queryChartData'（crm-report）
          ├─ 4. success 处理（第 428 行 _success）：
          │     ├─ util.setGrayConfig(res.Result) 更新灰度
          │     ├─ this.initChartData(res.Value) 存数据（xkcharts.js，第 317 行）
          │     ├─ this.destroyChart() 销毁旧图表
          │     └─ this.render() ★进入渲染链路 5★
          └─ error 处理：onRequestError → renderError（错误态 DOM）
```

**底层落点**：后端 HTTP（fs-bi `/stat/chartConfig/query` + `/stat/data/query`；老门户 crm-report 接口）。
**新手要点**：这是组件库的「心脏」。记住三步：先问后端「这个图长什么样」（配置），再问「数据是什么」（数据），最后渲染。配置接口和数据接口的参数都在 `server.js` 里组装。

---

## 链路 3：合并查询（配置+数据+筛选一次拉完）

**入口文件**：`src/core/instance/merged-query.js`
**入口方法**：`MergedQuery.queryMergedAll()`（第 19 行）

```
showDetail()（server.js，第 106 行，灰度命中 enableMergedQuery）
  → new MergedQuery(this).queryMergedAll(opt, params)（merged-query.js，第 19 行）
      ├─ 1. collectAllParams()（第 41 行）收集三类参数：
      │     ├─ statChartConfArg（图表配置参数，第 60 行 collectChartConfigParams）
      │     ├─ queryChartDataArg（数据查询参数，第 79 行 collectQueryDataParams，复刻 queryData 逻辑）
      │     └─ statFilterArg（筛选器参数，collectFilterParams）
      ├─ 2. shouldUseHybridPolling()（第 222 行）判断是否走异步轮询
      ├─ 3a. executeSyncRequest()（第 249 行）★同步合并查询★
      │     └─ this.instance.ajax({url: 合并接口})（默认 '/FHH/EM1HBISTAT/fs-bi-stat/stat/chart/query'）
      │         → 一次返回 {chartConfig, data, filterResult}
      │         → 分别赋值 → this.instance.render()
      └─ 3b. executeHybridPollingRequest()（第 229 行）→ 走异步轮询（见链路 4，用合并版接口）
```

**底层落点**：后端 HTTP（fs-bi `/stat/chart/query`，对应 fs-bi 链路 3）。
**新手要点**：原来要请求 2~3 次（配置、数据、筛选），合并查询 1 次搞定，省网络往返。注意这是灰度功能，默认仍走链路 2。

---

## 链路 4：异步查询（大数据量：先发任务、再轮询取结果）

**入口文件**：`src/util/hybrid-polling.js` + `src/core/instance/server.js`（第 530~548 行）
**入口方法**：`queryData()` 内 `new HybridPolling(...)`（server.js，第 538 行）

```
queryData()（server.js，第 316 行，命中异步灰度）
  └─ new HybridPolling({
         request: this.ajax,
         syncQueryUrl: _getQueryChartDataUrl(),       // 同步兜底接口
         sendQueryUrl: options.sendQueryDataUrl,       // 默认 '/async/sendQueryStatRequest'（发任务）
         loadQueryUrl: options.loadQueryDataUrl,       // 默认 '/async/loadQueryStatResult'（取结果）
         success, complete, data, headers
     })（src/util/hybrid-polling.js）
      ├─ 1. 先尝试同步查询（syncQueryUrl），快速返回就直接用
      ├─ 2. 超时/命中异步 → 调 sendQueryUrl 提交查询任务，拿到 reqId
      ├─ 3. 定时轮询 loadQueryUrl（带 reqId），后台算好就取回数据
      └─ 4. success 回调 → 走链路 2 的 _success → initChartData → render
```

**底层落点**：后端 HTTP（fs-bi `/async/sendQueryStatRequest` + `/async/loadQueryStatResult`）。
**新手要点**：大数据量统计图（几万行）同步查询会超时，所以「先提交任务拿号，再轮询取数」，前端一直转 loading 直到数据回来。

---

## 链路 5：图表渲染（数据 → ECharts 图形）

**入口文件**：`src/xkcharts.js`
**入口方法**：`render()`（第 782 行）→ `renderChart()`（第 1147 行）→ `renderChartByEcharts()`（第 1071 行）→ `_renderChartByEcharts()`（第 1118 行）

```
render()（xkcharts.js，第 782 行）★渲染总调度★
  ├─ 取图表类型 chartType = this.getChartType()
  ├─ 注册主题：registerTheme(this.getThemeName())（见链路 9）
  ├─ 分类型：
  │     ├─ card（KPI 卡片）→ renderKpiCard()（第 1052 行）→ mountVueComponent(KpiCard/CustomCard)
  │     ├─ table / pivottable → renderTable(true)（见链路 6）
  │     └─ 其他图表类型 → renderChart()（第 1147 行）
  │           ├─ renderDrill() 渲染下钻导航（如有）
  │           └─ renderChartByEcharts()（第 1071 行）
  │                 → _renderChartByEcharts()（第 1118 行）
  │                     ├─ createMyChart()（第 1113 行）→ echarts.init($container, themeName)
  │                     ├─ adaptDataForEcharts()（第 1156 行）★按类型选适配器★
  │                     │     ├─ bar/line/doubley → new BarLineAdapter（adapter/bar-line.js）
  │                     │     ├─ pie → PieAdapter；gauge → GaugeAdapter/ProgressAdapter
  │                     │     ├─ maphot/mapbubble/worldhot/worldbubble → Map/World 适配器
  │                     │     ├─ radar → DimRadar/MultiDimRadar；funnel → Funnel/CvrFunnel
  │                     │     └─ scatter/treemap/butterfly → 各自适配器
  │                     ├─ 适配器 translate()（如 bar-line.js 第 30 行）★生成 ECharts option★
  │                     │     ├─ getXAxisObj / getYAxisObj / getLegend / getTooltip / getSeries
  │                     │     ├─ 轴标记 initMark()（AxisMark）
  │                     │     └─ $.extend(this.xkcharts.chartOption, this.theOption)
  │                     ├─ setOption(chartOption) → myChart.setOption()
  │                     ├─ bindChartEvents()（events.js 第 42 行）绑定图例/鼠标事件
  │                     └─ resize() 自适应
  └─ 空数据处理：数据为空 → renderWhenNoData()（示例图）；无权限 → renderWhenNoQueryPermission()
```

**底层落点**：ECharts 渲染引擎（浏览器 Canvas/SVG）。
**新手要点**：渲染的「翻译官」是 adapter（适配器）。每种图一个 adapter，把统一的 chartConfig+data 翻译成 ECharts 认识的 option。想改某类图的样式，就找对应的 adapter 文件。

---

## 链路 6：表格渲染（统计表 / 透视表 / Canvas 大表）

**入口文件**：`src/core/table.js`
**入口方法**：`renderTable()`（第 98 行）

```
render()（xkcharts.js，第 782 行，chartType=table/pivottable，或图+表同屏）
  → renderTable(onlyTable)（src/core/table.js，第 98 行）
      ├─ renderDrill() 渲染下钻入口
      ├─ 分类型：
      │     ├─ pivottable（透视表）→ renderPivotTable() → 实例化 pivot-table 组件
      │     │     → components/canvas-table/pivot-table/index.js
      │     │     → bindPivotTableEvents()（第 141 行）绑定单元格点击（下钻/明细/排序）
      │     ├─ 移动端 → renderMobileTable()（bi-mobile-table）
      │     └─ PC → renderPCTable() → 实例化 chart-table / canvas-table 组件
      │           → components/chart-table/chart-table.js（Vue 组件）
      │           → bindCanvasTableEvents()（第 215 行）单元格点击/圈选/宽度调整
      └─ 排序：sortQueryData()（表格点击表头排序 → 重新 queryData）
```

**底层落点**：Vue 表格组件（DOM / Canvas 渲染），数据来自链路 2 的查询结果。
**新手要点**：统计图下面带表格（图+表同屏）或纯表格报表都走这条。单元格点击事件是下钻（链路 7）和明细（链路 8）的入口之一。

---

## 链路 7：下钻（逐级钻取）

**入口文件**：`src/core/instance/events.js` + `src/render/new-drill.js`
**入口方法**：图表点击回调（events.js，第 76 行）→ `newDrillObj.initDrill()`（new-drill.js，第 88 行）

```
用户点击图表柱子 / 表格单元格（events.js）
  └─ myChart.on('click')（events.js，第 76 行）
      → 判断 canDrill / linkageStatus / checkBeforeDrill()
      → this.newDrillObj.initDrill(params)（new-drill.js，第 88 行）
          ├─ 1. initDrillCrumbs()（第 28 行）初始化钻取导航条（显示钻取路径）
          ├─ 2. getSchemaDrillFields(params)（第 278 行）★查可下钻字段★
          │     └─ this.xkcharts.ajax({url: _getSchemaDrillFieldsUrl()})
          │           → 默认 '/FHH/EM1HBICRM/statChartController/getSchemaDrillFields'（crm-report）
          ├─ 3. 组装下钻查询参数：setDrillQueryParams / curDrillQueryParams（记录钻取路径）
          ├─ 4. this.xkcharts.queryData(opt, queryParams, true)（new-drill.js，第 496/633/886 行）
          │     → 复用链路 2 的查询（isDrillQuery=true，渲染下钻结果）
          └─ 5. 渲染新的图表 + 更新导航条（可回退上一级）
```

**底层落点**：后端 HTTP（crm-report `/statChartController/getSchemaDrillFields` + 链路 2 的数据接口）。
**新手要点**：下钻 = 「点一下柱子，看这柱子的下一层明细」。钻取路径存在 `curDrillQueryParams`，导航条可以逐级回退。

---

## 链路 8：查看明细（点击数值看明细列表）

**入口文件**：`src/render/see-detail.js`
**入口方法**：`SeeDetail.show()`（构造后 `seeDetailEvent()`，第 39 行；事件绑定第 469 行）

```
用户点击数值 → 触发 seeDetail 事件（events.js / table.js 分发）
  → SeeDetail 实例（src/render/see-detail.js）
      ├─ 1. 准备明细参数：收集当前图表筛选/维度值/行数据
      ├─ 2. 保存查询上下文：this.xkcharts.ajax({url: '/FHH/EM1HBISTAT/fs-bi-stat/stat/detail/data/saveQuery'})（第 62 行）
      ├─ 3. 拉明细数据：this.xkcharts.ajax({url: _getQueryStatToDetailInfoUrl()})（第 132 行）
      │     → server.js 第 23 行 _getQueryStatToDetailInfoUrl()
      │         → 默认 '/EM1HBICRM/statDetailController/queryStatToDetailInfo'（crm-report）
      │         → 自定义统计图（source=1）→ '/FHH/EM1HBISTAT/fs-bi-stat/stat/detail/data/query'（fs-bi）
      ├─ 4. 计算字段：/FHH/EM1HBISTAT/fs-bi-stat/stat/detail/calcagg/subfields（第 278 行，计算字段子项）
      └─ 5. 渲染明细弹层（zIndex = options.seeDetailzIndex）
```

**底层落点**：后端 HTTP（crm-report / fs-bi 明细接口）+ 弹层组件。
**新手要点**：查看明细 = 「点一个数字，弹出它对应的明细清单」。先 `saveQuery` 存上下文，再 `queryStatToDetailInfo` 拉明细。

---

## 链路 9：主题与图表类型切换

**入口文件**：`src/core/instance/theme.js` + `src/components/chart-type-select/chart-type-select.js`
**入口方法**：`registerTheme()`（theme.js，第 20 行）；切换器回调 → `render()`

```
【主题注册】
render()（xkcharts.js，第 782 行）
  → registerTheme(this.getThemeName())（theme.js，第 20 行）
      ├─ getThemeName()（第 55 行）根据 options.theme.name / styleId 决定主题名
      ├─ getThemeOption()（第 35 行）从 @theme 配置取主题 option
      ├─ registerThemeBefore()（第 74 行）外部可修改主题
      └─ window.echarts.registerTheme(themeName, themeOption) → echarts.init 时生效
  → 系统主题跟随：handleFollowSystemTheme()（util/theme-util/index.js）

【图表类型切换】
用户点切换器（chart-type-select 组件，components/chart-type-select/）
  → ChartTypeSelect 触发切换回调（xkcharts.js 中注册）
      → setOriginChartType(chartType)（记录原始类型）
      → queryData() 重新按新类型查数据 → render() → adaptDataForEcharts() 换 adapter → 重绘
```

**底层落点**：ECharts 主题注册表 + 重新渲染。
**新手要点**：主题 = ECharts 的「皮肤」；类型切换 = 换 adapter 重新画。注意切换后 `originChartType` 会保留原始类型用于特殊处理（如柱↔表切换限 2000 条）。

---

## 链路 10：自适应与销毁

**入口文件**：`src/core/instance/resize.js` + `src/xkcharts.js`（`destroy()`，第 1995 行）
**入口方法**：`resize()`（resize.js）；`destroy()`（xkcharts.js，第 1995 行）

```
【自适应】
窗口尺寸变化 → bindEvents() 里绑定的 window resize 回调（events.js，第 8 行）
  → 200ms 防抖 → this.resize()（src/core/instance/resize.js）
      ├─ 重新计算容器宽高
      ├─ adapter.resetOption() / adapter.resize(chartOption)（第 302/453 行）
      ├─ 表格组件 resize（chart-table）
      └─ myChart.resize() → ECharts 自适应重绘

【销毁】
宿主页面离开 / 组件卸载 → 实例.destroy()（xkcharts.js，第 1995 行）
  ├─ newDrillObj.destroy()（下钻导航清理）
  ├─ hybridPolling.destroy()（停止轮询）
  ├─ myChart.dispose()（ECharts 实例销毁）
  ├─ tableIns.$destroy()（表格组件销毁）
  ├─ $(window).off('resize')（解绑全局事件）
  └─ 清理 timer / ajaxAllLoading（中止进行中的请求）
```

**底层落点**：浏览器事件 + ECharts/Vue 实例生命周期。
**新手要点**：自适应和销毁是「善后」工作，容易被忽略但很重要：不销毁会内存泄漏、重复渲染错乱。`ajaxAllLoading` 数组用于切换图表时中止旧请求。

---

## 附录：后端接口调用清单（速查）

| 后端接口 | 用途 | 前端调用点 | 对应后端文档 |
| --- | --- | --- | --- |
| `/FHH/EM1HBISTAT/fs-bi-stat/stat/chartConfig/query` | 统计图配置 | server.js 第 146 行（链路 2） | fs-bi 链路 3 |
| `/FHH/EM1HBISTAT/fs-bi-stat/stat/data/query` | 统计图数据 | server.js 第 46 行（链路 2/4） | fs-bi 链路 4 |
| `/FHH/EM1HBISTAT/fs-bi-stat/stat/chart/query` | 合并查询（配置+数据+筛选） | merged-query.js（链路 3） | fs-bi 链路 3 |
| `/FHH/EM1HBISTAT/fs-bi-stat/async/sendQueryStatRequest` / `loadQueryStatResult` | 异步查询发任务/取结果 | server.js 第 542/543 行（链路 4） | fs-bi |
| `/FHH/EM1HBISTAT/fs-bi-stat/stat/detail/data/saveQuery` / `/stat/detail/data/query` | 明细上下文/明细查询 | see-detail.js 第 62/132 行（链路 8） | fs-bi |
| `/EM1HBICRM/statChartController/queryChartData` | 老门户统计图数据（from=base） | server.js 第 46 行 | crm-report 链路 2 |
| `/EM1HBICRM/statChartController/getSchemaDrillFields` | 可下钻字段 | new-drill.js 第 278 行（链路 7） | crm-report |
| `/EM1HBICRM/statDetailController/queryStatToDetailInfo` | 明细数据（老门户） | see-detail.js 第 132 行（链路 8） | crm-report |
| `/EM1HBIUDF/saleProcessAnalysisController/queryReportData` | 商机/销售过程图 | server.js 第 46 行（Oppo2 分支） | udf-report |
