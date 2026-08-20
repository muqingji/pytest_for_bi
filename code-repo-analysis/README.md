# BI 代码仓库源码解读文档总索引

本目录收录 BI 业务域 **后端（serve）**、**大数据（Data）**、**前端（FE）** 共 6 个代码仓库的源码解读文档。每个仓库按三种格式各出一份文档：

| 格式 | 文件命名 | 内容定位 |
| --- | --- | --- |
| 架构分析 | `xxx-架构分析.md` | 资深架构师视角：项目概况 / 整体架构 / 目录结构 / 模块构成 / 框架清单 / 核心流程 / 配置环境 / 优缺点风险 / 待核查项 / 代码走读路线 |
| 全链路走读 | `全链路走读-xxx.md` | 每个仓库 10 条主链路，从 API 接口文件 → 方法 → 服务层 → 最底层数据层 / RPC / MQ，附文件路径 + 行号 + 方法名；跨仓库调用附对方仓库接收链路 |
| 走读详解 | `走读详解-xxx.md` | 面向代码新手的逐行讲解版：概念速查 + 步骤拆解 + 代码片段 + 实践验证 + FAQ |

> 所有文档中的跨仓库引用均为相对路径链接（如 `../大数据/全链路走读-fs-bi-warehouse.md`），可直接点击跳转。

---

## 一、后端（serve）—— 4 个仓库

| 仓库 | Git 地址 | 本地路径 | 架构分析 | 全链路走读（10 链路） | 走读详解 |
| --- | --- | --- | --- | --- | --- |
| fs-bi（报表/统计图核心） | `git@git.firstshare.cn:bi/fs-bi.git` | `/Users/muqingji/code/serve/fs-bi` | [fs-bi-架构分析.md](后端/fs-bi-架构分析.md) | [全链路走读-fs-bi.md](后端/全链路走读-fs-bi.md) | [走读详解-fs-bi.md](后端/走读详解-fs-bi.md) |
| fs-bi-crm-report（CRM 门户/报表） | `git@git.firstshare.cn:bi/fs-bi-crm-report.git` | `/Users/muqingji/code/serve/fs-bi-crm-report` | [fs-bi-crm-report-架构分析.md](后端/fs-bi-crm-report-架构分析.md) | [全链路走读-fs-bi-crm-report.md](后端/全链路走读-fs-bi-crm-report.md) | [走读详解-fs-bi-crm-report.md](后端/走读详解-fs-bi-crm-report.md) |
| fs-bi-dev-platform（宽表平台） | `git@git.firstshare.cn:bi/fs-bi-dev-platform.git` | `/Users/muqingji/code/serve/fs-bi-dev-platform` | [fs-bi-dev-platform-架构分析.md](后端/fs-bi-dev-platform-架构分析.md) | [全链路走读-fs-bi-dev-platform.md](后端/全链路走读-fs-bi-dev-platform.md) | [走读详解-fs-bi-dev-platform.md](后端/走读详解-fs-bi-dev-platform.md) |
| fs-bi-udf-report（UDF 报表/SQL 引擎） | `git@git.firstshare.cn:dataplatform/fs-bi-udf-report.git` | `/Users/muqingji/code/serve/fs-bi-udf-report` | [fs-bi-udf-report-架构分析.md](后端/fs-bi-udf-report-架构分析.md) | [全链路走读-fs-bi-udf-report.md](后端/全链路走读-fs-bi-udf-report.md) | [走读详解-fs-bi-udf-report.md](后端/走读详解-fs-bi-udf-report.md) |

## 二、大数据（Data）—— 1 个仓库

| 仓库 | Git 地址 | 本地路径 | 架构分析 | 全链路走读（10 链路） | 走读详解 |
| --- | --- | --- | --- | --- | --- |
| fs-bi-warehouse（数仓/ODS 同步 + DWS 聚合计算） | `git@git.firstshare.cn:bi/fs-bi-warehouse.git` | `/Users/muqingji/code/Data/fs-bi-warehouse` | [fs-bi-warehouse-架构分析.md](大数据/fs-bi-warehouse-架构分析.md) | [全链路走读-fs-bi-warehouse.md](大数据/全链路走读-fs-bi-warehouse.md) | [走读详解-fs-bi-warehouse.md](大数据/走读详解-fs-bi-warehouse.md) |

> 重点：用户点名关注的「**DWS 聚合计算链路（RocketMQ 事件 → ClickHouse 聚合）**」见 [全链路走读-fs-bi-warehouse.md](大数据/全链路走读-fs-bi-warehouse.md) 链路 2 和 [走读详解-fs-bi-warehouse.md](大数据/走读详解-fs-bi-warehouse.md)。

## 三、前端（FE）—— 1 个仓库

| 仓库 | Git 地址 | 本地路径 | 架构分析 | 全链路走读（10 链路） | 走读详解 |
| --- | --- | --- | --- | --- | --- |
| bi-xkcharts（统计图组件库） | `git@git.firstshare.cn:fe/bi-xkcharts.git`（Web 端：`http://git.firstshare.cn/fe/bi-xkcharts`） | `/Users/muqingji/code/FE/bi-xkcharts` | [bi-xkcharts-架构分析.md](前端/bi-xkcharts-架构分析.md) | [全链路走读-bi-xkcharts.md](前端/全链路走读-bi-xkcharts.md) | [走读详解-bi-xkcharts.md](前端/走读详解-bi-xkcharts.md) |

---

## 阅读顺序建议

1. **先看架构分析**：建立整体认知（仓库是干什么的、怎么分层、依赖谁）。
2. **再看全链路走读**：挑一条业务链路，按「接口文件 → 方法 → 服务层 → 数据层/RPC/MQ」顺着走一遍，理解一次请求在仓库内外的完整旅程。
3. **最后看走读详解**：对最核心的链路（如统计图出图、DWS 聚合计算）逐行精读。

仓库之间的调用关系（调用链上游 → 下游）：

```
前端 bi-xkcharts ──HTTP──▶ fs-bi-crm-report（门户聚合）
                              │
                              ├──RPC──▶ fs-bi（统计图配置/数据/明细）
                              ├──RPC──▶ fs-bi-udf-report（报表 SQL 引擎/交叉表）
                              ├──RPC──▶ fs-bi-dev-platform（大宽表）
                              └──MQ───▶ fs-bi-warehouse（DWS 视图变更事件）
```

对应推荐阅读顺序：前端 → fs-bi-crm-report → fs-bi → fs-bi-udf-report → fs-bi-dev-platform → fs-bi-warehouse。

## 说明

- 每份文档末尾的「需要补充核查的内容」列出仓库内缺失、需向运维 / 负责人确认的信息（生产配置、DDL、部署拓扑、容器化等）。
- 各仓库的分析日期均为 2026-08-20，基于当前本地源码（master 分支）编写；代码如有更新，行号可能偏移，请以方法名为准。
- 本目录仅整理源码解读文档，不包含任何测试与构建产物。
