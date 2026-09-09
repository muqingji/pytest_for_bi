# API 响应结构与解析

## 通用结构

TAPD API 响应结构如下：

```json
{
  "status": 1,
  "data": [],
  "info": "success"
}
```

- 列表查询返回的每条数据按实体类型键名包裹（例如 `item["Story"]["name"]`、`item["Bug"]["title"]`，而不是 `item["name"]`）。
- **空字段省略与 `all-fields=1`**：CLI 默认会省略值为空字符串的 `custom_field_*`，并在根节点返回 `_omitted_custom_fields` 提示。若需要查看全量字段，可追加参数 `all-fields=1`。

## Story（需求）

```json
{
  "Story": {
    "id": "1120019471001400908",
    "name": "标题",
    "status": "planning",
    "owner": "张三;",
    "priority_label": "Middle",
    "category_id": "-1",
    "workitem_type_id": "...",
    "description": "<div>HTML内容</div>",
    "created": "2026-05-12 11:27:03",
    "due": "2026-05-20",
    "iteration_id": "..."
  }
}
```

## Task（任务）

```json
{
  "Task": {
    "id": "...",
    "name": "标题",
    "status": "open",
    "owner": "...",
    "priority_label": "High",
    "due_date": "2026-05-20",
    "story_id": "...",
    "iteration_id": "...",
    "description": "<div>HTML内容</div>",
    "created": "..."
  }
}
```

## Bug（缺陷）

```json
{
  "Bug": {
    "id": "...",
    "title": "标题",
    "status": "new",
    "severity": "serious",
    "priority_label": "High",
    "current_owner": "张三",
    "reporter": "李四",
    "description": "<div>HTML内容</div>",
    "created": "..."
  }
}
```

### 常用自定义字段（Bug）

| 字段 | label | 说明 |
| --- | --- | --- |
| `custom_field_7` | BUG来源（来源渠道） | 400 / 纷享客服 / 微信 / 运营群 / 销售 / 渠道 / 研发内部 等 |
| `custom_field_8` | 所属团队 | 平台架构组 / 基础业务团队 / Web架构组 / 开发平台 等 |
| `custom_field_four` | 企业类型 | VIP付费 / 付费 / 自注册 / 开源 / 测试 |
| `custom_field_26` | 客户类型打标 | 国际化 / 测试2 |
| `custom_field_15` | 拒绝原因 | 多选：产品设计如此 / 用户操作错误 / 重复bug 等 |
| `custom_field_17` | 是否重复Bug | 重复bug / 非重复Bug |
| `custom_field_24` | 是否需要补充文档 | 无需补充文档 / 需补充产品手册/实施指南 / 需补充乐享文档 等 |

查询时如需这些字段，直接加到 `fields` 参数中，例如：

```bash
tapd-cli bug list workspaceid=20019471 fields=id,title,status,severity,custom_field_7,custom_field_8,custom_field_four,current_owner,created
```

## Iteration（迭代）

```json
{
  "Iteration": {
    "id": "...",
    "name": "迭代1",
    "status": "open",
    "startdate": "2026-05-01",
    "enddate": "2026-05-15"
  }
}
```

## Comment（评论）

```json
{
  "Comment": {
    "id": "...",
    "description": "已完成代码审查",
    "author": "...",
    "created": "...",
    "entry_id": "...",
    "entity_type": "story"
  }
}
```

- `comment list` 默认返回纯文本清洗后的 `description`。如需获取原始 HTML，可追加 `--full` 选项。

## 状态值处理

不同项目的 `status` 取值往往是项目级自定义配置。推荐：

- 用 `v_status` 传中文状态名（如 `v_status=规划中`、`v_status=已解决`），并在 `story list` 时可搭配 `with_v_status=1` 获取中文名。
- 或使用 `tapd-cli bug/story fields workspaceid=XXX` 查询状态映射。

## 回复摘要规范

- **列表输出**：提取关键字段，使用 Markdown 表格输出 ID、标题/名称、状态（转为中文）、负责人、创建时间等。
- **详情输出**：先输出实体 URL、状态、负责人、优先级，再摘要 `description`。
- **HTML 清洗**：`description` 包含 HTML 时，先去除 HTML 标签提取纯文本后再做摘要，禁止直接原样输出大段混乱的 HTML 代码。
- **空结果处理**：查询为空时，明确说明当前查询条件与 `workspace_id`，不要直接回答模糊的“没有”。
