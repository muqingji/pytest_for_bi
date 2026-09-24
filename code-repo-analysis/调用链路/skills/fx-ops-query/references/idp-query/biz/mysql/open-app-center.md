# open-app-center

**方言**: `mysql` 
**说明**: 开放应用中心，管理开放应用上下架、应用模板、可见性配置及媒体资源 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns open-app-center <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query open-app-center`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables open-app-center --dialect mysql -j
fx-ops idp --profile <profile> show columns open-app-center <table> --dialect mysql -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query open-app-center --sql "<SQL>" -j
```

## 统计

- 表级筛选条目: **17**
- 复杂筛选（无租户列和/或子查询）: **8**
- 使用 `$tenant_id` / EI: **0**
- 使用 `$tenant_account` / EA: **9**

## 复杂筛选表（优先阅读）

下列表的 **queryTemplate** 为 **子查询/关联** 或未使用单列租户列，
不要写成 `WHERE tenant_id = <EI>`；需用 `tenant get` 得到 **tenantAccount（EA）** 并按模板拼 WHERE。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `app_ea_visible_log` | - | `gmt_create` | `app_id` IN ('FSAID_989ad3') |
| `app_icon` | - | `gmt_modified` | (`app_id` IN ('FSAID_9896e2','FSAID_989ad3','FSAID_989ad4','FSAID_989ad5') OR `app_id` IN (SELECT DISTINCT `component_id` FROM `open_app_component` WHERE `app_id` IN (SELECT DISTINCT `app_id` FROM ... |
| `app_template` | - | `update_time` | `app_id` IN (SELECT DISTINCT `app_id` FROM `open_app` WHERE `app_creater`=$tenant_account) |
| `app_visible` | - | `gmt_create` | `app_id` IN ('FSAID_989ad3') |
| `open_app` | - | `gmt_modified` | (`app_id`='FSAID_989ad3' OR `app_creater`=$tenant_account) |
| `open_app_component` | - | `gmt_modified` | `app_id` IN (SELECT DISTINCT `app_id` FROM `open_app` WHERE (`app_id`='FSAID_989ad3' OR `app_creater`=$tenant_account)) |
| `open_app_scope_order` | - | `gmt_create` | `app_id` IN (SELECT DISTINCT `app_id` FROM `open_app` WHERE (`app_id`='FSAID_989ad3' OR `app_creater`=$tenant_account)) |
| `open_component_url_gray` | - | `gmt_modified` | `app_id` IN (SELECT DISTINCT `app_id` FROM `open_app` WHERE `app_creater`=$tenant_account) |

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `ea_visible` | fs_ea | `gmt_create` | `fs_ea`=$tenant_account |
| `media` | enterprise_account | `update_time` | `enterprise_account`=$tenant_account |
| `media_message` | enterprise_account | `update_time` | `enterprise_account`=$tenant_account |
| `month_activity_ea` | ea | `gmt_create` | `ea`=$tenant_account |
| `open_app_admin` | fs_ea | `gmt_create` | `fs_ea`=$tenant_account |
| `open_customer` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `open_demo_app` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `outer_service_wechat` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `service_dashboard_statistics` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |

## 客开组件（PWC）字段语义

> 源码依据：`git.firstshare.cn/fs-open/fs-open-app-center`（`master`）。用于解读客户自建应用与卡片级客开组件，不必再猜枚举。

### `open_app_component.component_type`

`AppComponentTypeEnum`（`fs-open-app-center-api/src/main/java/com/facishare/open/app/center/api/model/enums/AppComponentTypeEnum.java`）；写入前经 `CustomComponentVO` 调 `getByCode()` 校验：

| 值 | 常量 | 含义 |
| --- | --- | --- |
| 1 | `APP` | app 端 |
| 2 | `WEB` | web 端 |
| 3 | `SERVICE` | 服务号 |
| 4 | `LINK_SERVICE` | 互联服务号 |

同一组件常出现 `1` 与 `2` 两行（app + web 双端发布）；统计组件规模按 `component_id` 去重，勿把端数当组件数。`status = 1` 为启用。

### `open_component_url_gray.gray_json`

结构为 `ComponentUrlGrayJsonVO{loginUrl, fsEaList[]}`（`fs-open-app-center-api/.../vo/ComponentUrlGrayJsonVO.java`），由运营后台按 `componentId` 写入（`fs-open-app-manage` 的 `AppManager#saveOpenComponentUrlGray`），语义是**组件 `loginUrl` 按企业（EA）白名单灰度覆盖**。

该表无记录只代表未配置企业级 URL 灰度，**不能**据此推断组件是纯后端 API，也与环境差异无关。

### 与组件定义库的分工

本库是**发布挂载视角**；组件与插件的真实定义、构建状态在 MongoDB `customer-component`（`ComponentEntity` / `PluginEntity`，`tenantId` 为**数值**，见 [customer-component.md](../mongodb/customer-component.md)）。两侧数量不一致属正常（实测某租户 17 vs 126）：本库只记录被发布挂载的组件。
