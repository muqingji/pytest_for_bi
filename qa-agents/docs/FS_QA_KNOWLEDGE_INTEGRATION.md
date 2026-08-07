# fs-qa-knowledge 接入要求

`fs-qa-knowledge` 是 Case 草稿能力提供方，不是 QA 质量系统的发布端。生产接入前，该仓库
需要在一个固定 commit 中提供 `qa-agent-provider.json` 和无副作用入口。

## 必须提供的能力

```json
{
  "schema_version": "case-provider-capability/1.0",
  "mode": "artifact_only",
  "entrypoint": ["provider-command", "generate", "--artifact-only"],
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
- 进程退出后，由 QA 系统校验 Bundle，再由 A08 选择是否采用草稿。

## 当前兼容结论

冻结版本 `1ca888b645bd1c346b6d708a9a583af58d299fc8` 没有
`qa-agent-provider.json`，且 `testcase-generate` 的 Step 10.1 强制调用 `upload2fs`。因此当前
版本只能作为规范和人工能力参考，不能作为生产工作流中的无副作用 Provider 直接执行。

QA 系统会把该状态记录为 `incompatible`，不会静默降级为已接入，也不会修改
`fs-qa-knowledge` 仓库。
