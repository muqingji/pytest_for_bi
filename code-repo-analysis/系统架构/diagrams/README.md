# BI 架构流程图

> 每张图都在**流程图上方**附有「节点是什么 / 起什么作用」讲解。

| 图 | HTML（推荐浏览器打开） | Markdown |
| --- | --- | --- |
| 平台架构 | [BI-平台架构流程图.html](./BI-平台架构流程图.html) | [BI-平台架构流程图.md](./BI-平台架构流程图.md) |
| 整体系统 | [BI-整体系统架构流程图.html](./BI-整体系统架构流程图.html) | [BI-整体系统架构流程图.md](./BI-整体系统架构流程图.md) |

## 打开方式

```bash
open "/Users/liushanshan/code/QA/bug-finder/output/BI-platform-architecture-20260825/diagrams/BI-整体系统架构流程图.html"
open "/Users/liushanshan/code/QA/bug-finder/output/BI-platform-architecture-20260825/diagrams/BI-平台架构流程图.html"
```

需联网加载 Mermaid CDN。

## 图清单与讲解覆盖

### 整体系统
1. 全景主图（三侧+存储）
2. 读路径出图时序
3. **写路径数据生产**（含业务 PG / copier / CH / MQ / DWS / StatView / fs-bi-stat 逐项讲解）
4. 门户编排
5. 配置驱动数仓计算

### 平台架构
1. L1–L6 分层主图
2. 控制面 / 数据面 / 体验面
