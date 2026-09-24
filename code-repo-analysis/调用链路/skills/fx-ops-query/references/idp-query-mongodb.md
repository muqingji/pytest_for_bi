# fx-ops idp query — MongoDB

MongoDB 业务线直查。`--tenant-id` 必填。需要找 biz 时读 idp-query/biz/mongodb.md。

## 模板

```bash
fx-ops idp --profile <profile> query <biz> --tenant-id <id> \
 --collection <collection> \
 --filter '<JSON>' \
 --limit 20 \
 -j
```

```bash
fx-ops idp --profile <profile> query qixin --tenant-id 123 \
 --collection messages \
 --filter '{"session_id":"s_abc123"}' \
 --projection '{"content":1,"createdAt":1}' \
 --limit 20 \
 -j
```

## 规则与陷阱

- `--filter` 为标准 MongoDB 查询 JSON
- 租户字段必须用直接等值或 `$eq` / `$in`，不支持 `$or` / `$not` / `$ne`
- aggregate 中禁止 `$lookup` / `$graphLookup` / `$unionWith`
- 列出集合：`fx-ops idp --profile <profile> show tables <biz> --tenant-id <id> -j`
- 典型 biz：`qixin`、`org-data`、`oa-todo`、`paas-bpm`、`paas-workflow`、`waiqin`

## 租户键类型（最容易误判为「无数据」）

MongoDB 是弱类型存储：租户键在部分库里是 **数值**（`int` / `long`），字符串过滤**不会报错，而是静默返回 0 条**，`code` 仍为 0。这与「该企业真的没有数据」在信封上完全一致，极易得出错误结论。

**落笔前先用 introspection 定型，不要凭字段名猜**：

```bash
fx-ops idp --profile <profile> show columns <biz> <collection> -j
# 看 data.table.columns[]，例如 {"name":"tenantId","type":"int"}
```

| introspection 类型 | 正确写法 | 错误写法（静默 0 条） |
| --- | --- | --- |
| `int` / `long` | `--filter '{"tenantId":40020103}'` | `--filter '{"tenantId":"40020103"}'` |
| `string` | `--filter '{"tenantId":"40020103"}'` | `--filter '{"tenantId":40020103}'` |

实测（`ksc` / 40020103，2026-08-21）：`customer-component.ComponentEntity` 与 `webpage-customer.HomePageLayout` 的 `tenantId` 均为 `int`；字符串过滤 0 条，数值过滤分别 126 条与 11 条。已按实测类型定稿的库见 `idp-query/biz/mongodb/customer-component.md`、`idp-query/biz/mongodb/webpage-customer.md`。

**取证纪律**：Mongo 查询返回 0 条时，先换另一种类型复测，再决定是否写「无数据」；不得直接据此下业务结论。
