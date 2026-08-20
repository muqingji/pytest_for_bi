# bi-xkcharts 代码走读详解（新手向 · 超详细版）

> 配套文档：《bi-xkcharts-架构分析.md》的「十、代码走读路线」和《全链路走读-bi-xkcharts.md》。本文把最核心的「**打开一个统计图 → 出图**」链路逐行讲透。
> 仓库根目录：`/Users/muqingji/code/FE/bi-xkcharts`。

---

## 0. 读代码前，先认识几个概念（新手速查）

| 概念 | 一句话解释 |
| --- | --- |
| BIXkcharts | 这个组件库的「全局名字」。页面引入库后，通过 `new BIXkcharts(options)` 创建一个统计图实例 |
| 实例（instance） | 一张统计图 = 一个实例。一个页面可以同时有多个实例（多个图） |
| options | 创建实例时传入的配置对象：图的 id、挂在哪个 DOM 上、什么场景、查询参数、接口地址等 |
| adapter（适配器） | 「翻译官」：把后端给的配置+数据，翻译成 ECharts 画图要的 option |
| option | ECharts 的绘图描述对象（有哪些轴、哪些数据系列、什么颜色） |
| chartConfig | 统计图「长什么样」的配置（图表类型、维度、指标、布局） |
| dataSet | 后端返回的「数据集合」（每一行的维度值+指标值） |
| from / scene | 场景标记：`from` 决定调哪一组后端接口（base 门户/subscription 订阅/board 驾驶舱）；`scene` 决定页面布局（PC/H5/编辑/预览） |
| traceId | 请求追踪号，出问题时报给后端排查用 |
| FHHApi | 宿主平台提供的统一 HTTP 调用能力（优先用它，没有就退回 jQuery 的 `$.ajax`） |

**这个仓库的特点**：它**不负责算数据**，只负责「把数据画出来」。后端（fs-bi 等）算好统计结果，它负责翻译成图形。所以它的「后端」就是那些 `/FHH/EM1HBISTAT/fs-bi-stat/stat/...` 接口。

---

## 1. 主链路总览（打开一个统计图，屏幕上出现了柱状图）

```
页面（门户/App/第三方）
   │ ① 引入库 + new BIXkcharts({...})
   ▼
xkcharts.js 构造函数（第 56 行）      ← 建实例：合并配置、准备 DOM、绑定事件
   ▼
宿主调用 showDetail()（server.js 第 106 行）   ← 开始干活：查配置 → 查数据
   ▼
queryChartConfig()（第 137 行）      ← 问后端：这个图长什么样？
   │   请求 /FHH/EM1HBISTAT/fs-bi-stat/stat/chartConfig/query
   ▼
queryData()（第 316 行）             ← 问后端：数据是什么？
   │   请求 /FHH/EM1HBISTAT/fs-bi-stat/stat/data/query
   ▼
initChartData() 存数据 → render()（xkcharts.js 第 782 行）   ← 开始画
   ▼
renderChart() → renderChartByEcharts() → echarts.init()
   ▼
adaptDataForEcharts() 选适配器 → adapter.translate() 生成 option
   ▼
myChart.setOption(option) → 屏幕上出现柱状图 🎉
```

---

## 2. 步骤 ①：`new BIXkcharts(options)` —— 建实例（前台接待）

文件：`src/xkcharts.js`（构造函数第 56 行）

```js
let xkcharts = function (opt) {
    this.clsName = 'ui-xkcharts';
    this.data = null;                       // 最新后台数据
    this.options = {
        $el: null,                          // 图表要挂载的 DOM 节点
        from: 'base',                       // 接口分组：base/subscription/qixin/board
        scene: '',                          // 场景：pc_edit/pc_prev/pc_detail/h5_board...
        queryChartConfigUrl: '/FHH/EM1HBISTAT/fs-bi-stat/stat/chartConfig/query',
        queryChartDataUrl: '/FHH/EM1HBISTAT/fs-bi-stat/stat/data/query',
        // ... 几十个默认配置
    };
    $.extend(this.options, opt);            // 用户传的配置覆盖默认值
    this.monitor = new MonitorService();    // 监控实例
    this.init();                            // 进入初始化
};
```

