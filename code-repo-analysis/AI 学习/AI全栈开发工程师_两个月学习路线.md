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

## 三、逐周详细学习内容、练习与资料

本节是八周计划的详细说明。每周按“概念 → 最小实现 → 异常测试 → 接入最终项目”的顺序推进。B 站用于建立直觉，官方文档用于确认参数和版本；视频链接失效时，按同一行的搜索关键词寻找替代视频。

### 第 1 周：Python、HTTP、FastAPI 与 pytest

#### 要学习什么

- **Python 基础**：函数、类、列表、字典、集合、异常、文件、JSON、模块和依赖管理。重点是能把每个 Agent、工具和业务步骤拆成可测试的函数。
- **类型标注与数据建模**：掌握 `str`、`int`、`bool`、`list[T]`、`dict[K, V]` 和可选类型；用 `dataclass` 或 Pydantic 表达请求、响应、配置和 Agent 状态。
- **异步编程**：理解协程、事件循环、`async`、`await` 和 `asyncio.gather`。异步主要解决网络等待，不会自动加速 CPU 密集型任务。
- **HTTP**：掌握方法、状态码、请求头、JSON、鉴权、超时和幂等性；能区分 4xx 输入/权限问题与 5xx 服务问题。
- **FastAPI**：路由、请求体、响应模型、参数校验、异常处理和接口文档。
- **pytest**：测试函数、fixture、参数化、mock 和异步接口测试。真实模型 API、数据库和日志服务都应在单元测试中 mock。

#### 为什么要学

LLM 应用本质上仍是软件系统。模型只是其中一个不稳定的外部依赖；如果不了解异常、超时、接口契约和测试，后面的 Agent 编排也无法稳定运行。

#### 动手练习

1. 写一个命令行工具：读取缺陷 JSON 文件，统计严重程度和模块分布。
2. 写一个 `POST /defects/normalize` 接口，接收标题、描述和环境信息，返回清洗后的 JSON。
3. 为合法输入、缺少字段、字段类型错误、空描述和业务异常各写测试。
4. 把业务逻辑从 FastAPI 路由抽到 service 函数，测试 service 时不启动 Web 服务。

#### 本周验收标准

- 能启动 FastAPI，并通过接口文档发送 JSON 请求。
- 至少有 8 个测试，覆盖成功、校验失败、业务异常和未知异常。
- API Key、数据库密码等敏感信息只从环境变量读取。
- 测试不依赖网络和真实模型服务。

#### B 站与文档

- B 站搜索：`Python 基础教程 函数 类 异常 JSON`。
- B 站搜索：`Python async await asyncio 异步编程`。
- B 站搜索：`FastAPI Pydantic Python 接口开发`。
- B 站搜索：`pytest 单元测试 fixture mock 参数化`。
- FastAPI：<https://fastapi.tiangolo.com/>；Pydantic：<https://docs.pydantic.dev/>；pytest：<https://docs.pytest.org/>。

### 第 2 周：LLM API 与 Prompt Engineering

#### 要学习什么

- **LLM、Token 和上下文**：理解模型根据上下文预测后续 Token；Token 影响上下文长度、延迟和费用，上下文越长不代表答案一定越好。
- **角色消息**：理解 system、user、assistant、tool 的职责，知道权限和业务规则不能只放在用户输入中。
- **API 调用**：模型、消息、最大输出 Token、温度、响应格式、工具和请求 ID；API Key 必须从环境变量读取。
- **稳定性**：处理超时、限流、网络中断、空响应和服务不可用；区分可重试与不可重试错误，使用有限次数的指数退避。
- **流式输出**：理解增量事件、结束事件和中途失败；流式只改善体验，最终结果仍需校验。
- **Prompt 结构**：任务、背景、输入、约束、输出格式和示例；掌握 zero-shot、few-shot、分隔符和任务拆解。
- **Prompt Injection**：把缺陷描述、日志、网页和知识库文档视为不可信数据，不能让文档中的指令改变工具权限。

#### 为什么要学

