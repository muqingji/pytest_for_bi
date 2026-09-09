---
name: constructed-asset-card-display
description: "把 112 环境实际构造成功的测试数据按分类回显到 Multica 任务详情。C5/C6 阶段卡和 N08 记录卡在产出之后必须展示「已构造测试数据」；分类顺序固定为统计图、报表、交叉表、驾驶舱、指标、自定义维度，有拼表再追加。实现或修改该回显时必须遵循本规范。"
---

# 已构造测试数据回显规范

适用范围：`qa-agents/src/qa_agents/constructed_assets.py`（唯一渲染器）、
`card_copy.py`（N08 记录卡）、`workflow_center.py`（C5/C6 阶段卡）、
`test_data.record_constructed_test_data`（库存写入）、
N08 执行收集的 `constructed-assets.json`。

## 目标

打开 C5、C6 或 N08 任务详情时，不翻 JSON、不看内部路径，也能按资产类别看到
本次在 112 **实际构造成功** 的名称和 ID。

## 强制规则

### 1. 只展示构造成功的数据

- 来源优先级：`constructed-test-assets.json` → N08 `constructed-assets.json` →
  已登记为 `constructed` 的 env-observed / A22 计划项。
- 禁止把「计划要造」但 setup 未完成的资源当成已构造。
- 禁止把 `qa-probe-*`、探测副本、JSON 路径、`resource_key` 当主信息。

### 2. 分类与顺序固定

必选六类，即使某类为空也要写「无」：

1. 统计图
2. 报表
3. 交叉表
4. 驾驶舱
5. 指标
6. 自定义维度

可选类：有数据才追加「拼表」；无法归类时才追加「其他」。

资源类型映射：

- 统计图：`stat_chart`
- 报表：`report`
- 交叉表：`pivot_table` / `pivot`
- 驾驶舱：`dashboard`
- 指标：`aggregate_metric` / `ordinary_metric` / `calculated_metric` / `comparison_metric`
- 自定义维度：`custom_dimension`
- 拼表：`joined_table` / `joined_report`

### 3. 每条资产的人话格式

```text
## 已构造测试数据

### 统计图
- `自定义维度查看明细验证统计图`（`BI_xxx`） · 目录：示例

### 指标
- `基线聚合指标`（`BI_xxx`）

### 自定义维度
- `客户等级枚举分组自定义维度`（`BI_xxx`） · 主题：客户
```

- 有名称：`` `名称`（`ID`） ``；可选 `目录：` / `主题：`。
- 名称必须是 A22 能力目录里贴合用例语义的中文可见名（见 `retained-test-asset-naming`），
  由 `asset_scene_naming.scene_display_name` 按 `resource_key` 解析。
  例如统计图显示 `自定义维度查看明细验证统计图`，不要显示短标签 `自定义维度`，
  也不要用 `resource_key`、英文 title、`qa-*`、`销售订单统计_副本N` 当主名称。
- 无 ID：省略括号，不要编造。不要用「未记录名称」凑数。
- 面向用户的段落禁止出现 `issue_code`、hash、JSON 路径。

### 4. 挂载位置

在五段式与运营段落实后追加，不要插进目标/背景/范围：

- C5 / C6 阶段卡：`## 产出` 之后、`## 异常处理` 之前。
- N08 记录卡：`## 产出` 之后、`## 你需要处理` 之前。
- 没有构造成功项时整节省略，不要输出六类全是「无」。

渲染必须走 `qa_agents.constructed_assets.render_constructed_assets_markdown`，
再由 `card_copy.constructed_assets_markdown` 挂到卡片；禁止各模块裸拼分类标题。

### 5. 名称与 ID 的证据

生命周期证据仍只允许 hash，不能把资源 ID 写进 `lifecycle.json`。
setup 成功后把 `{type, id, display_name, folder_name?, subject?}` 写到 sibling
`{case_id}.constructed-assets.json`，N08 聚合成 `constructed-test-assets.json`。

## 反例

- 用 `a22-test-data-plan.json` 路径、`variant_chart_set` 或「未记录名称」当卡片主信息。
- 只在对话里口述构造结果，不写进任务详情。
- 把计划中的报表/驾驶舱列成已构造，但 N08 并未创建成功。
- 分类顺序改成英文，或空类直接删掉必选六类。

## 验收

- [ ] C5/C6 在有库存时出现 `## 已构造测试数据`，六类齐全，空类为「无」
- [ ] N08 记录卡同样按分类列出名称 + ID
- [ ] 渲染走 `constructed_assets` / `card_copy`，不在业务模块裸拼
- [ ] `lifecycle.json` 仍不含资源 ID；名称/ID 在 constructed-assets 库存中
- [ ] 全量测试通过（`cd qa-agents && ../.venv/bin/python -m pytest -q`）
