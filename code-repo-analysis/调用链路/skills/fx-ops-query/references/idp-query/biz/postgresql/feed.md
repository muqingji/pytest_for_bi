# feed

**方言**: `postgresql`
**说明**: 社交云 Feed 业务库（`fs-plat-feeds-*` / 工作圈动态主库）。承载动态主体、回复、点赞、话题、审批动态等。
**路由**: `tenant-route`（**必填** `--tenant-id <EI>`）

**权威入口**: `biz=feed`（datasource 小写 `feed`）

> [!IMPORTANT]
> 1. **工作圈主库请用 `fx-ops idp query feed`**，不要默认 `query paas`。`paas` / `bi` 文档中可能出现 `fd_*` 表名，物理库可能是 `fsdb*` 镜像或残留，**不是** FEED 路由主路径。
> 2. 查数前先 `route get --biz feed --dialect postgresql`，确认 `database`（常见 `fsfeed*`）、`schema`（常见 `sch_<tenant>`）。
> 3. **`show tables feed` 不完整**：配置白名单约 29 张，而库内 base table 可达 ~60 张。`show tables` 未见的表**不能**据此判定不存在；用 `show columns feed <table>` 或 `information_schema` 复核。
> 4. 字段/索引以 `show columns` + 运行时 `information_schema`/`pg_indexes` 为准；tenant-filters `postgresql/feed/tables.yaml` 仅覆盖部分核心表。
> 5. ClickHouse 生命周期日志见 [biz-log-feeds-lifecycle.md](../clickhouse/biz-log-feeds-lifecycle.md)；CRM Feed 操作日志见 [biz-log-crmfeed.md](../clickhouse/biz-log-crmfeed.md)。

下列为 **表级租户筛选** 与核心表字段；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns feed <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query feed`（方言规则见 [idp-query-sql.md](../../../idp-query-sql.md)，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> route get --tenant-id <EI> --biz feed --dialect postgresql -j
fx-ops idp --profile <profile> show tables feed --dialect postgresql --tenant-id <EI> -j
fx-ops idp --profile <profile> show columns feed <table> --dialect postgresql --tenant-id <EI> -j
# show tables 未见时：
fx-ops idp --profile <profile> query feed --tenant-id <EI> --sql "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema() AND table_type='BASE TABLE' ORDER BY 1" -j
fx-ops idp --profile <profile> query feed --tenant-id <EI> --sql "<SQL>" -j
```

## 统计

- 运行时 base table（tenant=1 实测 `information_schema`）: **60**
- `show tables feed` 暴露: **约 29**（白名单，不完整）
- 下文深写核心表: **12**（含审批两表）

## 表级筛选速查（核心表）

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `fd_feed` | `tenant_id` | `create_time` | `tenant_id`=$tenantId |
| `fd_reply` | `tenant_id` | `create_time` | `tenant_id`=$tenantId |
| `fd_feed_approve` | `tenant_id` | `create_time` | `tenant_id`=$tenantId |
| `fd_approve_reply` | `tenant_id` | - | `tenant_id`=$tenantId |
| `fd_like` | `tenant_id` | - | `tenant_id`=$tenantId |
| `fd_attach` | `tenant_id` | `create_time` | `tenant_id`=$tenantId |
| `fd_follow` | `tenant_id` | - | `tenant_id`=$tenantId |
| `fd_topic` | `tenant_id` | `last_update_time` | `tenant_id`=$tenantId |
| `fd_topic_relation` | `tenant_id` | - | `tenant_id`=$tenantId |
| `fd_vote` | `tenant_id` | - | `tenant_id`=$tenantId |
| `fd_receipt` | `tenant_id` | - | `tenant_id`=$tenantId |
| `fd_feed_at` | `tenant_id` | - | `tenant_id`=$tenantId |
| `fd_obj_relation` | `tenant_id` | - | `tenant_id`=$tenantId |

## 其他表（浅列）

> 下列表在 `information_schema` 可见；部分未出现在 `show tables`。未深写字段时，用 `show columns feed <name>` 或 `information_schema.columns` 取结构。时间列多为 `create_time` / `last_update_time`（epoch 毫秒），以实查为准。