“会调用模型”不等于“会做 LLM 应用”。工程重点是请求失败怎么办、输出不符合预期怎么办、输入里藏着恶意指令怎么办，以及如何用固定样例判断 Prompt 是否变好了。

#### 动手练习与验收

1. 实现 `POST /defects/analyze`，输出缺陷标题、严重程度、模块、复现步骤、影响范围和缺失信息。
2. 增加超时、重试、日志和模型错误响应。
3. 准备 10 个正常缺陷、3 个信息不足缺陷、3 个恶意指令样例。
4. 维护至少两个 Prompt 版本，比较固定样例上的结果。
5. 验收：API Key 不出现在日志中；超时、限流和模型错误有明确处理；恶意输入不会扩大权限。

#### B 站与文档

- B 站搜索：`吴恩达 面向所有人的生成式 AI`。
- B 站搜索：`ChatGPT Prompt Engineering for Developers 中文版`。
- 现有直链参考：<https://www.bilibili.com/video/BV1Bo4y1A7FU>。
- B 站搜索：`使用 ChatGPT API 构建系统 吴恩达`；现有直链参考：<https://www.bilibili.com/video/BV1R7pMzpESQ/>。
- B 站搜索：`LLM API Python 大模型 API 调用`。
- Datawhale LLM Cookbook：<https://datawhalechina.github.io/llm-cookbook/>。

### 第 3 周：结构化输出与数据校验

#### 要学习什么

- **JSON Schema**：对象、数组、字符串、数字、布尔、枚举、必填字段、默认值和嵌套结构。
- **Pydantic Model**：定义请求、模型输出、错误响应和内部状态；用枚举限制严重程度、任务类型和状态。
- **解析失败类型**：区分 JSON 语法错误、字段缺失、字段类型错误、枚举不合法和业务语义错误。
- **结构化输出**：优先使用模型或 SDK 的结构化输出能力；“请只返回 JSON”不能代替代码校验。
- **重试与降级**：解析失败时有限重试；仍失败则返回 `needs_review` 或 `unknown`，不能伪造默认结论。
- **API 契约**：明确成功、输入错误、模型错误、校验失败和人工复核的响应结构，并为请求增加 `request_id`。

#### 动手练习

用以下结构实现稳定 API：

```json
{
  "severity": "high",
  "module": "login",
  "title": "登录接口在特定条件下返回 500",
  "reproduction_steps": [],
  "possible_cause": "unknown",
  "missing_information": [],
  "needs_human_review": false
}
```

测试合法 JSON、缺少必填字段、枚举错误、字段类型错误、Markdown 代码围栏、截断 JSON、额外字段、语义冲突和模型超时。

#### 本周验收标准

- 所有模型输出先解析再进入业务逻辑。
- 非法输出有重试上限和可观察的失败原因。
- 业务代码能区分“没有结论”和“结论为 unknown”。
- 无法可靠解析时明确标记人工复核或不确定。

#### B 站与文档

- B 站搜索：`大模型 结构化输出 JSON Schema Pydantic`。
- B 站搜索：`Pydantic 数据校验 FastAPI`。
- B 站搜索：`Function Calling 工具调用 JSON Schema`。
- Pydantic：<https://docs.pydantic.dev/latest/concepts/models/>。
- JSON Schema：<https://json-schema.org/learn/getting-started-step-by-step>。

### 第 4 周：Embedding 与 RAG

#### 要学习什么

- **文档清洗**：处理 Markdown、HTML、PDF、纯文本、日志和表格；保留标题、列表、代码块、表格列名和章节路径。
- **统一文档模型**：保存 `document_id`、标题、来源、版本、更新时间、权限范围和正文。
- **Chunk 与 Overlap**：优先按标题、段落和语义边界切分；Overlap 用于减少边界信息丢失，但过大则浪费上下文。
- **Embedding**：把文本转换为向量，用于语义相似检索；它不是摘要，也不是答案生成。
- **向量存储**：在 PostgreSQL + pgvector 中保存文档、Chunk、向量和 Metadata。
- **Cosine Similarity 与 Top-K**：理解相似度分数和候选数量；阈值必须用真实问题校准。
- **Metadata Filter**：按项目、版本、文档类型和权限过滤，防止跨项目泄露。
- **上下文长度**：为系统 Prompt、用户问题、召回片段、历史对话和预留输出分配 Token 预算。
- **引用与拒答**：每个关键结论必须关联来源；检索不到依据时明确说明不确定，不允许补写看似合理的结论。

