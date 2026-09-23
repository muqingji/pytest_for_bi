# AI 全栈开发工程师：两个月最小学习路线

## 一、目标定位

目标不是成为大模型研究员，而是成为能够使用 AI 编程工具完成全栈交付，并能设计、实现和评测多 Agent 系统的 AI 全栈开发工程师。

你已经具备一定 Agent 开发能力，因此不再把“如何调用一个模型、如何写一个简单 Agent”作为主线。主要补齐 AI 应用技术栈和多 Agent 编排中最容易失控的部分：角色边界、状态传递、任务交接、并发、收敛、失败恢复和全链路评测。

核心能力链路：

```text
Python
→ LLM API
→ Prompt Engineering
→ Structured Output
→ Embedding
→ RAG
→ Tool Calling
→ Multi-Agent Orchestration
→ AI 评测与安全
→ AI 应用部署
```

两个月内暂不学习：从零训练大模型、CUDA、分布式训练、复杂 RLHF 和 GPU 集群运维。

多 Agent 编排是本路线的重点，但只学习可落地的工作流、状态机、工具治理和评测，不追求复杂的自主智能体。

## 二、最小技术栈

| 模块 | 学习内容 | 推荐选择 |
| --- | --- | --- |
| 编程语言 | 异步、类型标注、HTTP、JSON、测试 | Python、pytest |
| API 服务 | 模型调用、业务接口、参数校验 | FastAPI、Pydantic |
| 大模型 | 对话、流式输出、Token、成本、重试 | 一个 OpenAI-compatible API |
| 输出控制 | JSON Schema、字段校验、失败重试 | Pydantic Structured Output |
| 知识库 | Embedding、切分、召回、引用 | PostgreSQL + pgvector |
| Agent | 工具调用、状态、终止条件、人工审批 | LangGraph 或现有编排框架 |
| 多 Agent | 路由、分工、交接、并发、收敛、恢复 | 状态机、事件、共享上下文 |
| 评测 | Golden Dataset、回归、幻觉、越权 | pytest + 自建评测集 |
| 工程化 | 日志、Token、延迟、脱敏、Prompt Injection | Python 日志与基础监控 |

## 三、八周计划

### 第 1 周：Python 最小基础

掌握函数、类、字典、列表、异常、文件、JSON、类型标注、虚拟环境、`async/await`、HTTP 请求和 pytest。

产出：一个 Python 命令行工具和一个能够接收 JSON 的 FastAPI 接口。

### 第 2 周：LLM API 与 Prompt

掌握 System/User 消息、上下文、多轮对话、流式输出、Temperature、Token、超时、重试、模型降级和 Prompt Injection 基础。

产出：缺陷描述分析 API，将自然语言转换为缺陷标题、严重程度、模块、复现步骤和缺失信息。

### 第 3 周：结构化输出与数据校验

学习 JSON Schema、Pydantic Model、枚举、必填字段、解析失败重试和降级策略。模型输出必须当作不可信外部输入处理。

产出：稳定返回以下结构的 API：

```json
{
  "severity": "high",
  "module": "login",
  "possible_cause": "unknown",
  "missing_information": []
}
```

### 第 4 周：Embedding 与 RAG

掌握文本清洗、Chunk、Overlap、Embedding、向量存储、Cosine Similarity、Top-K、Metadata Filter、上下文长度和引用。

产出：测试规范和历史缺陷知识库助手，回答时必须返回引用，找不到依据时明确说明不确定。

### 第 5 周：AI 应用技术栈补齐

集中补齐你做 Agent 时会反复用到的基础设施：Embedding、Rerank、结构化输出、Prompt 版本管理、模型路由、Token/延迟统计、缓存、重试、限流、超时、流式事件和审计日志。

产出：将已有 Agent 的模型调用、工具调用、Prompt、重试和日志抽成可复用模块，并为每个模块补最小测试。

### 第 6 周：多 Agent 编排基础

掌握工具定义、参数 Schema、调用循环、工具错误、超时、重试、权限、幂等和审计日志。多 Agent 中每个工具都必须明确归属 Agent 和权限范围，不能让所有 Agent 共享全部工具。

至少实现三个工具：

- `search_knowledge(query)`
- `query_bug(bug_id)`
- `get_service_logs(service, time_range)`

原则：AI 决定是否调用工具，代码负责校验参数、权限和副作用。

### 第 7 周：多 Agent 编排进阶

重点学习多 Agent 的五个核心问题：

1. **分工**：哪些工作由路由 Agent、检索 Agent、执行 Agent、审查 Agent 负责？
2. **交接**：Agent 之间传递什么最小状态、证据和待办，而不是传递整段上下文？
3. **编排**：什么时候使用串行、并行、分支、循环和人工审批？
4. **收敛**：什么条件下认为任务完成，如何防止 Agent 无限循环或重复派发？
5. **恢复**：某个 Agent 超时、返回空结果、工具失败或结果冲突时如何降级？

建议先实现显式状态机，再使用框架封装。不要把多个 Agent 简单串成“模型 A 调模型 B 调模型 C”。

