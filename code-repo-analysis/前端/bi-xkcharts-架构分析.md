# bi-xkcharts 源码架构分析报告

> 仓库地址：`http://git.firstshare.cn/fe/bi-xkcharts`
> 本地路径：`/Users/muqingji/code/FE/bi-xkcharts`
> 分析日期：2026-08-20

---

# 一、项目概况

- **项目简介**：BI 数据统计系统中的「统计图组件库」（代号 xkcharts），负责把后端算好的统计数据渲染成柱状图、折线图、饼图、漏斗图、地图、KPI 卡片、统计表格等 20+ 种可视化形态，并支持下钻、查看明细、联动、图例交互、主题切换等能力。以 UMD 库形式发布（全局变量 `BIXkcharts`），可被主站、客户端、第三方独立引入。
- **业务领域**：商业智能（BI）数据可视化前端组件。
- **项目类型**：前端组件库（SDK/UMD 库），不是完整应用，也不是微服务。
- **技术栈**：
  - 主框架：Vue 2.6.12（运行时组件用 Vue 挂载）
  - 图表引擎：ECharts（全局 `echarts`，CDN 引入或从 libs 目录异步加载）
  - 其他：jQuery（DOM/事件/AJAX）、underscore、moment、html2canvas、vue-infinite-scroll、bi-mobile-table、fb-ui、crm-core-bi
  - 构建：`@vue/cli-service` 4.5（webpack 4）、Babel、Less
  - 测试：Jest 27
  - 运行环境：Node 10.13.0（volta 锁定，不可升级）、浏览器（PC / H5 / 企微 / 云之家 / 纷享 App）
- **打包方式**：`vue-cli-service build`，webpack 输出 **UMD** 格式（`libraryTarget: 'umd'`，`library: 'BIXkcharts'`），构建产物按 `dev / devo / prod` 模式区分，产物上传 CDN 供各端以 `<script>` 引入。
- **部署方式**：静态资源 CDN 部署（`publicPath: '__PUBLIC_PATH__'` 构建时替换）；仓库内 `preview/` 是本地预览站点（端口 9966）。
- **容器化**：无 Docker；CI 走 GitLab CI（`.gitlab-ci.yml`）。

---

# 二、整体系统架构

1. **架构模式**：经典的前端「组件库 + 插件化适配」模式。
   - 分层：宿主环境（页面/门户）→ 库入口 `BIXkcharts` 实例 → 核心内核（core）→ 图表适配器（adapter）→ 公共组件（components）→ 渲染引擎（ECharts/Canvas Table）。
   - 实例是「一个统计图一个实例」：`new BIXkcharts(options)` 生成一个图表实例，`options` 决定场景、图表 id、查询参数、回调钩子。
2. **服务拆分**：不涉及服务拆分；依赖外部后端服务（HTTP JSON 接口）：
   - `fs-bi-stat`（统计图配置/数据查询，`/FHH/EM1HBISTAT/fs-bi-stat/stat/...`）
   - `fs-bi-crm-report`（老门户统计图/明细接口，`/EM1HBICRM/...`）
   - `fs-bi-udf-report`（销售过程/目标等定制图，`/EM1HBIUDF/...`）
3. **外部依赖**：
   - 全局对象：`$`（jQuery）、`Vue`、`Fx`、`FS`、`$t`、`echarts`、`_`（underscore）、`seajs`、`biPluginManager`、`window.BI.util.FHHApi`（统一 API 调用）、`window.Fx.util.decryptRes`（响应解密）
   - 跨项目组件：`seajs.use('bi-modules/...')` 动态加载外部组件（如 xktable），详见 `docs/third-party-dependency-index.md`
4. **请求整体流转**（典型统计图）：
   ```
   页面/门户 引入 BIXkcharts → new BIXkcharts({id, $el, from, scene, queryParamsObj...})
   → 实例 init() → 建 DOM 容器 → bindEvents()
   → showDetail() →（默认）queryChartConfig() 拉配置 → queryData() 拉数据
     （合并查询灰度下）→ MergedQuery.queryMergedAll() 一次拉 配置+数据+筛选
   → initChartData() 存数据 → render() 渲染
   → renderChartByEcharts() → echarts.init() → adapter.translate() 生成 option → 绘制
   → 用户交互（图例/点击）→ events.js 分发 → 下钻/明细/联动 → 重新 queryData()
   ```