#### 为什么要学

RAG 不是“把文档丢给模型”，而是一条可测试的数据链路：采集、清洗、切分、向量化、过滤、召回、排序、拼接上下文、生成答案和返回引用，任何一环都可能导致幻觉或越权。

#### 推荐 Chunk 数据结构

```json
{
  "document_id": "test-spec-login-v3",
  "chunk_id": "test-spec-login-v3-chunk-007",
  "title": "登录模块测试规范",
  "section": "异常登录测试",
  "content": "连续失败五次后账号进入短暂锁定状态。",
  "source": "docs/test-spec-login.md",
  "version": "3.0",
  "metadata": {
    "project": "bi",
    "doc_type": "test_spec",
    "access": "qa"
  }
}
```

#### 动手练习与验收

1. 准备至少 20 份测试规范和历史缺陷，统一成带元数据的文档。
2. 实现清洗、切分、Embedding、入库和增量更新脚本。
3. 实现 `search_knowledge(query, project, doc_type, version)`。
4. 为 20 个问题标注正确文档和 Chunk，比较 Chunk 大小、Overlap 和 Top-K。
5. 对无答案问题返回“知识库中没有足够依据”，没有引用的回答必须测试失败。

#### B 站与文档

- B 站搜索：`Embedding 向量数据库 RAG 原理`。
- B 站搜索：`RAG 知识库 pgvector PostgreSQL`。
- B 站搜索：`LangChain RAG 文档切分 向量检索`。
- RAG 视频参考：<https://www.bilibili.com/video/BV1d2R4BMEbm>、<https://www.bilibili.com/video/BV1ug3qzhEp9>、<https://www.bilibili.com/video/BV1K6516CEgg>。
- pgvector：<https://github.com/pgvector/pgvector>；PostgreSQL：<https://www.postgresql.org/docs/>。

### 第 5 周：AI 应用基础设施与可复用模块

#### 要学习什么

- `ModelClient`：统一模型请求、流式事件、超时、重试和错误映射。
- `EmbeddingClient`：统一批量向量化、限流、模型版本和缓存。
- `PromptTemplate`：管理模板、版本、变量、输出约束和变更记录。
- `StructuredParser`：统一解析、Pydantic 校验、错误重试和降级。
- `RetryPolicy`：区分可重试与不可重试错误，限制次数和总耗时。
- `ToolExecutor`：统一参数校验、权限、超时、幂等、审计和结果格式。
- `Metrics` 与 `AuditLogger`：记录运行、耗时、Token、错误、工具调用和终止原因。
- **Rerank 与模型路由**：理解向量召回和重排序的差异；让模型路由规则可解释、可测试。
- **缓存、限流和事件**：定义缓存失效条件，按请求数和 Token 限流，并统一运行事件格式。

#### 为什么要学

如果每个 Agent 都自己处理 HTTP、重试、日志和 Token 统计，系统会迅速出现行为不一致。基础设施层让业务 Agent 只关心任务，不重复实现可靠性细节。

#### 动手练习与验收

1. 把第 2 周的模型调用替换为 `ModelClient`。
2. 为模型、Embedding、工具和 Prompt 各写一个 mock 单元测试。
3. 故意制造超时、非法 JSON 和工具异常，验证错误可以分类和追踪。
4. 每次调用都能查到模型、Prompt 版本、耗时、Token、重试次数和结果状态。

#### B 站与文档

- B 站搜索：`大模型应用工程化 Token 统计 日志 重试 限流`。
- B 站搜索：`RAG rerank 重排序 原理 实战`。
- B 站搜索：`LangSmith LLM 可观测性 Trace`。
- Python 日志：<https://docs.python.org/3/library/logging.html>。
- OpenTelemetry：<https://opentelemetry.io/docs/>。

