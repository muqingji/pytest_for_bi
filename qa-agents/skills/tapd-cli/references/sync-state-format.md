# 同步状态文件格式参考

## 文件路径

默认存储位置：`~/.workbuddy/sync-states/tapd_sync_{workspace_id}.json`

> 旧版本使用 `/tmp/` 路径，重启后丢失。新版本默认使用持久化目录。

## 完整结构

```json
{
  "workspace_id": 48671251,
  "entity_type": "stories",
  "docid": "DOC_ABC123",
  "sheet_id": "sheet_0",
  "last_sync_time": "2025-06-08T15:30:00+08:00",
  "conflict_strategy": "tapd_wins",
  "tapd_id_column": "TAPD_ID",
  "total_records": 25,
  "field_mapping": { ... },
  "diff_fields": [ ... ],
  "status_map": { ... },
  "snapshot": {
    "1148671251001001001": {
      "tapd": {
        "name": "用户登录功能",
        "status": "developing",
        "priority_label": "High",
        "owner": "zhangsan",
        "effort": "8",
        "begin": "2025-06-01",
        "due": "2025-06-15"
      },
      "sheet": {
        "name": "用户登录功能",
        "status": "developing",
        "priority_label": "High",
        "owner": "zhangsan",
        "effort": "8",
        "begin": "2025-06-01",
        "due": "2025-06-15"
      }
    }
  },
  "sync_log": [
    {
      "time": "2025-06-08T15:30:00+08:00",
      "trigger": "manual",
      "total_tapd_records": 25,
      "total_sheet_records": 23
    }
  ]
}
```

## 字段说明

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| workspace_id | integer | TAPD 项目 ID |
| entity_type | string | 工作项类型：stories / tasks / bugs |
| docid | string | 企微智能表格 docid |
| sheet_id | string | 子表 ID |
| last_sync_time | string | ISO 8601 格式的上次同步时间 |
| conflict_strategy | string | 冲突解决策略 |
| tapd_id_column | string | 关联键列名（默认 TAPD_ID） |
| total_records | integer | 快照中的记录总数 |
| field_mapping | object | 当前使用的字段映射 |
| diff_fields | array | 当前参与 diff 的字段列表 |
| status_map | object | 状态枚举映射（中文 → TAPD status 值） |
| snapshot | object | 三向 diff 用的同步快照 |
| sync_log | array | 同步操作日志（最近 50 条） |

## 快照字段

快照中 `tapd` 和 `sheet` 的字段是**参与 diff 比较的字段**（不含 id、modified 等元数据），且值已规范化。

- 日期字段已归一化为 `YYYY-MM-DD`
- 状态字段已归一化为统一格式（中文或英文，取决于 status_map 配置）

## 同步日志

每次 save-state 时会追加一条日志记录，最多保留 50 条。用于审计追踪。

## 状态文件丢失

如果状态文件丢失：
- 快照为空，所有记录视为新增
- 退化为全量同步
- 不会删除任何数据（安全策略）

## 重置状态

使用 `--action reset-state` 可以清空状态文件，原文件会备份为 `.bak`：
```bash
python3 ${SKILL_DIR}/scripts/bidirectional_sync_engine.py \
  --action reset-state \
  --state-file ~/.workbuddy/sync-states/tapd_sync_48671251.json
```