---

# 三、目录结构详细解析

```
bi-xkcharts/
├── src/                         # 源码主目录
│   ├── xkcharts.js              # ★库入口（2307 行）：构造函数 + 全部原型方法 + 组件注册
│   ├── core/                    # 内核：实例能力（通过 initMixin 注入原型）
│   │   ├── config.js            # 图表类型字典（CHART_TYPES）、CDN/地图 JSON 地址
│   │   ├── gray.js              # 灰度开关
│   │   ├── table.js             # 表格渲染 mixin（renderTable、透视表、排序）
│   │   ├── sample-img.js        # 示例图
│   │   ├── global-api/index.js  # 全局 API（util、toast、alert、showTextViewer）
│   │   └── instance/            # 实例能力模块（每个文件一个 initXxx）
│   │       ├── init.js          # initMixin 汇总入口
│   │       ├── server.js        # ★数据请求核心：showDetail/queryChartConfig/queryData/异步查询
│   │       ├── merged-query.js  # ★合并查询（配置+数据+筛选 一个接口）
│   │       ├── ajax.js          # ★ajax 封装：traceId、cookie、缓存、日志、FHHApi
│   │       ├── render.js        # 渲染辅助：loading/空态/错误态 DOM
│   │       ├── events.js        # ★事件：bindEvents、图表点击、下钻/明细分发
│   │       ├── theme.js         # 主题注册（echarts.registerTheme）
│   │       ├── resize.js        # 自适应尺寸（window resize、表格/图表联动缩放）
│   │       ├── calc.js / sort.js / pagination.js / scene.js / map.js / image.js
│   │       ├── tooltip.js / random-tooltip.js / axis-mark/（轴线标记）
│   │       ├── plugin-service.js / registry-comps.js（组件注册表）
│   │       └── map-core/        # 地图内核（maphot 热力/worldhot/worldbubble/mapbubble）
│   ├── adapter/                 # ★图表适配器：把 chartConfig+data 翻译成 ECharts option
│   │   ├── base.js              # 适配器基类
│   │   ├── bar-line.js          # 柱形图/折线图/双轴图适配器（最核心）
│   │   ├── pie.js / funnel/ / gauge/ / radar/ / scatter.js / treemap/
│   │   ├── map.js / world/      # 中国地图/国际地图
│   │   ├── butterfly/           # 蝴蝶图
│   │   └── __tests__/           # 适配器单测
│   ├── components/              # ★公共组件（Vue 组件 + 类组件）
│   │   ├── chart-table/         # 统计表格组件
│   │   ├── canvas-table/        # Canvas 大表 + 透视表（pivot-table）
│   │   ├── customization-table/ # 客户定制报表
│   │   ├── card/src/card.vue    # KPI 卡片
│   │   ├── custom-card/         # 自定义卡片（多布局）
│   │   ├── title/ sub-title/    # 标题/副标题
│   │   ├── last-time/           # 「更新于 xx」时间组件
│   │   ├── average-total/       # 平均/合计
│   │   ├── chart-type-select/   # 图表类型切换器
│   │   ├── world-switch-btn/    # 国际地图切换按钮
│   │   ├── drill-crumbs/ drill-cascader/  # 下钻导航条/级联
│   │   ├── sale-process/ oppo2/ # 销售过程/商机定制组件
│   │   ├── heatmap/ stack-bar/ stack-line/  # 堆叠图
│   │   ├── alert/ tips/         # 提示组件
│   │   ├── data-manager.js      # 数据管理器（传给组件）
│   │   └── config-manager.js    # 配置管理器
│   ├── render/                  # 交互渲染
│   │   ├── new-drill.js         # ★下钻实现（initDrill、getSchemaDrillFields、钻取导航）
│   │   └── see-detail.js        # ★查看明细弹层
│   ├── mixins/wechat/           # 企业微信 mixin
│   ├── util/                    # 工具函数
│   │   ├── util.js              # ★大工具集（2382 行）：环境判断/格式化/字段处理/i18n
│   │   ├── helpers.js / tool.js / text-size.js / base64.js / pagination.js
│   │   ├── aggrtype.js / field.js / goal-util.js / util-wechat.js
│   │   ├── hybrid-polling.js    # ★异步查询轮询工具
│   │   ├── monitor-service.js   # 监控埋点
│   │   └── theme-util/          # 主题工具
│   ├── assets/                  # 样式（xkcharts.less）、图片、主题（@theme）
│   └── polyfill/                # size polyfill
├── preview/                     # 本地预览站点（examples/views，端口 9966）
├── libs/                        # 第三方库（vendor-source/world-source）
├── docs/                        # 文档（third-party-dependency-index.md 依赖索引）
├── tools/                       # 工具脚本（predev-check、i18n-update、测试）
├── jest/                        # 测试基建（setup-globals.js 全局 mock）
├── public/                      # 静态资源
├── vue.config.js                # webpack 配置（UMD 输出、路径别名）
├── package.json                 # 依赖与脚本（serve 9966 / dev / build / test）
├── .gitlab-ci.yml               # CI 配置
└── PLAN.md / README.md          # 规划与说明
```

