# 值格式转换参考

## TAPD → 智能表格

从 TAPD 读取数据写入智能表格时，需按列类型转换值格式。

### 通用规则

| 智能表格列类型 | TAPD 原始值 | 智能表格写入格式 | 示例 |
| --- | --- | --- | --- |
| FIELD_TYPE_TEXT (URL) | 字符串 + URL | `[{"type": "url", "text": "显示文字", "link": "https://..."}]` | `[{"type":"url","text":"用户登录","link":"https://tapd.woa.com/tapd_fe/48671251/story/detail/111"}]` |
| FIELD_TYPE_TEXT | 字符串 | `[{"type": "text", "text": "内容"}]` | `[{"type":"text","text":"张三"}]` |
| FIELD_TYPE_SINGLE_SELECT | 字符串 | `[{"text": "选项值"}]` | `[{"text":"实现中"}]` |
| FIELD_TYPE_NUMBER | 数字 | 直接传数字 | `8.0` |
| FIELD_TYPE_DATE_TIME | YYYY-MM-DD | `"YYYY-MM-DD"` | `"2025-06-08"` |

### TAPD_ID 和标题列（必须带超链接）

```python
# TAPD_ID 列：text 填完整 19 位 ID，link 指向详情页
values["TAPD_ID"] = [{"type": "url", "text": tapd_id, "link": detail_url}]
# 标题列：text 填需求名称，link 指向详情页
values["标题"] = [{"type": "url", "text": story_name, "link": detail_url}]
```

URL 模板：
- 司内版：`https://tapd.woa.com/tapd_fe/{workspace_id}/story/detail/{tapd_id}`
- 公有云：`https://www.tapd.cn/{workspace_id}/prong/stories/view/{tapd_id}`

> ⚠️ TAPD_ID 的 `text` 必须是完整 19 位 ID，不要截短显示。反向读取时如果 `text` 不是完整 ID，需从 `link` 正则解析。

## 智能表格 → TAPD

从智能表格读取数据写入 TAPD 时，需反向解析。

| 列类型 | 读取方式 | 说明 |
| --- | --- | --- |
| TEXT / URL | 取 `[0].text` | URL 类型也可取 `text` |
| SINGLE_SELECT | 取 `[0].text`，再通过 `status_map` 转为 TAPD status 值 | 用 `v_status` 传中文状态名更方便 |
| NUMBER | 直接取数字 |  |
| DATE_TIME | 取日期字符串 | 毫秒时间戳需转换 |
| USER | 取 `[0].user_id` | 需映射为 TAPD 用户名 |

## 日期格式转换

智能表格 API 返回的日期字段可能是**毫秒时间戳字符串**（如 `"1684252800000"`），而 TAPD 使用 `YYYY-MM-DD` 格式。

同步引擎已内置日期归一化逻辑（`normalize_date` 函数），自动处理以下格式：
- `"2025-06-08"` → `"2025-06-08"`
- `"2025-06-08 14:30:00"` → `"2025-06-08"`
- `"1684252800000"`（毫秒时间戳）→ `"2023-05-17"`
- 数字类型 `1684252800000` → `"2023-05-17"`

无需手动转换，引擎在 diff 和 save-state 时会自动归一化。

## 单选项读取格式

智能表格单选列读取时返回：
```json
[{"id": "oXXX", "style": 1, "text": "实现中"}]
```

diff 时取 `[0].text` 即可。状态枚举两边都用中文时可直接对比（用 `v_status` 传中文）。

## 反向同步 TAPD 更新

更新 TAPD 记录时：
- **优先用 `v_status` 传中文状态名**，避免 status 值映射麻烦
- 如果返回 422（工作流不允许跳转），标记为"待人工处理"，不静默失败
- 创建 TAPD 记录时可直接传 `status` 指定初始状态（部分模板支持）