建议掌握以下编排模式：

```text
Router → Specialist → Reviewer → Synthesizer
       ↘ Specialist ↗
```

以及：

- 串行流水线：上一个 Agent 的结果是下一个 Agent 的输入。
- 并行调查：多个 Specialist 独立取证，最后由 Synthesizer 汇总。
- 竞争假设：多个 Agent 分别提出根因，再由 Reviewer 比较证据。
- 监督者模式：Supervisor 选择下一个 Agent，但必须受最大步数和预算限制。
- 人工审批：高风险工具调用前暂停，等待明确批准。

产出：

```text
用户问题
→ 判断意图
→ 检索知识库
→ 必要时查询缺陷或日志
→ 汇总证据
→ 输出根因候选和下一步建议
```

### 第 8 周：多 Agent 评测、可观测性与面试项目

建立 Golden Dataset，测试正常输入、缺失信息、恶意 Prompt、超长输入、无答案、工具失败、非法 JSON、权限不足和越权访问。

至少评测：

- 结构化输出通过率
- 检索相关性
- 答案是否有证据支持
- 引用正确率
- 工具选择和参数正确率
- 幻觉率
- 延迟和 Token 成本

建立多 Agent 专用评测集：

- 路由是否选择正确 Agent
- 是否发生重复派发
- 交接状态是否完整
- 并发结果是否全部汇总
- 冲突证据是否被识别
- Agent 是否在预算内收敛
- 工具失败后是否正确恢复
- 是否出现循环、越权和隐式副作用

每次运行至少记录：`run_id`、`agent_id`、`parent_agent_id`、`task_id`、`handoff_id`、工具调用、输入输出摘要、耗时、Token、重试次数、终止原因。

### 面试项目与 AI 编程工作流

训练用 AI 实现功能的流程：

```text
需求拆解
→ 功能规格
→ 数据结构与 API 契约
→ 让 AI 先给方案
→ 分阶段实现
→ 让 AI 补测试
→ 运行测试
→ 根据错误修复
→ 人工 Review
```

每次给 AI 的任务都要包含目标、输入输出、约束、异常场景和验收标准，而不是只说“帮我做一个系统”。

## 四、最终练手项目

项目名称：**多 Agent AI 缺陷诊断与测试知识库助手**。

完整链路：

```text
用户输入缺陷描述
→ Router Agent 判断任务类型
→ 并行派发日志、知识库、历史缺陷 Specialist
→ 各 Agent 返回结构化证据和置信度
→ Reviewer Agent 检查证据冲突和缺口
→ Synthesizer Agent 输出结论
→ 高风险动作进入人工审批
→ 评测集自动回归
```

项目必须展示：

- Python/FastAPI 服务
- LLM 调用封装
- Pydantic 输出校验
- RAG 检索和引用
- 至少三个工具
- 多 Agent 角色、状态、交接和终止条件
- 并行执行与结果汇总
- 超时、重试、降级和人工审批
- Prompt 版本
- AI 回归测试集
- Token、延迟和错误日志
- Prompt Injection 与越权测试

## 五、面试必须能讲清楚的问题

1. 为什么把任务拆成多个 Agent，而不是一个强 Agent？
2. 如何定义 Agent 的边界和工具权限？
3. Agent 之间传递什么状态，如何避免上下文膨胀？
4. 什么时候并行，什么时候串行？如何保证结果汇总完整？
5. 如何防止循环、重复派发和无限重试？
6. Agent 结果冲突时由谁裁决？
7. 某个 Agent 超时或返回空结果时如何恢复？
8. 如何评测路由正确率、交接完整性和最终收敛率？
9. 为什么用 RAG，而不是把所有文档放进 Prompt？
10. 工具调用如何做权限校验、幂等和人工审批？
11. 如何测试幻觉、越权和 Prompt Injection？
12. 如何统计 Token、延迟和单次运行成本？

## 六、个人优势表达

测试工程师的优势不是“只会测试”，而是能够把质量能力迁移到 AI 系统：

> 我能够使用 Python 和 AI 编程工具完成 AI 全栈功能，并且会对结构化输出、检索结果、工具调用、权限边界、异常恢复和模型回归进行验证。相比只会调用模型 API，我更关注系统在错误输入和真实生产场景下是否可靠。

## 七、学习原则

- 只选一个模型 API、一个向量数据库和一个 Agent 框架。
- 先掌握 API、结构化输出、RAG 和可观测性，再把重点放到多 Agent 编排。
- 多 Agent 的核心不是 Agent 数量，而是职责边界、状态契约和可验证的收敛条件。
- 每个 Agent 都要有明确输入、输出、工具白名单、失败状态和终止条件。
- 优先实现 3 个角色协作的稳定系统，再扩展 Agent 数量。
- 每周必须有可运行产出。
- 所有 AI 结论都要能关联证据或明确标注不确定。
- 不把框架调用当作能力，必须理解 HTTP、检索、状态机和工具循环。
