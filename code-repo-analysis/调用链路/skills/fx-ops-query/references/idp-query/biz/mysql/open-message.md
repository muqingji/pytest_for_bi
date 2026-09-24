# open-message

**方言**: `mysql` 
**说明**: 设备消息通知，管理企业设备状态、通知发送记录及定时任务 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼） 

**双方言**: 同名还有 `mongodb`（开放消息会话等）。查 MySQL **必须** `--dialect mysql` 或 `open-message-mysql`。


## 多方言：必须指明 dialect

`open-message` 同时注册 **`mongodb` / `mysql`**。 本文档仅描述 **`mysql`** 侧；另一方言见 [`mongodb/open-message.md`](../mongodb/open-message.md)。

| 操作 | 本方言（mysql） |
| --- | --- |
| `table list` / `table get` | 必须加 `--dialect mysql` |
| 执行 SQL | `query open-message-mysql`（勿用无后缀的 `query open-message`） |

另一方言 CLI：`--dialect mongodb` / `query open-message-mongodb`。

**不要** 省略 `--dialect` 调用 `table list open-message`，否则可能推断到错误库。

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns open-message <name> --dialect mysql -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query open-message-mysql`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables open-message --dialect mysql -j
fx-ops idp --profile <profile> show columns open-message <table> --dialect mysql -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query open-message-mysql --sql "<SQL>" -j
```

## 统计

- 表级筛选条目: **9**
- 复杂筛选（无租户列和/或子查询）: **1**
- 使用 `$tenant_id` / EI: **0**
- 使用 `$tenant_account` / EA: **8**

## 复杂筛选表（优先阅读）

下列表的 **queryTemplate** 为 **子查询/关联** 或未使用单列租户列，
不要写成 `WHERE tenant_id = <EI>`；需用 `tenant get` 得到 **tenantAccount（EA）** 并按模板拼 WHERE。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `reply_latest_time` | - | `-` | `user` LIKE CONCAT('E.',$tenant_account,'.%') |

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `customer_session_info` | enterprise_account | `gmt_modified` | `enterprise_account`=$tenant_account |
| `customservice_switch_status` | enterprise_account | `-` | `enterprise_account`=$tenant_account |
| `default_reply_content` | enterprise_account | `-` | `enterprise_account`=$tenant_account |
| `keyword_reply_content` | enterprise_account | `-` | `enterprise_account`=$tenant_account |
| `reply_switch_status` | enterprise_account | `-` | `enterprise_account`=$tenant_account |
| `t_msg_callback` | enterprise_account | `update_time` | `enterprise_account`=$tenant_account |
| `t_msg_send` | enterprise_account | `update_time` | `enterprise_account`=$tenant_account |
| `t_msg_session` | enterprise_account | `update_time` | `enterprise_account`=$tenant_account |
