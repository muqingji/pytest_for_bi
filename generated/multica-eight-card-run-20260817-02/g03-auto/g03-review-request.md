# 自动化代码审核

**目标**

确认 A14/A15 生成的自动化候选、独立复核结论与 N05 确定性代码检查结果一致，批准后进入 N08 受控自动化执行。

**背景**

N05 确定性代码检查已通过（生成 `1` 个、候选 `1` 个、复核问题 `0` 个）。

**范围**

包含：
- 1 个自动化候选的 Manifest、候选代码与安全红线。
- A18-BE / A18-CT 独立复核结论与阻塞问题。

不包含：
- 修改候选代码本身；需要修改时置 blocked 回流对应生成/复核节点。

**输入材料**

- `n05-automation-code-check`：`sha256:02516229dc95e55f3bb2c519728374b459fb0d018d904729f7f7a4f6829735b8`
- `a14-backend-automation-generation`：`sha256:9ba9e7f97f436f2e0cd5e596aaedaad81cd0443bd77d431f4e2c7152c0287d51`
- `a18-be-backend-automation-review`：`sha256:18c7ee682b4a43018af6ed8c011bed0edc3327b29b4ffbeb68391df59c27b462`
- 本 Issue 附件：`g03-review-request.json`

**本批生成与复核明细**

- `A14` 生成 `1` 个候选（Manifest `manifest-a14-backend`，拒绝 `5`）
- `A18-BE` 复核结论 approved=True，问题 `0` 个

**本批候选覆盖 Case**

1. `TC-BE-001-BACKEND` 自定义维度三类位置的专用错误与双语提示（critical / P0）
   - 候选文件：`generated/backend/test_TC_BE_001_BACKEND.py`
   - 覆盖预期：EXP-BE-001-01、EXP-BE-001-02、EXP-BE-001-03

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
