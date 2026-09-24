# eip-data-sync（已废弃）

> **DEPRECATED（2026-08-07）**: 错误 biz 名 eip-data-sync / eip_data_sync / syncdata；正确为 link-eip-data-sync。
> 请改用 **`link-eip-data-sync --dialect postgresql`**（双方言，未指定会 `dialect_required`）。
> 独立库入口：`link-eip-data-sync-1`、`link-eip-data-sync-747125`。Mongo 缓冲用 `--dialect mongodb`。

```bash
fx-ops idp --profile <profile> show tables link-eip-data-sync --dialect postgresql -j
fx-ops idp --profile <profile> query link-eip-data-sync --dialect postgresql --sql "<SQL>" -j
```

正式文档：[link-eip-data-sync.md](./link-eip-data-sync.md) · 总览：[../link-eip-data-sync.md](../link-eip-data-sync.md)
