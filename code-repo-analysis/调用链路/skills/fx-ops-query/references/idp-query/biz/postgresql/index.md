# POSTGRESQL 业务线筛选索引

各 biz 表级筛选与字段说明。通用拼 SQL 规则见 [idp-query-filter-hint.md](../../../idp-query-filter-hint.md)。

> live 清单以 `fx-ops idp show datasources` 为准（当前 21 个）。

| biz | 文档 |
| --- | --- |
| `bi` | [bi](./bi.md)（双方言，须 `--dialect postgresql`） |
| `bi-system` | [bi-system](./bi-system.md) |
| `enterprise-relation` | [enterprise-relation](./enterprise-relation.md)（双方言，须 `--dialect postgresql`） |
| `feed` | [feed](./feed.md)（工作圈主库；勿默认用 paas 查 `fd_*`） |
| `hospital-spider` | [hospital-spider](./hospital-spider.md) |
| `link-eip-data-sync` | [link-eip-data-sync](./link-eip-data-sync.md)（双方言，须 `--dialect postgresql`） |
| `link-eip-data-sync-1` | [link-eip-data-sync-1](./link-eip-data-sync-1.md)（独立库，非 dialect） |
| `link-eip-data-sync-747125` | [link-eip-data-sync-747125](./link-eip-data-sync-747125.md)（独立库，非 dialect） |
| `link-enterprise-relation-biz` | [link-enterprise-relation-biz](./link-enterprise-relation-biz.md) |
| `link-erp-data-sync` | [link-erp-data-sync](./link-erp-data-sync.md) |
| `link-mankeep` | [link-mankeep](./link-mankeep.md) |
| `metadata-option` | [metadata-option](./metadata-option.md) |
| `metadata-recycle` | [metadata-recycle](./metadata-recycle.md) |
| `oncall` | [oncall](./oncall.md) |
| `openapi` | [openapi](./openapi.md) |
| `outer-oa` | [outer-oa](./outer-oa.md) |
| `paas` | [paas](./paas.md) |
| `paas-i18n` | [paas-i18n](./paas-i18n.md) |
| `paas-license` | [paas-license](./paas-license.md) |
| `paas-nomon` | [paas-nomon](./paas-nomon.md) |
| `tenant-router` | [tenant-router](./tenant-router.md) |

## 已废弃 / 非 live

| 名称 | 文档 |
| --- | --- |
| `link-enterprise-relation` | [link-enterprise-relation](./link-enterprise-relation.md) → `enterprise-relation` |
| `eip-data-sync` | [eip-data-sync](./eip-data-sync.md) → `link-eip-data-sync` |
| `paas-function` | [paas-function](./paas-function.md)（curated / 非 idp biz） |