### 第 6 周：Tool Calling 与单 Agent 工具治理

#### 要学习什么

- **工具定义**：名称、用途、参数 Schema、返回 Schema、权限范围、超时和副作用。
- **参数校验**：模型生成的参数必须经过 Pydantic 或 JSON Schema 校验，不能直接进入执行函数。
- **调用循环**：模型决定是否调用工具，代码校验工具名和参数、检查权限、执行工具，再把结构化结果返回模型。
- **权限与副作用**：查询工具和写入工具分开；删除、发布、发送等高风险动作默认需要人工审批。
- **幂等和审计**：写入工具使用幂等键；记录用户、Agent、时间、参数摘要、结果和审批状态。
- **预算与终止**：限制最大工具调用次数、总耗时、Token 预算和重复任务。

#### 必须实现的工具

```text
search_knowledge(query, project, doc_type)
query_bug(bug_id)
get_service_logs(service, time_range)
```

日志工具必须校验时间范围和服务白名单；缺陷查询工具必须校验项目权限；知识库工具必须执行 Metadata Filter。

#### 本周验收标准

- 单 Agent 能正确选择三个工具，并处理空结果和工具错误。
- 非法工具名、缺失参数、越权参数和超时请求不会进入真实执行函数。
- 工具调用有最大次数和总预算，测试能证明不会无限循环。
- 高风险动作暂停等待人工批准，拒绝后不会执行副作用。

#### B 站与文档

- B 站搜索：`Function Calling Tool Calling 工具调用 大模型`。
- B 站搜索：`Agent 工具调用 循环 权限 控制`。
- B 站搜索：`LangChain Tools Agent 实战`。
- LangGraph：<https://docs.langchain.com/oss/python/langgraph/overview>。
- OWASP LLM Top 10：<https://owasp.org/www-project-top-10-for-large-language-model-applications/>。

### 第 7 周：多 Agent 编排、状态、并发与恢复

#### 要学习什么

- **角色边界**：Router、Knowledge Specialist、Log Specialist、Bug Specialist、Reviewer 和 Synthesizer 的职责、输入、输出和工具白名单。
- **状态与交接**：传递任务 ID、结构化证据、来源、待办、错误和状态，不复制整段上下文。
- **串行和并行**：有数据依赖时串行；独立调查时并行；并行必须处理超时、部分失败和结果完整性。
- **竞争假设**：不同 Specialist 提出根因候选，Reviewer 根据来源、时间和适用范围比较证据。
- **监督者模式**：Supervisor 可以选择下一个 Agent，但必须受最大步数、预算和工具白名单限制。
- **收敛与恢复**：记录访问次数、任务指纹和工具历史；定义完成、超时、冲突、空结果和全部失败状态。

建议状态至少包含：

```json
{
  "run_id": "run-001",
  "task_id": "task-001",
  "intent": "diagnose_bug",
  "evidence": [],
  "missing_information": [],
  "errors": [],
  "next_actions": [],
  "step_count": 2,
  "budget": {
    "max_steps": 12,
    "max_seconds": 60
  }
}
```

#### 推荐编排图

```text
Router → Knowledge Specialist ─┐
       → Bug Specialist ───────┼→ Reviewer → Synthesizer
       → Log Specialist ───────┘
```

#### 本周验收标准

- 至少实现 Router、两个 Specialist、Reviewer 和 Synthesizer。
- 并行结果能全部汇总，单个 Agent 超时不会导致无限等待。
- 每次交接都有结构化状态，能从 `run_id` 追踪完整流程。
- 测试覆盖重复派发、循环、工具失败、证据冲突、部分超时和人工拒绝。

#### B 站与文档

- B 站搜索：`LangGraph 多 Agent 工作流 状态机`。
- B 站搜索：`多 Agent 编排 Router Supervisor 并行`。
- B 站搜索：`LangGraph 状态 StateGraph 节点 边`。
- LangGraph 视频参考：<https://www.bilibili.com/video/BV1UbQ2B6EJj>、<https://www.bilibili.com/video/BV1knNj6hEpM>。
- LangGraph：<https://docs.langchain.com/oss/python/langgraph/overview>。

