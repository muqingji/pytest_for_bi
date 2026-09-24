# link-enterprise-relation-biz

**方言**: `postgresql` 
**说明**: 企业关系渠道登录注册配置，管理域名索引、导航、登录会话及注册布局 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns link-enterprise-relation-biz <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query link-enterprise-relation-biz`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables link-enterprise-relation-biz --dialect postgresql -j
fx-ops idp --profile <profile> show columns link-enterprise-relation-biz <table> --dialect postgresql -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query link-enterprise-relation-biz --sql "<SQL>" -j
```

## 统计

- 表级筛选条目: **9**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **9**
- 使用 `$tenant_account` / EA: **0**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `er_channel_domain_index` | tenant_id | `create_time` | `tenant_id`=$tenant_id |
| `er_channel_h5_login_template` | tenant_id | `create_time` | `tenant_id`=$tenant_id |
| `er_channel_login_template` | tenant_id | `create_time` | `tenant_id`=$tenant_id |
| `er_channel_navigation` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `er_login_session` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `login_register_config` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `login_register_layout_config` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `portal_site_login_register_config_association` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `site_miniprogram_bind` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