| 表名 | 租户列 | 备注 |
| --- | --- | --- |
| `fd_approve_export_task` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_approve_flow_default_range` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_approve_flow_range` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_approve_flow_relation` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_approve_flow_task` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_approve_flow_task_member` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_approve_form` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_approve_form_default_range` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_approve_form_group` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_approve_form_group_manager` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_approve_form_order` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_approve_form_permission` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_approve_form_range` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_approver_set` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_archive` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_archive_tag` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_archive_tag_relation` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_at_notify_setting` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_borrow_application` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_cc_permission` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_cc_range` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_correct_checkin_detail` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_discount_detail` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_ext_resource` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_fake_leave_info` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_filter_tab_member` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_follow_reply` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_id_generator` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_leave_detail` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_location` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_pay_detail` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_reimbursed_detail` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_reply_at` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_reply_to` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_topic_follow` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_topic_group` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_transfer` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_travel_detail` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_travel_member` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_travel_reimbursed_detail` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_url_resource` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_vote_feed_relation_v1` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_vote_option` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_vote_option_v1` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_vote_result` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_vote_result_v1` | `tenant_id` | 浅列；排障前 `show columns` |
| `fd_vote_v1` | `tenant_id` | 浅列；排障前 `show columns` |

---

## 核心表字段

### `fd_feed`

**说明**: Feed 主表，存储动态/Feed 主体内容与状态

**租户列**: `tenant_id`
**时间列**: `create_time`

#### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `varchar` | 租户 ID |
| `feed_id` | `bigint` | Feed ID |
| `feed_type` | `integer` | Feed 类型（枚举见下文「常用字段枚举值」） |
| `create_time` | `bigint` | 创建时间（epoch 毫秒） |
| `last_update_time` | `bigint` | 最后更新时间（epoch 毫秒） |
| `creator_id` | `bigint` | 创建者用户 ID |
| `obj_api_name` | `varchar` | 关联对象 API Name |
| `obj_data_id` | `varchar` | 关联对象数据 ID |
| `obj_uuid` | `varchar` | obj_uuid |
| `out_tenant_id` | `varchar` | out_tenant_id |
| `importer_id` | `bigint` |  |
| `import_time` | `bigint` |  |
| `feed_content` | `text` | Feed 文本内容（可能含 PII）；纯文本渲染版，正文关键词检索用本列 |
| `feed_content_json` | `text` | 结构化内容块 JSON 数组（见下文「内容双轨模型与话题提取」） |
| `reply_count` | `integer` |  |
| `client_source` | `integer` |  |
| `is_public` | `boolean` |  |
| `is_crm_feed` | `boolean` |  |
| `feed_status` | `integer` | Feed 状态（枚举见下文「常用字段枚举值」） |
| `source_feed_id` | `bigint` |  |

#### 索引

| 索引 | 列 | 说明 |
| --- | --- | --- |
| `fd_feed_obj_data_id_idx` | `obj_data_id`, `tenant_id`, `obj_api_name` |  |
| `fd_feed_obj_uuid_idx` | `obj_uuid`, `tenant_id` |  |
| `fd_feed_pkey` | `tenant_id`, `feed_id` | 主键 |
| `fd_feed_time_idx` | `create_time`, `feed_id`, `feed_type`, `creator_id` |  |
| `fd_feed_uqkey` | `tenant_id`, `feed_id` |  |
| `i_fd_feed_create_time` | `tenant_id`, `create_time`, `feed_id` | i_fd_feed_create_time |
| `i_fd_feed_last_update_time` | `tenant_id`, `last_update_time`, `feed_id` | i_fd_feed_last_update_time |
| `idx_feed_tenant_status_creator_type` | `tenant_id`, `feed_status`, `creator_id`, `feed_type`, `create_time`, `feed_id` |  |

### `fd_reply`

**说明**: Feed 回复表

**租户列**: `tenant_id`
**时间列**: `create_time`

#### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `varchar` | 租户 ID |
| `reply_id` | `bigint` | 回复 ID |
| `creator_id` | `bigint` | 创建者用户 ID |
| `out_tenant_id` | `varchar` | out_tenant_id |
| `create_time` | `bigint` | 创建时间（epoch 毫秒） |
| `feed_id` | `bigint` | Feed ID |
| `reply_content` | `text` | reply_content |
| `reply_content_json` | `text` | reply_content_json |
| `to_reply_id` | `bigint` | to_reply_id |
| `client_source` | `integer` | client_source |
| `is_deleted` | `boolean` | 是否删除 |
| `delete_time` | `bigint` | delete_time |
| `key_reply_code` | `varchar` |  |
| `biz_id` | `varchar` |  |
| `biz_type` | `varchar` |  |

#### 索引

| 索引 | 列 | 说明 |
| --- | --- | --- |
| `fd_reply_pkey` | `tenant_id`, `reply_id` | 主键 |
| `i_fd_feed_reply_byfeed` | `tenant_id`, `feed_id`, `reply_id` | i_fd_feed_reply_byFeed |
| `i_fd_reply_biz` | `tenant_id`, `biz_id`, `biz_type` |  |

### `fd_feed_approve`

**说明**: 审批动态主状态（工作圈审批流）

**租户列**: `tenant_id`
**时间列**: `create_time`

#### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `varchar` |  |
| `feed_id` | `integer` |  |
| `sender_id` | `integer` |  |
| `current_approver_id` | `integer` |  |
| `status` | `smallint` |  |
| `last_update_time` | `bigint` |  |
| `approve_type` | `smallint` |  |
| `approve_reason` | `varchar` |  |
| `approve_budget` | `numeric` |  |
| `approve_prepayments` | `numeric` |  |
| `detail_summary` | `varchar` |  |
| `metadata_id` | `varchar` |  |
| `current_task_id` | `varchar` |  |
| `flow_instance_id` | `varchar` |  |
| `flow_type` | `smallint` |  |
| `approve_form_id` | `varchar` |  |
| `approve_form_name` | `varchar` |  |
| `metadata_api_name` | `varchar` |  |
| `metadata_layout_id` | `varchar` |  |
| `metadata_version` | `varchar` |  |
| `agree_flag` | `boolean` |  |
| `travel_start_date` | `bigint` |  |
| `travel_end_date` | `bigint` |  |
| `travel_duration` | `numeric` |  |
| `life_status` | `integer` |  |
| `create_time` | `bigint` |  |
| `feed_content` | `text` |  |
| `feed_content_json` | `text` |  |

#### 索引

| 索引 | 列 | 说明 |
| --- | --- | --- |
| `fd_feed_approve_pkey` | `tenant_id`, `feed_id` |  |
| `idx_feed_approve_tenant_id_approve_type` | `tenant_id`, `approve_type` |  |
| `idx_feed_approve_tenant_id_sender_id` | `tenant_id`, `sender_id` |  |
| `idx_feed_approve_tenant_id_status` | `tenant_id`, `status` |  |

### `fd_approve_reply`

**说明**: 审批批复与回复映射

**租户列**: `tenant_id`
**时间列**: `-`

#### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `varchar` |  |
| `feed_id` | `integer` |  |
| `feed_reply_id` | `integer` |  |
| `operation_type` | `smallint` |  |
| `approver_id` | `integer` |  |
| `approve_task_id` | `varchar` |  |
| `with_hand_signature` | `boolean` |  |

#### 索引

| 索引 | 列 | 说明 |
| --- | --- | --- |
| `fd_approve_reply_pkey` | `tenant_id`, `feed_reply_id` |  |
| `idx_approve_reply_tenant_id_approver_id` | `tenant_id`, `approver_id` |  |
| `idx_approve_reply_tenant_id_feed_id_feed_reply_id` | `tenant_id`, `feed_id`, `feed_reply_id` |  |

### `fd_like`

**说明**: Feed 点赞表

**租户列**: `tenant_id`
**时间列**: `-`

#### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `varchar` | 租户 ID |
| `ref_data_type` | `integer` | ref_data_type |
| `ref_data_id` | `bigint` | ref_data_id |
| `liker_id` | `bigint` | liker_id |
| `is_like` | `boolean` | is_like |
| `like_time` | `bigint` | like_time |
| `ref_data_creator_id` | `bigint` | ref_data_creator_id |

#### 索引

| 索引 | 列 | 说明 |
| --- | --- | --- |
| `fd_like_pkey` | `tenant_id`, `ref_data_type`, `ref_data_id`, `liker_id` | 主键 |

### `fd_attach`

**说明**: Feed 附件表

**租户列**: `tenant_id`
**时间列**: `create_time`

#### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `varchar` | 租户 ID |
| `attach_id` | `bigint` | 附件 ID |
| `ref_data_type` | `integer` | ref_data_type |
| `ref_data_id` | `bigint` | ref_data_id |
| `attach_type` | `integer` | 附件类型（枚举见下文「常用字段枚举值」） |
| `attach_sub_type` | `integer` | attach_sub_type |
| `attach_path` | `varchar` | 附件存储路径（敏感） |
| `attach_size` | `bigint` | attach_size |
| `attach_name` | `varchar` | 附件文件名 |
| `owner_id` | `bigint` | 所有者用户 ID |
| `create_time` | `bigint` | 创建时间（epoch 毫秒） |
| `is_public` | `boolean` | is_public |
| `height` | `integer` |  |
| `width` | `integer` |  |
| `is_location_pic` | `boolean` |  |
| `original_height` | `integer` |  |
| `original_width` | `integer` |  |
| `tags` | `varchar` |  |
| `reimbursed_detail_id` | `integer` |  |

#### 索引

| 索引 | 列 | 说明 |
| --- | --- | --- |
| `fd_attach_pkey` | `tenant_id`, `attach_id` | 主键 |
| `fd_attach_ref_data_id_idx` | `ref_data_id`, `tenant_id` |  |

### `fd_follow`

**说明**: Feed 关注关系

**租户列**: `tenant_id`
**时间列**: `-`

#### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `varchar` | 租户 ID |
| `feed_id` | `bigint` | Feed ID |
| `follower_id` | `bigint` | follower_id |
| `follow_time` | `bigint` | follow_time |

#### 索引

| 索引 | 列 | 说明 |
| --- | --- | --- |
| `fd_follow_pkey` | `tenant_id`, `feed_id`, `follower_id` | 主键 |

### `fd_topic`

**说明**: 话题表

**租户列**: `tenant_id`
**时间列**: `last_update_time`

#### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `varchar` | 租户 ID |
| `topic_id` | `bigint` | 话题 ID |
| `topic_group_id` | `bigint` | topic_group_id |
| `name` | `varchar` | name |
| `name_spell` | `varchar` | name_spell |
| `count` | `integer` | count |
| `description` | `varchar` | description |
| `last_update_time` | `bigint` | 最后更新时间（epoch 毫秒） |
| `is_fixed` | `boolean` | is_fixed |
| `fixed_order` | `integer` | fixed_order |
| `is_open` | `boolean` | is_open |
| `is_public` | `boolean` | is_public |
| `is_public_export` | `boolean` |  |
| `is_official` | `boolean` |  |
| `is_blacklist` | `boolean` |  |
| `open_range_of_users` | `ARRAY` |  |
| `open_range_of_departments` | `ARRAY` |  |
| `export_range_of_users` | `ARRAY` |  |
| `export_range_of_departments` | `ARRAY` |  |

#### 索引

| 索引 | 列 | 说明 |
| --- | --- | --- |
| `fd_topic_pkey` | `tenant_id`, `topic_id` | 主键 |

### `fd_vote`

**说明**: 投票表

**租户列**: `tenant_id`
**时间列**: `-`

#### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `varchar` | 租户 ID |
| `feed_id` | `bigint` | Feed ID |
| `creator_id` | `bigint` | 创建者用户 ID |
| `title` | `varchar` | title |
| `selection_limit` | `integer` | selection_limit |
| `deadline` | `bigint` | deadline |
| `is_anonymouse` | `boolean` | is_anonymouse |
| `watcher_view_type` | `integer` | watcher_view_type |
| `watcher_id_list` | `ARRAY` | watcher_id_list |

#### 索引

| 索引 | 列 | 说明 |
| --- | --- | --- |
| `fd_vote_pkey` | `tenant_id`, `feed_id` | 主键 |
| `i_fd_vote_byfeed` | `tenant_id`, `feed_id` | i_fd_vote_byFeed |

### `fd_receipt`

**说明**: 已读回执

**租户列**: `tenant_id`
**时间列**: `-`

#### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `varchar` | 租户 ID |
| `feed_id` | `bigint` | Feed ID |
| `receiptor_id` | `bigint` | receiptor_id |
| `is_receipt_sent` | `boolean` | is_receipt_sent |
| `receipt_time` | `bigint` | receipt_time |
| `client_source` | `integer` | client_source |

#### 索引

| 索引 | 列 | 说明 |
| --- | --- | --- |
| `fd_receipt_pkey` | `tenant_id`, `feed_id`, `receiptor_id` | 主键 |
| `idx_fd_receipt_unsent_feed_receiptor` | `tenant_id`, `feed_id`, `receiptor_id` |  |
| `idx_fd_receipt_unsent_feed_receiptor_true` | `tenant_id`, `feed_id`, `receiptor_id` |  |

### `fd_feed_at`

**说明**: Feed @ 提及

**租户列**: `tenant_id`
**时间列**: `-`

#### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `varchar` | 租户 ID |
| `feed_id` | `bigint` | Feed ID |
| `at_user_id` | `bigint` | at_user_id |
| `is_at_department` | `boolean` | is_at_department |

#### 索引

| 索引 | 列 | 说明 |
| --- | --- | --- |
| `fd_feed_at_pkey` | `tenant_id`, `feed_id`, `at_user_id`, `is_at_department` | 主键 |
| `idx_fd_feed_at_tenant_user_dept` | `at_user_id`, `feed_id`, `tenant_id` |  |

### `fd_obj_relation`

**说明**: Feed 与业务对象关联

**租户列**: `tenant_id`
**时间列**: `-`

#### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `varchar` | 租户 ID |
| `feed_id` | `bigint` | Feed ID |
| `obj_api_name` | `varchar` | 关联对象 API Name |
| `obj_data_id` | `varchar` | 关联对象数据 ID |

#### 索引

| 索引 | 列 | 说明 |
| --- | --- | --- |
| `fd_obj_relation_pkey` | `tenant_id`, `feed_id`, `obj_api_name`, `obj_data_id` | 主键 |
| `i_fd_obj_relation_byfeed` | `tenant_id`, `feed_id` | i_fd_obj_relation_byFeed |
| `i_fd_obj_relation_byobject` | `tenant_id`, `obj_api_name`, `obj_data_id` | i_fd_obj_relation_byObject |

### `fd_topic_relation`

**说明**: 话题与 Feed 关联表；正文 `#话题#` 提取后逐条落关联行

