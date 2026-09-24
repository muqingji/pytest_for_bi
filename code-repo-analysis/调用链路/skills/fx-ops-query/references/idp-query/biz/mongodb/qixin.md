# qixin

**方言**: `mongodb` 
**说明**: 企信即时通讯核心模块，管理用户资料、会话消息、会话状态及音视频文字转换 
**租户 ID**: 必填 `--tenant-id <EI>` 

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns qixin <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query qixin`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables qixin --dialect mongodb --tenant-id <EI> -j
fx-ops idp --profile <profile> show columns qixin <table> --dialect mongodb --tenant-id <EI> -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query qixin --tenant-id <EI> --collection <collection> --filter '<JSON>' -j
```

## 统计

- 表级筛选条目: **3**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **0**
- 使用 `$tenant_account` / EA: **3**

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `MergedMessage` | EA | `MTS` | `{"Env": 0, "EA":"$tenant_account"}` |
| `RouterInfo` | _id | `UTS` | `{"_id":"$tenant_account"}` |
| `TimingData` | EA | `-` | `{"EA":"$tenant_account"}` |