**新手解读**：
- `$.extend(this.options, opt)`：把用户传的配置和默认配置合并。用户没传的用默认值（比如接口地址都是默认写好的）。
- 注意接口地址都是 `/FHH/EM1HBISTAT/fs-bi-stat/...`——这就是它对接的后端服务（fs-bi）。
- `new BIXkcharts` 只是「准备」，真正查数据要宿主调用 `showDetail()`。

**初始化 init()（第 211 行）**：
```js
init: function () {
    this.$el = this.options.$el;
    this.terminalJudge();           // 判断终端（PC/手机/企微/云之家/纷享App）
    this.env = util.detectEnv();    // 检测环境（浏览器类型/系统）
    this.initTheme();               // 初始化主题
    this._initDom();                // 创建图表容器 DOM
    this.onReplyLibReady(() => {    // 等 echarts 就绪
        this._init();               // → bindEvents() 绑定窗口resize + 点击事件
    });
}
```

**新手解读**：一个统计图先把自己「安顿好」：确定在什么设备上、建好画布容器、绑定好全局事件，然后等 ECharts 脚本加载完再继续。

---

## 3. 步骤 ②：`showDetail()` —— 开始干活（查配置）

文件：`src/core/instance/server.js`（第 106 行）

```js
showDetail: function (opt = {}) {
    if (this.options.chartConfig) {
        // 外部已经直接给了配置 → 跳过查配置，直接查数据
        $.extend(this.chartConfig, this.options.chartConfig);
        this.queryData(opt);
    } else {
        let id = this.options.id || '';
        let isView = this.options.isView === 0 ? 0 : this.options.isView || 1;
        let params = { id, isView, dashboardId: this.getDashboardId() };
        this.setQueryParams(params);
        // 合并查询灰度开关
        this.isMergedQuery = (opt.enableMergedQuery || this.options.enableMergedQuery) && ...;
        if (this.isMergedQuery) {
            new MergedQuery(this).queryMergedAll(opt, params);   // 新路径：一次拉完（见全链路 链路 3）
        } else {
            this.queryChartConfig(opt, params, (options) => {    // 老路径：先配置后数据
                this.queryData(options);
            });
        }
    }
}
```

**queryChartConfig（第 137 行）**——问后端「这个图长什么样」：
```js
queryChartConfig: function (opt = {}, params, cb) {
    let paramsData = $.extend({}, this._addQueryParams(params), { apiName: this.options.objectApiName });
    this.ajax({
        url: this._getQueryChartConfigUrl(),      // → /FHH/EM1HBISTAT/fs-bi-stat/stat/chartConfig/query
        data: paramsData,
        success: async (res, status, xhr) => {
            if (util.isResponseSuccess(res)) {
                // 处理特殊字段（比例类型、switchReportId 等）
                this.chartConfig = ...;           // ★存下配置
                cb && cb(...);                    // 回调 → 去查数据 queryData()
            } else {
                this.renderError('统计图配置不存在...');   // 错误处理
            }
        }
    });
}
```

**新手解读**：`chartConfig` 就是「这张图长什么样」的说明书：图表类型（柱状图/饼图）、维度字段、指标字段、X/Y 轴配置、是否显示表格、是否可下钻……拿到说明书后，才能知道「数据怎么查、怎么画」。

---

## 4. 步骤 ③：`queryData()` —— 查数据（核心）

文件：`src/core/instance/server.js`（第 316 行）

```js
queryData: function (opt = {}, queryParams, isDrillQuery) {
    // 1. 组装查询参数
    if (!queryParams) {
        this.resetPageInfo();
        queryParams = this.getQueryParams(opt.chartType);   // queryParamsObj + 分页 + 图表类型
    }
    // 2. 附加参数：queryLimit、chartType、全局筛选...
    queryParams = {...queryParams, ...onceQueryParams, chartType};

    // 3. 发起请求（第 530 行附近）
    if (需要异步) {
        this.hybridPolling = new HybridPolling({...});      // 异步：发任务+轮询取结果
    } else {
        this.ajax({
            url: this._getQueryChartDataUrl(),   // → /FHH/EM1HBISTAT/fs-bi-stat/stat/data/query
            data: paramsData,
            success: success,                    // 成功回调（见下）
            complete: complete,                  // 结束回调（关loading/记日志）
        });
    }
}

// 成功回调 _success（第 428 行）：
//   util.setGrayConfig(res.Result)    ← 更新灰度开关
//   this.initChartData(res.Value)     ← ★存数据
//   this.destroyChart()               ← 销毁旧图
//   this.render()                     ← ★开始渲染（下一步）
```

