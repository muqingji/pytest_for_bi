# Pilot 001：下钻查看明细提示文案优化

## 样本目的

该样本是生产级 QA 多 Agent 系统的首个纵向流程基准，覆盖：

```text
N00 确定性模板选择
  -> N01/N02 远端输入采集、ChangeSet 标准化与冻结
  -> A02 需求分析
  -> A03 技术方案与可测性分析
  -> A05 后端 commit 分析
  -> A06 需求、方案与实现对齐
  -> N24 确定性风险策略，未知项才调用 A07
  -> A08 测试设计
  -> A09 Oracle 与测试防范覆盖审查
  -> N04 Test Case IR 校验
```

本需求没有前端实现，A04 应输出 `skipped_by_policy/not_applicable`，不能输出
`blocked_input`。接口错误码会被 Web、移动端和拼表消费，因此契约和端到端验证仍属于
测试范围。

## 特殊输入特征

- PRD 是体验优化合集，目标范围只能取“下钻查看明细提示文案优化”章节。
- 实现链接是 merge commit，不是 MR。代码分析使用 merge commit 相对第一父提交的完整
  first-parent diff。
- `fs-bi-dev-platform` 是拼表透传依赖，但本样本没有提供该仓库的变更 commit；应记录为
  参考基线和待验证依赖，不能虚构其实现变化。
- 远端 Story 中已有 `qa/test-cases.md`，但内容为空表，可作为“没有有效存量 Case”的证据。
- 业务代码及其 Git 元数据全程只读。

## 文件说明

| 文件 | 用途 | 是否可传给 Agent |
| --- | --- | --- |
| `input/workflow-input.json` | 用户目标、Story 范围、组件适用性 | 是 |
| `input/source-snapshot.json` | 冻结的远端来源和 commit 关系 | 是 |
| `input/source-material.json` | N01 从远端固定 commit 采集的正文和 diff；执行 collect 后生成 | 是 |
| `oracle/expected-routing.json` | A01 和分支路由基准 | 否 |
| `oracle/expected-analysis.json` | 需求、实现事实、差异和待确认项基准 | 否 |
| `oracle/expected-test-obligations.json` | A08/A09 必须召回的测试义务 | 否 |
| `oracle/expected-safety.json` | 业务仓库只读和输入隔离基准 | 否 |

本地目录中的 oracle 只供开发自检。正式评估时应导入受限 Oracle Registry，并向 Agent
容器只挂载 `input/`；不得把整个 QA 仓库作为 Agent 可搜索工作区。

## 当前边界

该样本当前用于设计与静态分析流程，不包含测试环境、账号、真实业务数据或接口凭证，因而
不能据此声称已经完成真实接口执行。进入 N07/N08 前必须另行提供脱敏测试数据、部署 commit
和只读/最小权限测试账号。
