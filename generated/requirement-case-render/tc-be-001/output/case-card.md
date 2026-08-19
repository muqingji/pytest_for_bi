### `TC-BE-001` 自定义维度三类位置的专用错误与双语提示 · backend / critical / P0

**测试场景**

自定义维度字段位于维度、数据范围、下钻三类位置时，通过保存资产的查看明细入口触发查看明细，均被拒绝进入明细视图：返回专用错误码 s307011534，zh_CN 与 en 运行时消息精确为批准模板。

**前置条件**

- 已构造并保存含自定义维度字段的统计图/拼表/交叉表资产，配置回查中精确出现自定义维度 ID

**测试步骤**

1. 构造并保存 dimension 变体资产，配置回查确认自定义维度 ID 出现在维度位置
2. 构造并保存 data_range 变体资产，配置回查确认自定义维度 ID 出现在数据范围位置
3. 构造并保存 drill_field 变体资产，配置回查确认自定义维度 ID 出现在下钻字段位置
4. 依次通过三个变体资产的查看明细入口实际触发查看明细，记录 detail_api 响应
5. 比对 detail_api.error 的 code、message.zh_CN、message.en 实际值与预期结果

**预期结果**

- `EXP-BE-001-01`：三个变体均拒绝查看明细并返回错误码 s307011534。
- `EXP-BE-001-02`：zh_CN 运行时消息精确为批准模板：「维度或数据范围中使用了自定义维度字段，暂不支持查看明细」
- `EXP-BE-001-03`：en 运行时消息精确为批准模板：`Custom dimension fields are used in the dimension or data range. Details view is not supported.`