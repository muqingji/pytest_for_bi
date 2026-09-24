# webpage-customer

**方言**: `mongodb` 
**说明**: 网页客服模块，管理客服会话资料、会话消息及用户消息状态；**同库还承载「站点与页面层」**——自定义页 / 微页面 / 首页与门户布局 / 主导航菜单挂载（见下表加粗集合）。不要因数据源注册表里的「网页客服」描述而跳过本库排查自定义页面。 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns webpage-customer <name> -j` 核对 `filterHint` 与列类型。

> [!IMPORTANT]
> 本库租户键是 **数值**（introspection 实测：`tenantId` / `TId` / `EI` 均为 `int`）。写成字符串**不会报错，而是静默返回 0 条**——曾据此把自定义页相关集合误判为「全空」。类型规则见 [idp-query-mongodb.md](../../../idp-query-mongodb.md) 「租户键类型」。
>
> 自定义页定位：`HomePageLayout.apiName` 形如 `layout_<id>__c`，与前端路由 `crm/custompage/=/layout_<id>__c`、`paasapp/custompage/=/appId_<app>/layout_<id>__c` 一一对应；`name` 是页面业务名（报告里用它，不要用 id），`layoutType=2` 为自定义页、`status=1` 启用。实测 ksc/40020103：`layout_Rj7P4FphTc__c` = 「quick link」。

**查询入口**: `fx-ops idp query webpage-customer`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables webpage-customer --dialect mongodb -j
fx-ops idp --profile <profile> show columns webpage-customer <table> --dialect mongodb -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query webpage-customer --collection <collection> --filter '<JSON>' -j
```

## 统计

- 表级筛选条目: **14**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **13**
- 使用 `$tenant_account` / EA: **1**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 | 说明 |
| --- | --- | --- | --- | --- |
| `EmployeeConfig` | tenantId | `updateTime` | `{"tenantId":$tenant_id}`（**数值**） | 员工个人门户与页面配置 |
| `EmployeeCurrentHomePageLayout` | tenantId | `updateTime` | `{"tenantId":$tenant_id}`（**数值**） | 员工当前生效的首页布局实例 |
| `HomePageLayout` | tenantId | `updateTime` | `{"tenantId":$tenant_id}`（**数值**） | **企业首页与微页面布局**：各卡片/组件排布配置 |
| `MenuEntity` | TId | `-` | `{"TId":$tenant_id}`（**数值**） | 菜单实体定义 |
| `PaaSAppEntity` | tenantId | `updateTime` | `{"tenantId":$tenant_id}`（**数值**） | PaaS 应用实体配置 |
| `PageTemple` | tenantId | `updateTime` | `{"tenantId":$tenant_id}`（**数值**） | **自定义页面与微页面模板**：页面元数据与组件结构定义 |
| `TenantConfigEntity` | TId | `-` | `{"TId":$tenant_id}`（**数值**） | 租户全局门户配置 |
| `TenantMainChannelEntity` | tenantId | `updateTime` | `{"tenantId":$tenant_id}`（**数值**） | **租户主导航频道**：顶部与左侧主导航频道配置 |
| `TenantMenu` | tenantId | `updateTime` | `{"tenantId":$tenant_id}`（**数值**） | **租户菜单配置**：主菜单中微页面/自定义页面挂载配置 |
| `UserDefaultTemplate` | EI | `-` | `{"EI":$tenant_id}`（**数值**；该集合 `TId` 为 string，租户过滤用 `EI`） | 用户默认页面模板 |
| `UserMainChannelEntity` | tenantId | `updateTime` | `{"tenantId":$tenant_id}`（**数值**） | 用户自定义主导航频道 |
| `UserMenu` | tenantId | `updateTime` | `{"tenantId":$tenant_id}`（**数值**） | 用户个人自定义菜单 |
| `UtilityBarEntity` | tenantId | `updateTime` | `{"tenantId":$tenant_id}`（**数值**） | 底部实用工具栏配置 |

## 典型排查查询示例

### 1. 查询企业自定义页面/微页面模板定义
```bash
fx-ops idp --profile <profile> query webpage-customer \
  --collection PageTemple \
  --filter '{"tenantId":<EI>}' -j   # ksc/40020103 实测 7 条
```

### 2. 查询企业首页与微页面组件布局排布
```bash
fx-ops idp --profile <profile> query webpage-customer \
  --collection HomePageLayout \
  --filter '{"tenantId":<EI>}' \
  --projection '{"apiName":1,"name":1,"layoutType":1,"status":1}' -j   # ksc/40020103 实测 11 条
```

### 3. 查询租户主菜单中挂载的自定义页面
```bash
fx-ops idp --profile <profile> query webpage-customer \
  --collection TenantMenu \
  --filter '{"tenantId":<EI>}' -j
```

### 4. 用前端路由里的 layout id 反查页面定义

```bash
fx-ops idp --profile <profile> query webpage-customer \
  --collection HomePageLayout \
  --filter '{"tenantId":<EI>,"apiName":"layout_<ID>__c"}' \
  --projection '{"apiName":1,"name":1,"layoutType":1,"status":1}' -j
```

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `LinkAppObjectAssociation` | upstreamEa | `updateTime` | `{"upstreamEa":"$tenant_account"}` |