**租户列**: `tenant_id`

#### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `varchar` | 租户 ID |
| `topic_id` | `bigint` | 话题 ID（`fd_topic.topic_id`） |
| `feed_id` | `bigint` | Feed ID（`fd_feed.feed_id`） |

#### 索引

| 索引 | 列 | 说明 |
| --- | --- | --- |
| `fd_topic_relation_pkey` | `tenant_id`, `topic_id`, `feed_id` | 主键 |
| `i_fd_topic_relation_byTopic` | `tenant_id`, `topic_id`, `feed_id` | 按话题查 Feed（DDL 声明） |
| `i_fd_topic_relation_byFeed` | `tenant_id`, `feed_id`, `topic_id` | 按 Feed 反查话题（DDL 声明；部分分库物理索引以实查为准） |

> `fd_topic.count` 是话题下 Feed 数的冗余计数，异步维护允许短期不一致（tenant 1 实测与关联行数一致）；统计口径以 `fd_topic_relation` 行数为准。

### 常用字段枚举值

> 权威来源：`git.firstshare.cn/feeds/fs-feeds` 仓 `fs-feeds-enums` 模块（`FeedTypes` / `FeedStatus` / `AttachTypes`）；枚举漂移时以源码为准。源码注释：**新增 feedTypes 需要通知 BI**。

