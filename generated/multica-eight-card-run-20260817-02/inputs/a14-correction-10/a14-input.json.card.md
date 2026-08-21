# A14 服务端自动化生成

## 目标

按执行计划把后端用例生成独立 pytest 接口自动化候选，并产出自动化 Manifest。

## 背景

C4 执行计划确定后由 A14 生成后端自动化；候选须绑定接口、测试数据计划与 Oracle，经 A18-BE 独立复核、N05 代码检查与 G03 人工审核后才可执行。

## 范围

包含：
- 绑定接口、数据计划与 Oracle 生成 pytest
- 维护每条 Case 到用例的可追溯性
- 产出自动化 Manifest 与 pytest 候选文件

不包含：
- 直接写业务仓库或发布
- 跳过独立复核与安全校验直接执行

## 输入材料

- 输入参数包（附件：`a14-input.json`）
- C4 执行计划与 Test Case IR
- 冻结 OpenAPI 与契约
- A22 测试数据计划

## 验收

- 产出 a14-backend-automation-generation 与自动化 Manifest 并入库
- 每条 Case 可追溯且断言有效，通过 N05 确定性代码检查