### 第 8 周：评测、可观测性、安全、部署与面试项目

#### 要学习什么

- **Golden Dataset**：每条样例保存输入、期望意图、期望来源、期望事实和禁止声称的事实。
- **测试类型**：正常输入、信息缺失、无答案、恶意 Prompt、超长输入、非法 JSON、工具超时、权限不足、越权和证据冲突。
- **评测指标**：结构化输出通过率、检索相关性、引用正确率、无答案识别率、工具选择正确率、路由正确率、交接完整性、收敛率、幻觉率、越权率、P95 延迟和 Token 成本。
- **可观测性**：记录 `run_id`、`agent_id`、`parent_agent_id`、`task_id`、`handoff_id`、Prompt 版本、模型、检索结果、工具调用、耗时、Token、重试和终止原因。
- **安全**：Prompt Injection、敏感信息泄露、越权检索、危险工具和恶意超长输入；权限必须在代码层校验。
- **部署**：使用 Docker 或固定启动脚本运行 FastAPI，健康检查和配置从环境变量读取。

能用确定性规则判断的内容，如 JSON 合法性、引用 ID、权限和工具参数，应使用代码判断；语义质量才考虑模型辅助评审，并抽样人工复核。

#### Golden Dataset 示例

```json
{
  "case_id": "bug-001",
  "input": "登录失败五次后账号仍未锁定",
  "expected_intent": "diagnose_bug",
  "expected_sources": ["test-spec-login-v3-chunk-007"],
  "expected_facts": ["连续失败五次后账号应进入短暂锁定"],
  "must_not_claim": ["已经确认是数据库故障"]
}
```

#### 本周验收标准

- 有可重复执行的 Golden Dataset 和评测命令。
- 有评测报告，列出成功率、失败样例、已知风险和下一轮改进项。
- 能从用户请求追到检索、工具、Agent 交接和最终回答。
- 有 Prompt Injection、越权、无答案和工具失败测试。
- 项目能按 README 启动并完成端到端演示。

#### B 站与文档

- B 站搜索：`LLM 评测 RAG 评测 幻觉 评测集`。
- B 站搜索：`LangSmith LLM 评测 Trace 可观测性`。
- B 站搜索：`大模型应用安全 Prompt Injection 越权`。
- B 站搜索：`FastAPI Docker 部署 Python`。
- pytest：<https://docs.pytest.org/>。
- OWASP LLM Top 10：<https://owasp.org/www-project-top-10-for-large-language-model-applications/>。

## 四、最终项目的分阶段验收

项目名称：**多 Agent AI 缺陷诊断与测试知识库助手**。

- **第 1～2 周**：完成 `POST /defects/analyze`，支持 Prompt 版本、超时、重试、结构化响应和基础日志。
- **第 3 周**：所有模型输出经过 Pydantic 校验；非法 JSON、枚举错误、字段缺失和模型超时都有测试。
- **第 4 周**：完成文档清洗、Chunk、Embedding、入库、Top-K、Metadata Filter 和引用回答。
- **第 5 周**：抽出模型、Embedding、Prompt、解析、重试、日志和工具执行模块。
- **第 6 周**：接入 `search_knowledge`、`query_bug`、`get_service_logs`，完成权限、超时、幂等和审计测试。
- **第 7 周**：接入 Router、Specialist、Reviewer 和 Synthesizer，支持并行调查、冲突识别、超时降级和人工审批。
- **第 8 周**：完成 Golden Dataset、回归命令、运行追踪、安全测试、部署和演示文档。

## 五、八周计划速览

### 第 1 周：Python 最小基础

掌握函数、类、字典、列表、异常、文件、JSON、类型标注、虚拟环境、`async/await`、HTTP 请求和 pytest。

产出：一个 Python 命令行工具和一个能够接收 JSON 的 FastAPI 接口。

### 第 2 周：LLM API 与 Prompt

掌握 System/User 消息、上下文、多轮对话、流式输出、Temperature、Token、超时、重试、模型降级和 Prompt Injection 基础。