#### `fd_feed.feed_type`

| 值 | 含义 |
| --- | --- |
| 1 | 分享（BlogObj） |
| 2 | 日志（JournalObj） |
| 3 | 指令 |
| 4 | 审批 |
| 5 | 销售记录（ActiveRecordObj） |
| 6 | 任务（旧） |
| 7 | 日程（ScheduleObj） |
| 8 | 服务记录（ServiceLogObj） |
| 9 | 销售流程 |
| 10 | PK 助手 |
| 99 | 外勤 |
| 201 | 项目任务 |
| 2003 | 群通知 |
| 2004 | 跟进记录（暂时不用） |
| 2005 | 工作汇报 |
| 2006 | 任务（TaskObj） |
| 2007 | CRM 审批流（ApprovalInstanceObj） |
| 2008 | 电销记录 |
| 9997 | 公告（AnnounceObj） |
| 9998 | CRM 信息 |

#### `fd_feed.feed_status`

| 值 | 含义 |
| --- | --- |
| 0 | 正常 |
| 1 | 作废（常见于日程改期后的旧日程、改稿前的旧分享） |
| 2 | 删除 |

#### `fd_attach.attach_type`

| 值 | 含义 |
| --- | --- |
| 1 | 音频 |
| 2 | 图片 |
| 3 | 文件 |
| 4 | 定位 |
| 5 | 复制文件 |
| 6 | 定位图片 |
| 7 | 一键定位 |
| 8 | 转发文件 |
| 11 | 手写签名 |

