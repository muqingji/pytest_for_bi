# link-eip-data-sync（双方言）

`link-eip-data-sync` 在 catalog 中对应 **PostgreSQL 策略库 + MongoDB 分片缓冲**，使用前 **必须指明方言**，否则 `dialect_required`。

禁止把 `eip-data-sync` / `eip_data_sync` / `syncdata` 当作 biz 名。

查询走 `fx-ops idp query`（IDP 只读/从库路由），禁止直连主库或手写连接串。以当前 profile 的 `show datasources` 为准；部分云可能尚未登记本 biz。

| 方言 | 说明 | 文档 |
| --- | --- | --- |
| **postgresql** | EIP 同步策略 / 映射 / 快照（库 `eip_data_sync`） | [postgresql/link-eip-data-sync.md](./postgresql/link-eip-data-sync.md) |
| **mongodb** | 分片缓冲集合 `buf_*`（库 `fs-sync-data-all`） | [mongodb/link-eip-data-sync.md](./mongodb/link-eip-data-sync.md) |

与下面两个 **独立查询入口** 不同，不要写成 dialect：

| biz | 说明 | 文档 |
| --- | --- | --- |
| `link-eip-data-sync-1` | instance1 独立库 `eip_data_sync_1` | [postgresql/link-eip-data-sync-1.md](./postgresql/link-eip-data-sync-1.md) |
| `link-eip-data-sync-747125` | 大客户 747125 独立库 `eip_data_sync_747125` | [postgresql/link-eip-data-sync-747125.md](./postgresql/link-eip-data-sync-747125.md) |

## CLI 用法（必读）

| 操作 | PostgreSQL | MongoDB |
| --- | --- | --- |
| 表列表 / 表结构 | `show tables link-eip-data-sync --dialect postgresql -j` | `show tables link-eip-data-sync --dialect mongodb -j` |
| 执行查询 | `query link-eip-data-sync --dialect postgresql --sql "..."` 或 `query link-eip-data-sync-postgresql --sql "..."` | `query link-eip-data-sync --dialect mongodb --collection <buf_*> --filter '<JSON>'` |

独立库直接 `query link-eip-data-sync-1` / `query link-eip-data-sync-747125`，不要加在本 biz 的 `--dialect` 上。

## 选型

- 查 **策略、快照、映射、历史任务** → **postgresql**（默认实例无 `sync_data`；该表在 `-1`）
- 查 **buf_* 分片缓冲** → **mongodb**
- 明确要 instance1 / 747125 独立库 → 用对应独立 biz，不走默认入口

拼 WHERE 规则见 [idp-query-filter-hint.md](../../idp-query-filter-hint.md)。
