# fx-ops idp query — SQL

MySQL 和 PostgreSQL 共用本规则。`--tenant-id` 按 biz 的 `routeMode` 与表级 filterHint 决定是否传入——**不是永远必填**。

## 模板

```bash
# tenant-route biz（如 paas / bi / feed）：必填 --tenant-id
fx-ops idp --profile <profile> query <biz> --tenant-id <id> --sql "<SQL>" -j

# fixed 路由 biz（如 openapi / enterprise-relation / outer-oa / mail 等）：可免 --tenant-id
fx-ops idp --profile <profile> query <biz> --sql "<SQL>" -j

# 双方言 biz：必须 --dialect 或 <biz>-<dialect> 别名
fx-ops idp --profile <profile> query enterprise-relation --dialect postgresql --sql "<SQL>" -j
fx-ops idp --profile <profile> query enterprise-relation-postgresql --sql "<SQL>" -j
fx-ops idp --profile <profile> query link-eip-data-sync --dialect postgresql --sql "<SQL>" -j

fx-ops idp --profile <profile> query <biz> --sql-file <file> -j
cat query.sql | fx-ops idp --profile <profile> query <biz> --sql-from-stdin -j
```

## 规则

- 只写 `SELECT`、`WITH` 或 `EXPLAIN`。
- 单条语句，末尾不加分号。
- 必须带能收敛数据量的 `WHERE` 或 `LIMIT`。
- 默认超时 30 秒，返回上限 1000 行。
- 不确定表名或字段名时，先用 `show tables` / `show columns` 发现（详见 idp-query-table.md）。
- **fixed vs tenant-route**：CLI 层 fixed 可免 `-t`；SQL 内仍须按 filterHint 收敛租户（`$tenant_id` / `$tenant_account`）。
- **禁止旧 biz 名**：`open-oauth`、`open-link-app`、`wechat-proxy`、`wechat-notice`、`link-enterprise-relation`、`open-qywx`、`eip-data-sync`。映射见 [biz/index.md](./idp-query/biz/index.md)。

## 工作流

```bash
# 1. 选 biz；不确定时先查 catalog（以实测为准，勿死记旧名）
fx-ops idp --profile <profile> show datasources -j

# 2. 读 biz 表级筛选文档
#  references/idp-query/biz/<dialect>/<biz>.md

# 3. 发现表和字段 + filterHint
#    fixed biz 可省略 --tenant-id；双方言加 --dialect
fx-ops idp --profile <profile> show columns <biz> <table> -j
fx-ops idp --profile <profile> tenant get --tenant-id <id> -j  # 模板含 $tenant_account 时取 EA

# 4. 按 idp-query-filter-hint.md 拼 WHERE 后查询
fx-ops idp --profile <profile> query <biz> --sql "SELECT ... LIMIT 20" -j
```

拼模板细则见 [idp-query-filter-hint.md](./idp-query-filter-hint.md)。

## 业务线索引

- MySQL：只在需要按业务含义找 biz 时读 idp-query/biz/mysql.md。
- PostgreSQL：只在需要按业务含义找 biz 时读 idp-query/biz/postgresql.md。
