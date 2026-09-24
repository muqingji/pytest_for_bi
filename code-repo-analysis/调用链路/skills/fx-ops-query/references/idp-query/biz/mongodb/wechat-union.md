# wechat-union

**方言**: `mongodb` 
**说明**: 微信联盟消息聚合模块，管理上下行消息、模板通知、邮件消息及粉丝会话 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

## 多方言：必须指明 dialect

`wechat-union` 同时注册 **`mongodb` / `mysql`**。 本文档仅描述 **`mongodb`** 侧；另一方言见 [`mysql/wechat-union.md`](../mysql/wechat-union.md)。

| 操作 | 本方言（mongodb） |
| --- | --- |
| `table list` / `table get` | 必须加 `--dialect mongodb` |
| 执行 SQL | `query wechat-union-mongodb`（勿用无后缀的 `query wechat-union`） |

另一方言 CLI：`--dialect mysql` / `query wechat-union-mysql`。

**不要** 省略 `--dialect` 调用 `table list wechat-union`，否则可能推断到错误库。

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns wechat-union <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query wechat-union-mongodb`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables wechat-union --dialect mongodb -j
fx-ops idp --profile <profile> show columns wechat-union <table> --dialect mongodb -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query wechat-union-mongodb --collection <collection> --filter '<JSON>' -j
```

## 统计

- 表级筛选条目: **21**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **0**
- 使用 `$tenant_account` / EA: **21**

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `DownMsgItem` | ea | `-` | `{"ea":"$tenant_account"}` |
| `LuckyMoneyDepartmentInfoDO` | fsEa | `-` | `{"fsEa":"$tenant_account"}` |
| `MassCallbackMsgRecord` | fsEa | `-` | `{"fsEa":"$tenant_account"}` |
| `MessageContent` | fsEa | `-` | `{"fsEa":"$tenant_account"}` |
| `MessageUser` | fsEa | `-` | `{"fsEa":"$tenant_account"}` |
| `QrMsgItem` | enterpriseAccount | `-` | `{"enterpriseAccount":"$tenant_account"}` |
| `TemplateNotify` | fsEa | `updateTime` | `{"fsEa":"$tenant_account"}` |
| `TemplateNotifyPersonal` | fsEa | `updateTime` | `{"fsEa":"$tenant_account"}` |
| `UpMsgItem` | ea | `-` | `{"ea":"$tenant_account"}` |
| `WeChatClickEvent` | fsEa | `-` | `{"fsEa":"$tenant_account"}` |
| `WechatFanSessionItem` | fsEa | `updateTime` | `{"fsEa":"$tenant_account"}` |
| `WechatMsgItem` | ea | `-` | `{"ea":"$tenant_account"}` |
| `customer_evaluation` | fsEa | `updateTime` | `{"fsEa":"$tenant_account"}` |
| `customer_evaluation_statistics` | fsEa | `-` | `{"fsEa":"$tenant_account"}` |
| `email_message_item` | ea | `-` | `{"ea":"$tenant_account"}` |
| `fs_message_item` | downEa | `-` | `{"downEa":"$tenant_account"}` |
| `log_original` | fsEa | `-` | `{"fsEa":"$tenant_account"}` |
| `online_knowledge_mark` | EA | `-` | `{"EA":"$tenant_account"}` |
| `service_number_message_item` | ea | `-` | `{"ea":"$tenant_account"}` |
| `web_im_message_item` | ea | `-` | `{"ea":"$tenant_account"}` |
| `work_order_bury` | ea | `-` | `{"ea":"$tenant_account"}` |
