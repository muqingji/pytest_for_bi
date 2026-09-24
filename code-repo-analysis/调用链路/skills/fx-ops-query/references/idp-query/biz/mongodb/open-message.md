# open-message

**方言**: `mongodb` 
**说明**: 开放消息模块，管理消息会话、消息转发引用、客户评价及临时消息 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

**双方言**: 同名还有 `mysql`（设备消息）。查 Mongo **必须** `--dialect mongodb` 或 `open-message-mongodb`。

## 多方言：必须指明 dialect

`open-message` 同时注册 **`mongodb` / `mysql`**。 本文档仅描述 **`mongodb`** 侧；另一方言见 [`mysql/open-message.md`](../mysql/open-message.md)。

| 操作 | 本方言（mongodb） |
| --- | --- |
| `table list` / `table get` | 必须加 `--dialect mongodb` |
| 执行 SQL | `query open-message-mongodb`（勿用无后缀的 `query open-message`） |

另一方言 CLI：`--dialect mysql` / `query open-message-mysql`。

**不要** 省略 `--dialect` 调用 `table list open-message`，否则可能推断到错误库。

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns open-message <name> --dialect mongodb -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query open-message-mongodb`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables open-message --dialect mongodb -j
fx-ops idp --profile <profile> show columns open-message <table> --dialect mongodb -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query open-message-mongodb --collection <collection> --filter '<JSON>' -j
```

## 统计

- 表级筛选条目: **5**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **0**
- 使用 `$tenant_account` / EA: **5**

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `customer_evaluate` | enterpriseAccount | `updateTime` | `{"enterpriseAccount":"$tenant_account"}` |
| `msg_session` | enterpriseAccount | `updateTime` | `{"enterpriseAccount":"$tenant_account"}` |
| `msg_transmit_ref` | enterpriseAccount | `updateTime` | `{"enterpriseAccount":"$tenant_account"}` |
| `open_msg` | enterpriseAccount | `updateTime` | `{"enterpriseAccount":"$tenant_account"}` |
| `temp_open_msg` | enterpriseAccount | `-` | `{"enterpriseAccount":"$tenant_account"}` |