**区分**：业务代码（src/，占绝大多数）、公共组件（src/components）、配置（src/core/config.js、vue.config.js）、工具（src/util）、单元测试（src/**/__tests__、jest/）、脚本（tools/）、静态资源（src/assets、public）。

---

# 四、代码模块详细构成

1. **核心业务模块**：
   - 实例内核（src/core/instance/*）：初始化、数据请求、渲染调度、事件、主题、自适应、分页、地图。
   - 图表适配器（src/adapter/*）：每种图表一个适配器，把「配置+数据」翻译成 ECharts option（含 X/Y 轴、图例、tooltip、series、markLine 等）。
   - 表格（src/core/table.js + components/chart-table、canvas-table）：统计表/透视表/Canvas 大表渲染。
   - 交互（src/render/*）：下钻、查看明细、联动。
   - 组件（src/components/*）：标题、时间、卡片、切换器、导航条等 UI 件。
2. **公共基础模块**：
   - 工具：src/util/util.js（环境检测、字段/指标处理、格式化、cookie、i18n `$t`）
   - 常量：src/core/config.js（CHART_TYPES）
   - 全局 API：src/core/global-api/index.js（`BIXkcharts.util`、`toast`、`alert`）
   - 事件：实例 `on/off/trigger`（events.js），组件用 `event-emitter.js`
   - 日志/监控：util-logger.js、monitor-service.js（耗时、埋点、`util.uploadLogBySas`）
3. **数据层设计**：
   - 无本地数据库；数据全部来自后端 HTTP JSON（见第二章接口列表），前端只做「查询参数组装 → 请求 → 结果缓存（可选内存缓存 ajaxCacheConfig）→ 渲染」。
   - 地图数据：china.json / world.json 从 CDN 加载。
   - 缓存：`window.xkcharts.ajaxCacheData`（内存缓存，默认关闭）。
4. **权限/认证/鉴权**：前端不直接做鉴权；请求带 `fs_token`（cookie）与 `traceId`，后端校验；无权限时后端返回错误码，前端 `renderWhenNoQueryPermission()` 渲染「暂无查看权限」。

---

# 五、用到的全部框架 & 第三方组件清单

| 组件 | 作用 |
| --- | --- |
| Vue 2.6.12 | 运行时组件（表格、卡片、弹层）的挂载与渲染 |
| ECharts（全局） | 所有统计图的绘制引擎 |
| jQuery（全局 $） | DOM 操作、事件绑定、AJAX 请求 |
| underscore（全局 _） | 工具函数 |
| moment 2.29.1 | 日期格式化 |
| html2canvas 1.4.1 | 图表截图（导出图片） |
| vue-infinite-scroll 2.0.2 | 表格滚动加载 |
| bi-mobile-table 2.0.7 | 移动端表格 |
| fb-ui 1.3.9 | 基础 UI |
| crm-core-bi 0.0.1 | BI 公共能力 |
| @tools/i18n2 | 国际化 |
| Fx / FS（全局） | 宿主平台能力（主题色、提示、API 调用 FHHApi、响应解密 decryptRes） |
| biPluginManager / seajs | 跨项目组件动态加载（bi-modules 等） |
| AxisMark（自研） | 轴线标记（markLine） |

---

# 六、核心业务流程拆解

**典型统计图加载流程（文字流程图）**：

```
宿主页面
  └─ new BIXkcharts(options)                     ← xkcharts.js:56 构造函数
       ├─ 合并默认 options（id/$el/from/scene/queryParamsObj/接口 URL）
       ├─ 若外部传 chartConfig/chartData 则直接使用
       └─ this.init()                            ← xkcharts.js:211
            ├─ 终端/环境检测（detectEnv）
            ├─ 初始化主题、DOM 容器（renderCntr）
            └─ onReplyLibReady() → _init() → bindEvents()（窗口 resize + 点击）
  └─ 宿主调用 showDetail(opt)                    ← server.js:106
       ├─ 有 chartConfig → 直接 queryData()
       ├─ 合并查询灰度 → MergedQuery.queryMergedAll()（一次拉 配置+数据+筛选）
       └─ 默认 → queryChartConfig()（server.js:137）
            └─ ajax POST /stat/chartConfig/query → 得到 chartConfig
                 └─ queryData()（server.js:316）
                      ├─ 组装查询参数（getQueryParams：筛选/分页/图表类型）
                      ├─ ajax POST /stat/data/query（或异步 sendQueryDataUrl+loadQueryDataUrl）
                      ├─ 成功 → initChartData(res.Value) → render()
                      └─ render()（xkcharts.js:782）
                           ├─ registerTheme() 注册主题
                           ├─ card → renderKpiCard()；table → renderTable()；其他 → renderChart()
                           └─ renderChartByEcharts()（xkcharts.js:1071）
                                → echarts.init($container, themeName)
                                → 实例化 adapter（如 BarLinedapter.translate()，adapter/bar-line.js）
                                → 生成 option → myChart.setOption() → 绘制
  └─ 用户点击柱形/单元格
       └─ events.js 点击回调 → newDrillObj.initDrill()（new-drill.js:88）
            ├─ getSchemaDrillFields() 请求可下钻字段 → 下钻查询 queryData()
            └─ 或 SeeDetail.show()（see-detail.js）查看明细弹层
```

**关键接口/函数执行逻辑**：`showDetail` 是「查配置→查数据→渲染」的总入口；`queryData` 是数据查询核心（含异步轮询 HybridPolling 分支）；`render` 是渲染调度（按图表类型分流）；`adapter.translate` 是 ECharts option 的组装点。

---

# 七、配置与环境

- **配置文件**：`vue.config.js`（构建）、`.eslintrc.js`（lint）、`.prettierrc`（格式）、`jest.config.js`（测试）、`babel.config.js`（转译）。
- **运行配置**：全部通过 `new BIXkcharts(options)` 传入（无独立配置文件）：`from`（接口分组 base/subscription/qixin/board/dht）、`scene`（pc_edit/pc_prev/pc_detail/pc_board/h5_board/h5_detail 等）、`styleId`（驾驶舱配色）、`queryParamsObj`（查询参数）、各接口 URL、超时、缓存、loading、下钻开关 `canDrill` 等。
- **多环境**：`npm run dev`（开发）/ `devo`（联调）/ `build`（生产），通过 `BUILD_TYPE` 与 `NODE_ENV` 区分；`process.env.cdn`、`VUE_APP_VERSION`、`VUE_APP_CACHE_VERSION` 等环境变量。
- **启动参数**：`npm run serve` 端口 9966；构建产物 `__PUBLIC_PATH__` 运行时替换 CDN 前缀。
- **灰度**：`src/core/gray.js` + 后端返回的 `grayConfig`（`util.setGrayConfig`）控制功能开关。

---

# 八、项目优缺点 & 风险点

**优点**
- 组件化 + 适配器模式：新增图表类型只需新增 adapter，扩展性好。
- 与业务解耦：纯前端库，后端只给 JSON，可被主站/客户端/第三方复用。
- 场景化配置（from/scene）覆盖 PC、H5、企微、驾驶舱、订阅等大量场景。
- 完善的错误/空态/loading/无权限渲染与监控埋点。

**现存问题 / 技术债务**
- 单文件过大：`src/xkcharts.js` 2307 行承担构造函数+全部原型方法，维护成本高。
- 全局依赖过多：直接依赖 `window.jQuery/Vue/echarts/Fx/FS/_/seajs` 等全局变量，测试与独立引入成本高。
- 老代码兼容负担：大量「历史 bug 兼容分支」「老逻辑暂时不动」注释，且使用 jQuery 拼 HTML 字符串渲染（XSS 风险点）。
- Vue 2.6 + Node 10 已停止维护，依赖版本老。

**接手改造注意事项**
- 严禁升级 Node（volta 锁定 10.13.0）、禁止引入 Node 12+ 语法到工具脚本。
- 改第三方依赖映射需同步 `docs/third-party-dependency-index.md`。
- 动 DOM 渲染（v-html/HTML 拼接）注意 XSS 防护（AGENTS.md 安全注意）。
- 新增测试先看 `jest/setup-globals.js` 的全局 mock 约定。

---

# 九、需要补充核查的内容

- 后端接口契约：`/stat/chartConfig/query`、`/stat/data/query`、`/stat/chart/query`（合并）的请求/响应字段文档缺失，需对照 fs-bi 后端源码（fs-bi-stat 模块）确认。
- `window.BI.util.FHHApi`、`Fx.util.decryptRes` 等宿主能力由外部平台注入，本仓库无实现，需向平台团队确认行为。
- 生产 CDN 地址、各环境 `__PUBLIC_PATH__` 替换值缺失。
- `PLAN.md`（220KB）为历史规划文档，是否仍有效需确认。
- 部分图表类型（sales-process、oppo2、customization-table）为特定业务定制，通用性有限。

---

# 十、代码走读路线（入口 → 渲染 → 后端接口，最完整力度）

**路线 A：统计图「加载 → 查数据 → 渲染」全链路（推荐第一条）**
1. `src/xkcharts.js:56` 构造函数（`new BIXkcharts(options)`）
2. `src/xkcharts.js:211` `init()`（环境/主题/DOM）
3. `src/core/instance/events.js:6` `bindEvents()`
4. `src/core/instance/server.js:106` `showDetail()`
5. `src/core/instance/server.js:137` `queryChartConfig()` → 后端 `/FHH/EM1HBISTAT/fs-bi-stat/stat/chartConfig/query`
6. `src/core/instance/server.js:316` `queryData()` → 后端 `/FHH/EM1HBISTAT/fs-bi-stat/stat/data/query`
7. `src/xkcharts.js:782` `render()`
8. `src/xkcharts.js:1071` `renderChartByEcharts()` → `src/xkcharts.js:1113` `createMyChart()`（echarts.init）
9. `src/adapter/bar-line.js` `translate()`（生成 option）→ `myChart.setOption()` 绘制
10. 对应后端：fs-bi 统计图数据链路（见《[全链路走读-fs-bi.md](../后端/全链路走读-fs-bi.md)》链路 3/4）

**路线 B：合并查询链路（灰度新路径）**
`server.js:106 showDetail()` → `src/core/instance/merged-query.js:19 queryMergedAll()` → `executeSyncRequest()`（merged-query.js:249）→ 后端 `/FHH/EM1HBISTAT/fs-bi-stat/stat/chart/query`（对应 fs-bi 链路 3）

**路线 C：下钻/查看明细**
`events.js` 点击回调 → `src/render/new-drill.js:88 initDrill()` → `getSchemaDrillFields()`（new-drill.js:278，后端 `/EM1HBICRM/statChartController/getSchemaDrillFields`）→ `queryData()` 重新查询；明细见 `src/render/see-detail.js`（后端 `/EM1HBICRM/statDetailController/queryStatToDetailInfo`）