产出：缺陷描述分析 API，将自然语言转换为缺陷标题、严重程度、模块、复现步骤和缺失信息。
AI 学习计划 · 国内可访问资源汇总

学习资源
一、第1天：基础概念
学习内容：LLM、Token、Prompt、API 基本概念
推荐资源：
- B站搜索：吴恩达 面向所有人的生成式AI
- 对应原课：Generative AI for Everyone 中文版
用途：零基础了解生成式 AI 能做什么，不要求编程。

二、第2～3天：Prompt Engineering
学习内容：提示词、文本总结、分类、翻译、构建聊天机器人
推荐资源：
- B站：https://www.bilibili.com/video/BV1Bo4y1A7FU
- Datawhale LLM Cookbook 在线阅读：https://datawhalechina.github.io/llm-cookbook/
- PDF 下载：https://github.com/datawhalechina/llm-cookbook/releases/tag/v1.0.0
备注：B站视频若失效，搜索“ChatGPT Prompt Engineering for Developers 中文版”。

三、第3天（可选）：Building Systems with the ChatGPT API
学习内容：多轮调用、复杂任务拆分、自动化流程、API 应用开发
推荐资源：
- B站：https://www.bilibili.com/video/BV1R7pMzpESQ/
- 搜索关键词：使用ChatGPT API构建系统 吴恩达
备注：链接失效时按关键词搜索。

四、第4天：调用 LLM API
学习内容：创建 API Key、安装 SDK、发送第一次请求
推荐资源：
- B站搜索：API基础与大模型调用
- B站搜索：AI大模型应用开发全套教程 2026
- 国内可替代 API：DeepSeek、通义千问等
提醒：搜索时用“LLM API”，不要用“LLK API”。

五、第5～7天：小项目实战
学习内容：文本总结器、智能问答机器人
推荐资源：
- Datawhale LLM Cookbook：https://datawhalechina.github.io/llm-cookbook/
- B站搜索：LLM Cookbook 第一期
- 备选：上海交大《动手学大模型》，搜索关键词“动手学大模型 GitHub”
备注：优先做小项目，不用一开始研究模型训练和复杂数学。

六、进阶：深入原理
学习内容：Transformer、预训练、微调、评估、部署
推荐资源：
- B站搜索：吴恩达 Transformer LLM 的工作原理
- Datawhale Happy-LLM，搜索关键词：Datawhale Happy-LLM
备注：需要一些 Python 和机器学习基础，建议第一周后再看。

七、最推荐收藏
- Datawhale LLM Cookbook：https://datawhalechina.github.io/llm-cookbook/
- 这个在线阅读地址把吴恩达系列课程做了中文翻译和代码复现，国内可直接访问，适合贯穿整个第一周。

八、使用提醒
- B站视频可能被 UP 主删除或更换，链接打不开时直接用关键词搜索。
- 国内学习优先用 B站 + Datawhale + 国内大模型 API。
- 第一周重点：会调用模型、会写 Prompt、能做小项目。

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

## 六、最终练手项目

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

## 七、面试必须能讲清楚的问题

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

## 八、个人优势表达

测试工程师的优势不是“只会测试”，而是能够把质量能力迁移到 AI 系统：

> 我能够使用 Python 和 AI 编程工具完成 AI 全栈功能，并且会对结构化输出、检索结果、工具调用、权限边界、异常恢复和模型回归进行验证。相比只会调用模型 API，我更关注系统在错误输入和真实生产场景下是否可靠。

## 九、学习原则

- 只选一个模型 API、一个向量数据库和一个 Agent 框架。
- 先掌握 API、结构化输出、RAG 和可观测性，再把重点放到多 Agent 编排。
- 多 Agent 的核心不是 Agent 数量，而是职责边界、状态契约和可验证的收敛条件。
- 每个 Agent 都要有明确输入、输出、工具白名单、失败状态和终止条件。
- 优先实现 3 个角色协作的稳定系统，再扩展 Agent 数量。
- 每周必须有可运行产出。
- 所有 AI 结论都要能关联证据或明确标注不确定。
- 不把框架调用当作能力，必须理解 HTTP、检索、状态机和工具循环。
