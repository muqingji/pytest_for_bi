# MySQL 业务线

按业务含义查找 `fx-ops idp query <biz>`。**各 biz 表级筛选** 见 [index.md](./mysql/index.md)。

> 2026-08-07 起：原 MySQL 的 open/wechat 系多已迁 PostgreSQL 并合并。**禁止**再使用
> `open-oauth`、`open-link-app`、`wechat-proxy`、`wechat-notice`、`wechat-union`(mysql)、`open-qywx`。
> 对应入口见 [postgresql.md](./postgresql.md) 的 `openapi` / `enterprise-relation`，以及本方言 `open-yunzhijia`。

当前平台 **MySQL live biz 共 12 个**，均为 `routeMode=fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint）。以 `show datasources` 为准。

| biz 命令 | 说明 | 筛选文档 |
| --- | --- | --- |
| `cross-notice` | 互联通知公告（库 `open_material`；勿用 Mongo `open-material`） | [cross-notice.md](./mysql/cross-notice.md) |
| `open-sail` | 售后服务，工单、派工、SLA、知识库 | [open-sail.md](./mysql/open-sail.md) |
| `online-consult` | 在线客服，会话、分配、快捷回复 | [online-consult.md](./mysql/online-consult.md) |
| `call-center` | 呼叫中心、外呼、ASR、电话营销 | [call-center.md](./mysql/call-center.md) |
| `mail` | 邮件收发、规则、CRM 邮件沉淀 | [mail.md](./mysql/mail.md) |
| `job-center` | 数据导入导出异步任务 | [job-center.md](./mysql/job-center.md) |
| `paas-crm-biz` | CRM 企业信息、线索、付费租户 | [paas-crm-biz.md](./mysql/paas-crm-biz.md) |
| `open-message` | 设备消息通知、设备状态（**双方言**，须 `--dialect mysql`） | [open-message.md](./mysql/open-message.md) |
| `open-app-center` | 应用中心、模板、可见性 | [open-app-center.md](./mysql/open-app-center.md) |
| `open-app-pay` | 应用付费、额度、企业付费 | [open-app-pay.md](./mysql/open-app-pay.md) |
| `open-yunzhijia` | 云之家组织架构同步、通讯录绑定 | [open-yunzhijia.md](./mysql/open-yunzhijia.md) |
| `paas-template` | PaaS 模板配置 | [paas-template.md](./mysql/paas-template.md) |

## 已废弃旧名（重定向）

| 旧名 | 新入口 |
| --- | --- |
| `open-oauth` | `openapi`（postgresql） |
| `open-link-app` / `wechat-proxy` / `wechat-notice` / `wechat-union`(pg) | `enterprise-relation --dialect postgresql` |
| `open-qywx` | `open-yunzhijia`（mysql） |

## 相关文档

- [业务线总览](index.md)
- [表级筛选索引](./mysql/index.md)
- [filterHint 拼 SQL](../../idp-query-filter-hint.md)
- [SQL 查询规则](../../idp-query-sql.md)
