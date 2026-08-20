# 自动化代码审核

**目标**

确认 A14/A15 生成的自动化候选、独立复核结论与 N05 确定性代码检查结果一致，批准后进入 N08 受控自动化执行。

**背景**

N05 确定性代码检查已通过（生成 `1` 个、候选 `6` 个、复核问题 `0` 个）。

**范围**

包含：
- 6 个自动化候选的 Manifest、候选代码与安全红线。
- A18-BE / A18-CT 独立复核结论与阻塞问题。

不包含：
- 修改候选代码本身；需要修改时置 blocked 回流对应生成/复核节点。

**输入材料**

- `n05-automation-code-check`：`sha256:75fa18f8e26cb1e76a3840f5b0d36999280b4276ecab22fa5b1ac229e36419ea`
- `a14-backend-automation-generation`：`sha256:74d222b347caf79b731023a43dcb7094ea9803fa7d9a4363373e4c6c94806b53`
- `a18-be-backend-automation-review`：`sha256:3391a8255b0ac9d804e51cafc0e90bc5751d71c1617357cbe99e59cb8efbb72d`
- 本 Issue 附件：`g03-review-request.json`

**本批生成与复核明细**

- `A14` 生成 `6` 个候选（Manifest `manifest-a14-backend`，拒绝 `0`）
- `A18-BE` 复核结论 approved=True，问题 `0` 个

**本批候选覆盖 Case**

1. `TC-BE-001-BACKEND` 自定义维度三类位置的专用错误与双语提示（critical / P0）
   - 候选文件：`generated/backend/test_tc_be_001_backend.py`
   - 覆盖预期：EXP-BE-001-01、EXP-BE-001-02、EXP-BE-001-03
2. `TC-BE-002-BACKEND` 结果集筛选指标名称解析、全部名称参数与本地化（critical / P0）
   - 候选文件：`generated/backend/test_tc_be_002_backend.py`
   - 覆盖预期：EXP-BE-002-01、EXP-BE-002-02、EXP-BE-002-03、EXP-BE-002-04、EXP-BE-002-05、EXP-BE-002-06、EXP-BE-002-07、EXP-BE-002-08
   - 人工确认项：EXP-BE-002-08
3. `TC-BE-003-BACKEND` 多关联关系失败替换与原成功关系回归（critical / P0）
   - 候选文件：`generated/backend/test_tc_be_003_backend.py`
   - 覆盖预期：EXP-BE-003-01、EXP-BE-003-02、EXP-BE-003-03、EXP-BE-003-04
4. `TC-BE-004-BACKEND` 所有 what 和 what-list 动态关联识别及非动态控制（critical / P0）
   - 候选文件：`generated/backend/test_tc_be_004_backend.py`
   - 覆盖预期：EXP-BE-004-01、EXP-BE-004-02、EXP-BE-004-03、EXP-BE-004-04、EXP-BE-004-05、EXP-BE-004-06
   - 人工确认项：EXP-BE-004-05、EXP-BE-004-06
5. `TC-BE-005-BACKEND` 多原因单提示且无固定业务优先顺序（critical / P0）
   - 候选文件：`generated/backend/test_tc_be_005_backend.py`
   - 覆盖预期：EXP-BE-005-01、EXP-BE-005-02、EXP-BE-005-03
6. `TC-BE-006-BACKEND` 权限错误优先与指标名称防泄露（critical / P0）
   - 候选文件：`generated/backend/test_tc_be_006_backend.py`
   - 覆盖预期：EXP-BE-006-01、EXP-BE-006-02、EXP-BE-006-03

**怎么反馈**

这是交付评审，不是审批仪式：

- 发现候选不安全 / Manifest 绑定错误 / 复核结论不一致：**在评论里逐条写明问题**，然后置 **blocked**。
- 评论内容会被作为修正指令回流：A14/A15 修正候选 → A18 复核 → N05 重新检查 → 重新生成审核卡给你。
- 没有问题：置 **done** 进入 N08 受控自动化执行。
- 保持 **in_review**：流程保持暂停。

**验收**

- 置 **done**：候选与复核结论一致，继续 N08。
- 置 **blocked**（必须带评论）：回流生成/复核节点修正。
- 置 **cancelled**：终止当前流程。
