# qixin-chatboard

**方言**: `mongodb` 
**说明**: 企信聊天面板模块，管理聊天面板、客户群配置、Zoom会议集成及水印 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns qixin-chatboard <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query qixin-chatboard`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables qixin-chatboard --dialect mongodb -j
fx-ops idp --profile <profile> show columns qixin-chatboard <table> --dialect mongodb -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query qixin-chatboard --collection <collection> --filter '<JSON>' -j
```

## 统计

- 表级筛选条目: **14**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **0**
- 使用 `$tenant_account` / EA: **14**

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `AudioTextConverEntity` | EA | `-` | `{"EA":"$tenant_account"}` |
| `BizDataEntity` | EA | `-` | `{"EA":"$tenant_account"}` |
| `CustomerGroupConfigDetail` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `CustomerGroupInvitationCode` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `EnterpriseConfigEntity` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `GroupInvitationCodeInfo` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `MetUpgradeConfig` | EA | `-` | `{"EA":"$tenant_account"}` |
| `UpgradeConfig` | EA | `-` | `{"EA":"$tenant_account"}` |
| `WaterMark` | EA | `UT` | `{"EA":"$tenant_account"}` |
| `WorkingState` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `ZoomMeetingEntity` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `ZoomTokenInfoEntity` | EA | `-` | `{"EA":"$tenant_account"}` |
| `ZoomUser` | EA | `-` | `{"EA":"$tenant_account"}` |
| `chat_board` | EA | `CT` | `{"EA":"$tenant_account"}` |