**新手解读**：
- `getQueryParams` 把「用户选的筛选条件 + 分页 + 图表类型」打包成后端要的参数。
- `initChartData(res.Value)` 把后端返回的 `dataSet`（行数据）和 `displayFields`（列信息）存到实例上。
- 数据一到手就调用 `render()` 画图。**先配置后数据**的顺序保证了画图时什么信息都有。

**ajax 封装（src/core/instance/ajax.js）**：每次请求都会自动带上
- `traceId`（追踪号：协议+企业+员工+端类型+浏览器，如 `FHH-E.xxx.123-...XMc`）
- `_fs_token`（登录凭证 cookie）
- `accept-language`（语言）
- 请求日志上报（`util.uploadLogBySas`）和耗时监控

---

## 5. 步骤 ④：`render()` —— 渲染调度

文件：`src/xkcharts.js`（第 782 行）

```js
async render() {
    let chartType = this.getChartType();          // 当前图表类型：bar/pie/table/card...
    this.registerTheme(this.getThemeName());      // 注册主题（颜色皮肤）
    if (chartType == 'card') {
        this.renderKpiCard();                     // KPI 卡片
    } else if (chartType == 'table' || chartType == 'pivottable') {
        this.renderTable(true);                   // 表格
    } else {
        await this.getWorldParameter();           // 地图需要的参数
        this.setTableChartCntr();                 // 图表+表格同屏的容器
        this.renderChart();                       // ★普通图表（柱/线/饼/地图...）
        if (需要表格) this.renderTable();
    }
    this.hideLoading();
}
```

**renderChart（第 1147 行）→ renderChartByEcharts（第 1071 行）→ _renderChartByEcharts（第 1118 行）**：
```js
_renderChartByEcharts() {
    this.createMyChart();                 // echarts.init($container, themeName) 创建 ECharts 实例
    this.adaptDataForEcharts();           // ★按图表类型选 adapter（翻译官）
    this.chartOption = util.resetLegendForFieldStatus(...);
    this.setOption(this.chartOption);     // myChart.setOption() 真正绘制
    this.bindChartEvents();               // 绑定图例点击/鼠标事件
    this.resize();                        // 自适应尺寸
}
```

**新手解读**：`render()` 像「路由器」，根据图表类型把活分给不同部门：卡片、表格、普通图表各走各的。普通图表最终都由 ECharts 画出来。

---

## 6. 步骤 ⑤：`adaptDataForEcharts()` —— 选翻译官（adapter）

文件：`src/xkcharts.js`（第 1156 行）

```js
adaptDataForEcharts: function () {
    var chartType = this.getChartType();
    switch (chartType) {
        case 'bar': case 'line': case 'doubley':
            this.adapter = new BarLineAdapter({ xkcharts: this });   // 柱/线/双轴
            break;
        case 'pie':
            this.adapter = new PieAdapter({ xkcharts: this });
            break;
        case 'maphot': case 'mapbubble': case 'worldhot': case 'worldbubble':
            this.adapter = new WorldHotAdapter / WorldAdapter / MapAdapter...
            break;
        // ... gauge/radar/funnel/scatter/treemap/butterfly 各有各的 adapter
    }
}
```

**adapter 的 translate()（以柱线图为例，src/adapter/bar-line.js 第 30 行）**：
```js
translate() {
    this.chartConfig = this.xkcharts.getChartConfig();
    let xAxis = this.getXAxisObj();        // X 轴（维度）
    let yAxis = this.getYAxisObj();        // Y 轴（指标）
    this.theOption = {
        title: this.getTitle(),
        xAxis: xAxis,
        yAxis: yAxis,
        legend: this.getLegend(),          // 图例
        tooltip: this.getTooltip(),        // 悬浮提示
        series: this.getSeries(),          // 数据系列（核心）
        ...
    };
    $.extend(this.xkcharts.chartOption, this.theOption);   // 写回实例的 chartOption
}
```

