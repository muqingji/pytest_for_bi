# MYSQL 业务线筛选索引

各 biz 表级筛选与字段说明。通用拼 SQL 规则见 [idp-query-filter-hint.md](../../../idp-query-filter-hint.md)。

> live 清单以 `fx-ops idp show datasources` 为准（当前 12 个）。下列旧名仅保留重定向 stub，**禁止**当作 live biz 查询。

| biz | 文档 |
| --- | --- |
| `call-center` | [call-center](./call-center.md) |
| `cross-notice` | [cross-notice](./cross-notice.md) |
| `job-center` | [job-center](./job-center.md) |
| `mail` | [mail](./mail.md) |
| `online-consult` | [online-consult](./online-consult.md) |
| `open-app-center` | [open-app-center](./open-app-center.md) |
| `open-app-pay` | [open-app-pay](./open-app-pay.md) |
| `open-message` | [open-message](./open-message.md)（双方言：mysql + mongodb） |
| `open-sail` | [open-sail](./open-sail.md) |
| `open-yunzhijia` | [open-yunzhijia](./open-yunzhijia.md) |
| `paas-crm-biz` | [paas-crm-biz](./paas-crm-biz.md) |
| `paas-template` | [paas-template](./paas-template.md) |

## 已废弃（重定向 stub）

| 旧名 | 文档 |
| --- | --- |
| `open-link-app` | [open-link-app](./open-link-app.md) → `enterprise-relation` |
| `open-oauth` | [open-oauth](./open-oauth.md) → `openapi` |
| `open-qywx` | [open-qywx](./open-qywx.md) → `open-yunzhijia` |
| `wechat-notice` | [wechat-notice](./wechat-notice.md) → `enterprise-relation` |
| `wechat-proxy` | [wechat-proxy](./wechat-proxy.md) → `enterprise-relation` |
| `wechat-union` (mysql 文档) | [wechat-union](./wechat-union.md) → PG 合并；mongo 见 mongodb |
