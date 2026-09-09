# 高级查询与字段探索

## 查询流程

当用户意图模糊时（例如“查 CRM 模块的 Bug”、“看看基础业务团队的缺陷”、“查找某团队的未解决 Bug”），**不要猜测枚举值拼接查询**，按以下流程进行：

1. **判断涉及字段**：明确用户意图对应的系统或自定义字段（如团队对应 `custom_field_8`，来源对应 `custom_field_7`）。
2. **查阅字段词典**：在 [xiaoke-tapd-dict.md](xiaoke-tapd-dict.md) 中查找。若在速查表中，直接取对应的精确枚举值。
3. **探索未知字段**：若不在词典中，使用 `fields` 子命令配合 `jq` 实时探索合法 options（见下方）。
4. **构建精确查询**：使用标准高级查询语法构建命令。

## TAPD 高级查询语法

| 语法 | 说明 | 示例 |
| --- | --- | --- |
| `LIKE` | 模糊匹配 | `'name=LIKE<关键词>'` |
| `LIKE_OR` | 多值模糊匹配（任一满足） | `'name=LIKE_OR<安卓\|苹果>'` |
| `EQ` | 全等匹配 | `'name=EQ<完整标题>'` |
| `NOT_EQ` | 全等不匹配 | `'status=NOT_EQ<closed>'` |
| `CONTAINS` | 多选字段同时包含所有值 | `'label=CONTAINS<v1\|v2>'` |
| `CONTAINS_OR` | 多选字段包含任一值 | `'label=CONTAINS_OR<v1\|v2>'` |
| `USER_OR` | 用户字段包含任一用户 | `'owner=USER_OR<user1\|user2>'` |
| `~` | 时间范围 | `'created=2026-01-01~2026-05-15'` |
| `\|` | 枚举查询（满足其一） | `'status=new\|in_progress'` |
| `<>` | 不等于 | `'iteration_id=<>1120019471001000001'` |
| `,` | 多 ID 列表 | `id=112001,112002,112003` |
| `;` | 多人员（与条件） | `owner=user1;user2` |

## 特殊字符转义与跨平台

| 特殊字符 | macOS / Linux | Windows PowerShell |
| --- | --- | --- |
| `<>` | 单引号包裹：`'custom_field_8=EQ<基础业务团队>'` | 单引号包裹：`'custom_field_8=EQ<基础业务团队>'` |
| `\|` | 单引号包裹：`'status=new\|in_progress'` | 单引号包裹：`'status=new\|in_progress'` |
| `~` | 推荐单引号包裹：`'created=2026-01-01~2026-05-15'` | 推荐单引号包裹：`'created=2026-01-01~2026-05-15'` |

## fields + jq 探索未知字段与选项

当需要了解字段定义、类型或合法枚举选项时，使用 `fields` 命令配合 `jq` 进行探索（支持 `story`、`bug`、`tcase`）：

### 1. 查单个字段的定义与选项

```bash
tapd-cli bug fields workspaceid=20019471 | jq '.data.custom_field_8'
```

### 2. 查找所有下拉/单选/多选字段列表

```bash
tapd-cli bug fields workspaceid=20019471 | jq '[.data | to_entries[] | select(.value.html_type == "select" or .value.html_type == "multi_select") | {field: .key, label: .value.label}]'
```

### 3. 提取特定字段的 options 候选字典

```bash
tapd-cli bug fields workspaceid=20019471 | jq '.data.custom_field_8.options'
```

## 查询示例

```bash
# 按团队精确查询 Bug
tapd-cli bug list workspaceid=20019471 'custom_field_8=EQ<基础业务团队>' fields=id,title,status,custom_field_8

# 多状态查询
tapd-cli bug list workspaceid=20019471 'status=new|in_progress|reopened' fields=id,title,status

# 模块模糊查询
tapd-cli bug list workspaceid=20019471 'module=LIKE<CRM>' fields=id,title,module

# 时间范围查询
tapd-cli bug list workspaceid=20019471 'created=2026-05-01~2026-05-15' fields=id,title,created
```
