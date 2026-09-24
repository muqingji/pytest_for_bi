# PostgreSQL 业务线

按业务含义查找 `fx-ops idp query <biz>`。**各 biz 表级筛选** 见 [index.md](./postgresql/index.md)。

> 2026-08-07：`openapi`（含原 `open-oauth`）与 `enterprise-relation`（含原 5 个 open/wechat 同库 biz）为合并后正式入口。

当前平台 **PostgreSQL live biz 共 21 个**。`routeMode=fixed` 的 biz（多数）免传 `--tenant-id`；
`paas` / `bi` / `feed` 等为 `tenant-route`，**必填** `-t`。以各 biz 文档「路由」行为准；数量以 `show datasources` 为准。

| biz 命令 | 说明 | 筛选文档 |
| --- | --- | --- |
| `paas` | PaaS 核心，元数据、对象、数据权限 | [paas.md](./postgresql/paas.md) |
| `link-mankeep` | CRM 核心，客户、营销、商机线索 | [link-mankeep.md](./postgresql/link-mankeep.md) |
| `bi` | BI 分析（**多方言**，须 `--dialect postgresql`；执行用 `bi-postgresql`） | [bi.md](./postgresql/bi.md) · [总览](./bi.md) |
| `bi-system` | BI 引擎，元数据拓扑、聚合规则、调度 | [bi-system.md](./postgresql/bi-system.md) |
| `feed` | 工作圈主库；勿默认用 paas 查 `fd_*` | [feed.md](./postgresql/feed.md) |
| `hospital-spider` | 医疗主数据（医院/科室/医生；无租户模板） | [hospital-spider.md](./postgresql/hospital-spider.md) |
| `link-erp-data-sync` | ERP 同步配置、策略、字段映射 | [link-erp-data-sync.md](./postgresql/link-erp-data-sync.md) |
| `link-eip-data-sync` | EIP 同步策略库（**双方言**，须 `--dialect postgresql`） | [link-eip-data-sync.md](./postgresql/link-eip-data-sync.md) · [总览](./link-eip-data-sync.md) |
| `link-eip-data-sync-1` | EIP instance1 独立库 `eip_data_sync_1`（非 dialect） | [link-eip-data-sync-1.md](./postgresql/link-eip-data-sync-1.md) |
| `link-eip-data-sync-747125` | EIP 大客户 747125 独立库（非 dialect） | [link-eip-data-sync-747125.md](./postgresql/link-eip-data-sync-747125.md) |
| `enterprise-relation` | 企业关系/微信/关联应用/名片（**双方言**，须 `--dialect postgresql`） | [enterprise-relation.md](./postgresql/enterprise-relation.md) |
| `link-enterprise-relation-biz` | 企业关系渠道、域名、导航、登录会话（**未**合并） | [link-enterprise-relation-biz.md](./postgresql/link-enterprise-relation-biz.md) |
| `openapi` | 开放平台 API + OAuth（库 `openapi_platform`） | [openapi.md](./postgresql/openapi.md) |
| `outer-oa` | 外部 OA（企微/钉钉/飞书）绑定与配置 | [outer-oa.md](./postgresql/outer-oa.md) |
| `tenant-router` | 租户路由元数据 | [tenant-router.md](./postgresql/tenant-router.md) |
| `metadata-option` | 元数据选项及关联关系 | [metadata-option.md](./postgresql/metadata-option.md) |
| `metadata-recycle` | 元数据回收站 | [metadata-recycle.md](./postgresql/metadata-recycle.md) |
| `paas-i18n` | 国际化词条、本地化场景 | [paas-i18n.md](./postgresql/paas-i18n.md) |
| `paas-nomon` | 数据库监控、扫描任务、执行日志 | [paas-nomon.md](./postgresql/paas-nomon.md) |
| `oncall` | 告警/路由/值班 | [oncall.md](./postgresql/oncall.md) |
| `paas-license` | 许可证（以 table get 为准） | [paas-license.md](./postgresql/paas-license.md) |

## 已废弃旧名

| 旧名 | 新入口 |
| --- | --- |
| `link-enterprise-relation` | `enterprise-relation --dialect postgresql` |
| `open-oauth` / MySQL openapi | `openapi` |
| `eip-data-sync` / `eip_data_sync` / `syncdata` | **`link-eip-data-sync --dialect postgresql`**（独立库用 `-1` / `-747125`） |
| `paas-function` | **非 idp biz**；见 [paas-function.md](./postgresql/paas-function.md) 与 `idp-function.md` |

## 相关文档

- [业务线总览](index.md)
- [表级筛选索引](./postgresql/index.md)
- [filterHint 拼 SQL](../../idp-query-filter-hint.md)
- [SQL 查询规则](../../idp-query-sql.md)