### 内容双轨模型与话题提取

- `feed_content`：纯文本渲染版，直接可读；**正文关键词检索用本列**，不要 LIKE `feed_content_json`（JSON 转义噪声大）。
- `feed_content_json`：结构化内容块 JSON 数组，服务端解析为 `TextDTO`（`type`/`subType`/`text`/`dataID`/`dataTitle`；运行时块另可含 `bold`/`content`/`feedId`/`objectType`）；解析前剔除老数据遗留的 `\uFFFC` 占位符。
- 内容块类型（`FeedTextBlockType`）：0=纯文本、1=关键字、2=Url（subType 1=feed 链接）、3=话题、4=@部门、5=@员工（subType 1=@下游员工）、6=Emoji、7=饼干表情、8=制表符、9=电话号码、10=COMMON（subType 1=CRM、2=审批）、11=日志自动化、12=@下游员工。
- 话题提取：正则 `#([^#\s]+)#`，命中后双写内容块（type=3）与 `fd_topic_relation` 行。

按话题查 feed（走 byTopic 索引）：

```sql
SELECT f.feed_id, f.feed_type, f.feed_status, f.create_time, f.creator_id
FROM fd_topic_relation tr
INNER JOIN fd_feed f
  ON f.tenant_id = tr.tenant_id AND f.feed_id = tr.feed_id
WHERE tr.tenant_id = '<EI>' AND tr.topic_id = <topicId>
ORDER BY f.create_time DESC
LIMIT 20
```