**新手解读**：adapter 是「翻译官」：后端给的是统一的 `chartConfig + dataSet`，但 ECharts 要的是 `xAxis/yAxis/series` 这种结构。每种图翻译方式不同（饼图没有 X/Y 轴，地图要经纬度），所以每种图一个 adapter。**想改某类图的样式，改对应 adapter 文件即可。**

---

## 7. 步骤 ⑥：交互（下钻 / 查看明细 / 联动）

数据画出来只是开始，用户还会点击。点击事件在 `src/core/instance/events.js`：

```js
this.myChart.on('click', params => {
    // 1. 判断能不能下钻（canDrill）、联动（linkageStatus）、跳转 CRM 详情
    // 2. 组装维度值
    // 3. this.newDrillObj.initDrill(params)   ← 下钻（src/render/new-drill.js 第 88 行）
    //      → getSchemaDrillFields() 问后端可下钻字段
    //      → queryData() 重新查更细的数据 → render() 重画
    // 4. 或 this.seeDetail 弹出明细（src/render/see-detail.js）
    //      → 请求 /EM1HBICRM/statDetailController/queryStatToDetailInfo
});
```

**新手解读**：下钻 = 点柱子看下一层；明细 = 点数字看清单；联动 = 点一个图，别的图跟着变。这些交互最终都会「改查询参数 → 重新走 queryData → render」，所以链路 2~5 是复用核心。

---

## 8. 实践验证（自己动手）

1. 打开仓库，按 `npm install` + `npm run serve`（端口 9966）启动预览站点 `preview/`。
2. 在 `preview/views` 找一个示例页面，看它怎么 `new BIXkcharts({...})` 传参。
3. 浏览器 F12 → Network，过滤 `stat/chartConfig` 和 `stat/data`，就能看到链路 2 的两次请求。
4. 在 `src/core/instance/server.js` 的 `showDetail` 和 `queryData` 里打断点（或 `debugger`），刷新页面看执行顺序。
5. 在 `src/adapter/bar-line.js` 的 `translate()` 里打断点，看 `this.theOption` 是怎么拼出来的——这就是 ECharts 要的 option。

---

## 9. FAQ（常见问题）

**Q1：为什么一个统计图要请求两次（配置 + 数据）？**
答：后端把「配置」和「数据」分开存/算。配置查得快、数据算得慢；而且切换图表类型（柱↔线）时只换配置不用重新算数据。新版合并查询（链路 3）已把两者合并成一次请求（灰度中）。

**Q2：前端的数据是从哪里来的？**
答：全部来自后端 HTTP 接口（fs-bi 等），前端不存数据、不算数。前端只是「把参数传过去，把结果画出来」。

**Q3：我想给柱状图加个新样式，改哪里？**
答：`src/adapter/bar-line.js`（柱/线/双轴共用一个适配器）。它负责生成 `xAxis/yAxis/series/legend/tooltip` 这些 option。

**Q4：图不显示了，怎么排查？**
答：① F12 Network 看接口是否报错（看 `res.Error.Code` 和 `FailureMessage`）；② 看 `render()` 里的错误分支（配置不存在/无权限/数据为空/查询异常分别渲染不同提示图）；③ 把请求里的 `traceId` 给后端，后端按 traceId 查日志。

**Q5：为什么改完代码要重启 `npm run dev`？**
答：`npm run dev` 是 watch 模式，改 `src/` 下代码会自动重编译，不用重启；但改 `vue.config.js`、`package.json` 需要重启。另外 Node 版本必须是 10.13.0（volta 锁定），版本不对会启动失败。

**Q6：`from` 和 `scene` 是什么？改错会怎样？**
答：`from` 决定调哪组后端接口（base 门户 / subscription 订阅 / qixin 企信 / board 驾驶舱），`scene` 决定页面行为（PC/H5/编辑/预览）。改错会导致请求打错接口或布局错乱。新接入场景时先找一份已接入页面复制配置。
