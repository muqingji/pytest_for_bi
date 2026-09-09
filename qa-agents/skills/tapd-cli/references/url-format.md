# TAPD 链接格式与解析

从 TAPD URL 自动提取 `workspace_id` 和实体 ID，无需用户重复输入。

URL 可能包含 query 或 hash，解析时忽略无关参数。优先从路径中的 `{workspace_id}` 和实体 ID 提取；若新版 URL 无法提取实体 ID，应说明无法从链接确定 ID 并请用户补充，不要猜测 ID。

## 常见 URL 格式

| 类型 | URL 模板 | 提取说明 |
| --- | --- | --- |
| 项目首页（新版） | `tapd.cn/tapd_fe/{workspace_id}` | 提取 `workspace_id` |
| 需求列表（新版） | `tapd.cn/tapd_fe/{workspace_id}/story/list` | 提取 `workspace_id` |
| 需求详情 | `tapd.cn/{workspace_id}/prong/stories/view/{id}` | 提取 `workspace_id` 与需求 `id` |
| 任务详情 | `tapd.cn/{workspace_id}/prong/tasks/view/{id}` | 提取 `workspace_id` 与任务 `id` |
| 缺陷详情 | `tapd.cn/{workspace_id}/bugtrace/bugs/view/{id}` | 提取 `workspace_id` 与缺陷 `id` |
| 迭代 | `tapd.cn/{workspace_id}/prong/iterations/card_view/{id}` | 提取 `workspace_id` 与迭代 `id` |
| Wiki | `tapd.cn/{workspace_id}/markdown_wikis/show/#{id}` | 提取 `workspace_id` 与 Wiki `id` |
| 测试用例 | `tapd.cn/{workspace_id}/sparrow/tcase/view/{id}` | 提取 `workspace_id` 与用例 `id` |
| 测试计划 | `tapd.cn/{workspace_id}/sparrow/testplan/view/{id}` | 提取 `workspace_id` 与计划 `id` |

## 提取示例

- 链接：`https://www.tapd.cn/20019471/prong/stories/view/1120019471001400908`
  - 提取结果：`workspace_id=20019471`，实体类型为 `story`，`id=1120019471001400908`
- 链接：`https://www.tapd.cn/20019471/bugtrace/bugs/view/1120019471001056789`
  - 提取结果：`workspace_id=20019471`，实体类型为 `bug`，`id=1120019471001056789`
- 链接：`https://www.tapd.cn/tapd_fe/20019471`
  - 提取结果：`workspace_id=20019471`
