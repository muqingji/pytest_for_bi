# customer-component

**方言**: `mongodb` 
**说明**: 客户组件中心，管理组件实体、插件及其构建历史记录 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns customer-component <name> -j` 核对 `filterHint` 与列类型。

> [!IMPORTANT]
> 本库 4 个集合的 `tenantId` 都是 **数值**（introspection 实测 `int`）。写成字符串（`{"tenantId":"40020103"}`）**不会报错，而是静默返回 0 条**，会被误读成「该企业没有 PWC 组件」。类型规则见 [idp-query-mongodb.md](../../../idp-query-mongodb.md) 「租户键类型」。

**查询入口**: `fx-ops idp query customer-component`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables customer-component --dialect mongodb -j
fx-ops idp --profile <profile> show columns customer-component <table> --dialect mongodb -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query customer-component --collection <collection> --filter '<JSON>' -j
```

## 统计

- 表级筛选条目: **4**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **4**
- 使用 `$tenant_account` / EA: **0**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 | 核心字段与说明 |
| --- | --- | --- | --- | --- |
| `ComponentEntity` | tenantId | `updateTime` | `{"tenantId":$tenant_id}`（**数值**） | **PWC 组件实体**（25列）：`apiName`, `meta`, `metaXml`, `fileTree`, `buildStatus`, `clientTypes`, `images`, `cmptId` 等；索引 `_id_`, `tenantId_1_apiName_1` |
| `PluginEntity` | tenantId | `updateTime` | `{"tenantId":$tenant_id}`（**数值**） | **客开插件实体**（22列）：`apiName`, `entryFileName`, `targetPath`, `client`, `scopeObjects`, `cmptId` 等 |
| `BuildHistoryEntity` | tenantId | `createTime` | `{"tenantId":$tenant_id}`（**数值**） | **组件构建历史**：记录 PWC 组件编译、打包与构建状态及日志 |
| `PluginBuildHistoryEntity` | tenantId | `createTime` | `{"tenantId":$tenant_id}`（**数值**） | **插件构建历史**：记录插件编译与打包发布历史 |

## 服务与架构信息

- **归属服务**: `fs-customer-component-provider`（服务注册表 #51，L2 一般业务服务 · 前台服务，PaaS 业务业务平台开发平台组，负责人：吴俊文 Raymond、张晓峰 zxf）
- **合并部署**: `fs-paas-function-service-runtime` 同时关联 `fs-paas-function-engine` 与本服务代码
- **源码仓库**: `git.firstshare.cn/Qixin/fs-customer-component`
- **底层数据库**: MongoDB `FS-CUSTOMER-COMPONENT-DB`（约 30 个环境均已接入）
- **与微页面关系**: 站点与页面层（`webpage-customer`）通过组件 ID / 页面卡片引用本库的 PWC 组件（`customer-component`），构成上下游调用关系
- **与应用中心关系**: MySQL `open-app-center`（`open_app` / `open_app_component`，租户键 `app_creater`=EA）记录**已发布挂载**的组件；本库记录**已构建定义**的组件。两侧数量不一致属正常（ksc/hkbnes 实测 17 vs 126），报告需分别标注口径

## 典型排查查询示例

### 1. 查询企业注册的 PWC 组件清单与构建状态
```bash
# ✅ 数值 EI（ksc / 40020103 实测 126 条）
fx-ops idp --profile <profile> query customer-component \
  --collection ComponentEntity \
  --filter '{"tenantId":<EI>}' \
  --projection '{"apiName":1,"name":1,"clientTypes":1,"buildStatus":1,"enableFlag":1}' --limit 300 -j

# ❌ 字符串 EI：返回 0 条且 code=0，与「真的没有」不可区分
fx-ops idp --profile <profile> query customer-component \
  --collection ComponentEntity \
  --filter '{"tenantId":"<EI>"}' -j
```

### 2. 按 apiName 钻取组件元数据与源码树
```bash
fx-ops idp --profile <profile> query customer-component \
  --collection ComponentEntity \
  --filter '{"tenantId":<EI>, "apiName":"<COMPONENT_API_NAME>"}' -j
```

### 3. 排查组件构建编译失败记录
```bash
fx-ops idp --profile <profile> query customer-component \
  --collection BuildHistoryEntity \
  --filter '{"tenantId":<EI>}' -j
```

### 4. 查询企业客开插件及生效范围
```bash
fx-ops idp --profile <profile> query customer-component \
  --collection PluginEntity \
  --filter '{"tenantId":<EI>}' -j
```
