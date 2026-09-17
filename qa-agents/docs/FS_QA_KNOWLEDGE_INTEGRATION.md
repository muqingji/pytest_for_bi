# fs-qa-knowledge Case Provider 接入方案

`fs-qa-knowledge` 是 Case 草稿能力提供方，不是 QA 质量系统的发布端。生产接入前，该仓库
需要在一个固定 commit 中提供 `qa-agent-provider.json` 和无副作用入口。A08 保留
Test Case IR 补全和纠错职责，G02 是 Provider 用例与 A08 补充用例的唯一人工审核点。

## 必须提供的能力

```json
{
  "schema_version": "qa-agent-provider/1.0",
  "mode": "artifact_only",
  "entrypoint": "provider-command generate --artifact-only",
  "input_contract": "case-provider-input/1.0",
  "output_contract": "case-provider-output/1.0",
  "side_effects": []
}
```

`artifact_only` 模式必须满足：

- 只读取调用方提供的冻结需求分析 Artifact。
- 只在调用方分配的临时输出目录生成 JSON 或 Markdown Bundle。
- 不调用 `upload2fs`、`md2excel`、Git 写命令、MR API 或消息通知。
- 不读取生产登录凭证。
- 返回完整 40 位 `provider_commit`、Case 来源引用和实际副作用列表。
- 进程退出后，由 QA 系统校验 Bundle，再由 A08 转换为正式 Test Case IR。

## 数据口径

Provider 只接收 `case-provider-input/1.0`，包含冻结的需求、G01 已批准范围、N24 策略和
来源引用。Provider 输出 `case-provider-output/1.0`。A08 补齐 `test-design-ir/1.1` 要求的
intent、layer、risk、test_data、Oracle、cleanup、execution_policy 和自动化候选字段。

A08 必须为每个 Provider Case 输出唯一映射：

```json
{
  "provider_case_id": "FS-20260910-001",
  "test_case_ir_id": "CASE-001"
}
```

Provider Case 到 A08 `parent_cases` 必须是双射：禁止遗漏、合并、一对多、多对一或引用
不存在的 IR Case。A08 可以为 G01/N24 未覆盖义务新增非 Provider Case。

## 统一审核与下游

A09 和 N04 继续校验完整 A08 Test Case IR。G02 每条审核项显示对应
`provider_case_id`，人工在同一个 Gate 审核 Provider 派生和 A08 补充用例。G02 通过后，N25 只消费
正式 IR 并按测试层拆分；选择、自动化、测试数据、执行和报告无需感知 Provider 格式。

## 运行时接入

Multica 同步器在 G01 通过并生成 N24 后，会先写出：

```text
generated/<run>/inputs/case-provider-input.json
```

该文件按 `case-provider-input/1.0` 冻结 A02 需求、G01 批准范围、N24 策略、Run 与
Source Snapshot，并包含 `input_hash`。Provider 输出必须写到：

```text
generated/<run>/inputs/case-provider-output.json
```

输出必须绑定同一个 Run、Source Snapshot 和 `input_hash`，声明
`mode=artifact_only`、`side_effects=[]`、`provider_commit` 和
`case-provider-output/1.0`。同步器会核对已评审 inspection；未评审 commit、有副作用、
哈希不匹配或 `production_enabled!=true` 都拒绝注入 A08。

若 Provider 维护者交付的是文档规定的 8 列 merged Markdown 表格，可先执行：

```bash
PYTHONPATH=qa-agents/src .venv/bin/python \
  qa-agents/scripts/convert_case_provider_markdown.py \
  --input generated/<run>/inputs/case-provider-input.json \
  --markdown /path/to/testcase.md \
  --provider-commit <40位commit> \
  --output generated/<run>/inputs/case-provider-output.json
```

转换器只做本地文件读取和 JSON 写入，不调用 `md2excel`、`upload2fs` 或任何外部系统。

新需求模板已设置：

```json
{
  "case_provider_required": true
}
```

该开关开启时，没有合规 Provider 输出就不会派发 A08；同步器返回
`case_provider_blocked`，不会静默生成纯 A08 Case。可用
`case_provider_output` 配置项指定非默认路径。

## 当前兼容结论

已评审并钉死的 Provider commit 为 `64cf10c3d2e030285f7f634a4cc5c61539546713`
（`refs/heads/main`，2026-09-10 远程探查）。该提交没有 `qa-agent-provider.json`，且
`testcase-generate` 的 Step 10.1 强制调用 `upload2fs`。状态为 `incompatible`。

历史试点 `pilot-001` 仍冻在 `1ca888b645bd1c346b6d708a9a583af58d299fc8`，只作审计回放。
未写入 `knowledge/case-provider-inspection.json` 的新 commit 一律 fail-closed，不能跟随
`origin/main` 漂移。

消费端已具备：artifact-only 合同、A08 一一映射、未覆盖义务补 Case、IR 字段补全、
G02 展示 `provider_case_id`、影子对比。上游未提供无副作用入口前，`production_enabled`
保持 false，只允许影子运行。

QA 系统不会静默降级为已接入，也不会修改 `fs-qa-knowledge` 仓库。所需 manifest 见
`contracts/qa-agent-provider.schema.json`。

## 上线顺序

1. Provider 远程仓库增加 `qa-agent-provider.json` 和真正无副作用的 artifact-only 入口。
2. 评审新 commit 后写入 `knowledge/case-provider-inspection.json`，并在 workflow snapshot 钉死。
3. 影子运行 `compare_provider_shadow`，比较 Provider 覆盖率、双射和 A08 补充 Case。
4. 只有当双射、A09、N04 和 G02 集成测试通过后才启用 Provider Case。
5. 不删除 A08 的 IR 补全、Oracle 建模或纠错能力。