### 查询示例

```bash
# 按 feed_id 查主动态
fx-ops idp --profile <profile> query feed --tenant-id <EI> --sql "
SELECT tenant_id, feed_id, feed_type, feed_status, create_time, last_update_time,
       creator_id, obj_api_name, obj_data_id, obj_uuid, reply_count, is_crm_feed,
       substring(feed_content from 1 for 500) AS feed_content
FROM fd_feed
WHERE tenant_id = '<EI>' AND feed_id = <feedId>
LIMIT 20
" -j

# 按关联对象反查（外勤等）
fx-ops idp --profile <profile> query feed --tenant-id <EI> --sql "
SELECT tenant_id, feed_id, feed_type, feed_status, create_time, creator_id,
       obj_api_name, obj_data_id, obj_uuid, reply_count
FROM fd_feed
WHERE tenant_id = '<EI>'
  AND obj_uuid = 'CheckinsObj|<对象ID>'
ORDER BY create_time DESC
LIMIT 10
" -j

# 审批动态状态
fx-ops idp --profile <profile> query feed --tenant-id <EI> --sql "
SELECT tenant_id, feed_id, sender_id, current_approver_id, status,
       last_update_time, approve_type, current_task_id, flow_instance_id,
       agree_flag, life_status, create_time
FROM fd_feed_approve
WHERE tenant_id = '<EI>' AND feed_id = <feedId>
LIMIT 20
" -j

# 审批批复 + 回复正文
fx-ops idp --profile <profile> query feed --tenant-id <EI> --sql "
SELECT ar.tenant_id, ar.feed_id, ar.feed_reply_id, ar.operation_type,
       ar.approver_id, ar.approve_task_id, ar.with_hand_signature,
       r.creator_id, r.create_time, r.is_deleted,
       substring(r.reply_content from 1 for 500) AS reply_content
FROM fd_approve_reply ar
LEFT JOIN fd_reply r
  ON ar.tenant_id = r.tenant_id AND ar.feed_reply_id = r.reply_id
WHERE ar.tenant_id = '<EI>' AND ar.feed_id = <feedId>
ORDER BY r.create_time, ar.feed_reply_id
LIMIT 50
" -j
```

## 相关文档

- [index.md](./index.md) — PostgreSQL biz 索引
- [paas.md](./paas.md) — 可能含 `fd_*` 名，**非**工作圈主库权威入口
- [../clickhouse/biz-log-feeds-lifecycle.md](../clickhouse/biz-log-feeds-lifecycle.md) — 截图反查 feedId 首选 CH 表
- [../clickhouse/biz-log-crmfeed.md](../clickhouse/biz-log-crmfeed.md) — CRM Feed 操作日志
