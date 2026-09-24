# paas-ai

**方言**: `mongodb` 
**说明**: AI智能平台，管理AI助手(Agent)、会话、技能、Prompt模板、RAG知识库、模型配置、用量统计及安全设置 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns paas-ai <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query paas-ai`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables paas-ai --dialect mongodb -j
fx-ops idp --profile <profile> show columns paas-ai <table> --dialect mongodb -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query paas-ai --collection <collection> --filter '<JSON>' -j
```

## 统计

- 表级筛选条目: **51**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **51**
- 使用 `$tenant_account` / EA: **0**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `Agent` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `AgentVersionEntity` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `AgentCompactionStatePo` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `AgentDebugLogDetail` | tenantId | `createTime` | `{"tenantId":"$tenant_id"}` |
| `AgentProcessLog` | tenantId | `createTime` | `{"tenantId":"$tenant_id"}` |
| `AgentProcessLogDetail` | tenantId | `createTime` | `{"tenantId":"$tenant_id"}` |
| `AgentPersonalKnowledgeSource` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `AgentUserConfigPo` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `ConversationPo` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `ConversationMessagePo` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `ConversationOutput` | tenantId | `createTime` | `{"tenantId":"$tenant_id"}` |
| `ConversationFile` | tenantId | `createTime` | `{"tenantId":"$tenant_id"}` |
| `MessagePo` | tenantId | `createTime` | `{"tenantId":"$tenant_id"}` |
| `SessionPo` | tenantId | `createTime` | `{"tenantId":"$tenant_id"}` |
| `Skill` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `SkillVersion` | tenantId | `createTime` | `{"tenantId":"$tenant_id"}` |
| `Prompt` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `PromptTemplateVersionEntity` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `Action` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `ActionV2` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `ActionDefinition` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `ActionDefinitionEntity` | tenantId | `-` | `{"tenantId":"$tenant_id"}` |
| `ActionCategory` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `Button` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `ButtonVersionEntity` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `RagPo` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `RagVersionPo` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `RagObjectSpecialChunkConfigPo` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `RagVersionDeleteTaskPo` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `RagFileJob` | tenantId | `createTime` | `{"tenantId":"$tenant_id"}` |
| `ModelManage` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `ModelGenerator` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `AIResource` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `UsageDetail` | tenantId | `createTime` | `{"tenantId":"$tenant_id"}` |
| `FeedBack` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `Monitor` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `SecuritySetting` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `EmployeeSkillRelation` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `DescribeField` | tenantId | `createTime` | `{"tenantId":"$tenant_id"}` |
| `Insight` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `PlatKnowledge` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `PlatLocalDoc` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `AIMemoryDelayPo` | tenantId | `createTime` | `{"tenantId":"$tenant_id"}` |
| `FileChatSearchPo` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `ReportConfig` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `APLCodeReport` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `EmbeddingSourceData` | tenantId | `-` | `{"tenantId":"$tenant_id"}` |
| `EmbeddingSourceDataV3` | tenantId | `-` | `{"tenantId":"$tenant_id"}` |
| `fx_repository_v1_bi` | tenant_id | `-` | `{"tenant_id":"$tenant_id"}` |
| `fs_knowledge_collection` | tenant_id | `-` | `{"tenant_id":"$tenant_id"}` |
| `eservice_service_fault` | tenant_id | `-` | `{"tenant_id":"$tenant_id"}` |

## 表字段说明

以下为已整理的表/字段含义（与筛选规则配合使用）。运行时仍以 `table get -j` 为准。

### `Agent`

**说明**: AI 助手主表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenantId` | `number` | 租户ID |
| `name` | `string` | 助手名称 |
| `apiName` | `string` | API Name标识 |
| `description` | `string` | 助手描述 |
| `llmProvider` | `string` | LLM服务商 |
| `model` | `string` | 模型名称 |
| `createBy` | `number` | 创建人ID |
| `lastUpdateBy` | `number` | 最后修改人ID |
| `skills` | `array` | 技能列表 |
| `status` | `number` | 状态码 |
| `createTime` | `number` | 创建时间戳 |
| `updateTime` | `number` | 更新时间戳 |
| `visible` | `boolean` | 是否可见 |
| `role` | `string` | 角色设定 |
| `editable` | `boolean` | 是否可编辑 |
| `welcomeMessage` | `string` | 欢迎语 |
| `useType` | `string` | 使用类型 |
| `copyable` | `boolean` | 是否可复制 |
| `recallSetting` | `object` | 召回设置 |
| `mode` | `string` | 运行模式 |
| `type` | `string` | 助手类型 |
| `topics` | `array` | 主题列表 |
| `version` | `number` | 版本号 |
| `isCurrent` | `boolean` | 是否当前版本 |

### `AgentVersionEntity`

**说明**: AI 助手版本实体表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `apiName` | `string` | API Name |
| `tenantId` | `number` | 租户ID |
| `version` | `number` | 版本号 |
| `topics` | `array` | 主题列表 |
| `isCurrent` | `boolean` | 是否当前版本 |
| `createBy` | `number` | 创建人ID |
| `lastUpdateBy` | `number` | 修改人ID |
| `status` | `number` | 状态码 |
| `createTime` | `number` | 创建时间戳 |
| `updateTime` | `number` | 更新时间戳 |
| `visible` | `boolean` | 是否可见 |
| `editable` | `boolean` | 是否可编辑 |
| `copyable` | `boolean` | 是否可复制 |
| `skills` | `array` | 技能列表 |
| `modelApiName` | `string` | 模型API Name |
| `buttons` | `array` | 按钮列表 |
| `role` | `string` | 角色设定 |
| `llmProvider` | `string` | LLM服务商 |
| `welcomeMessage` | `string` | 欢迎语 |
| `model` | `string` | 模型名称 |

### `AgentCompactionStatePo`

**说明**: 助手会话压缩状态表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `agentApiName` | `string` | 助手API Name |
| `sessionId` | `string` | 会话ID |
| `tenantId` | `number` | 租户ID |
| `userId` | `string` | 用户ID |
| `compactedHistoryTokenEstimate` | `number` | 压缩后token估算 |
| `coveredMessageCount` | `number` | 覆盖消息数 |
| `coveredUntilMessageId` | `string` | 覆盖截止消息ID |
| `createTime` | `number` | 创建时间戳 |
| `delete` | `boolean` | 是否删除 |
| `keepFirstUserMessage` | `boolean` | 保留首条用户消息 |
| `messagesToKeep` | `number` | 保留消息数 |
| `rawHistoryTokenEstimate` | `number` | 原始token估算 |
| `sourceHistoryHash` | `string` | 原始历史哈希 |
| `summaryText` | `string` | 摘要文本 |
| `summaryVersion` | `string` | 摘要版本 |
| `updateTime` | `number` | 更新时间戳 |

### `AgentDebugLogDetail`

**说明**: 助手调试日志详情表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `logId` | `string` | 日志ID |
| `agentApiName` | `string` | 助手API Name |
| `version` | `number` | 版本号 |
| `sessionId` | `string` | 会话ID |
| `createTime` | `number` | 创建时间戳 |
| `cost` | `object` | 消耗信息 |
| `type` | `string` | 日志类型 |
| `content` | `string` | 日志内容JSON |
| `errorMessage` | `string` | 错误信息 |
| `expireTime` | `number` | 过期时间戳 |
| `topicApiName` | `object` | 主题API Name |
| `topicName` | `object` | 主题名称 |
| `topicDescription` | `object` | 主题描述 |
| `topicInstructions` | `object` | 主题指令 |
| `lastActionApiName` | `object` | 上次动作API Name |
| `tenantId` | `number` | 租户ID |

### `AgentProcessLog`

**说明**: 助手处理日志表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `agentApiName` | `string` | 助手API Name |
| `sessionId` | `string` | 会话ID |
| `createTime` | `number` | 创建时间戳 |
| `tokens` | `number` | token数 |
| `duration` | `number` | 耗时毫秒 |
| `errorMessage` | `string` | 错误信息 |
| `expireTime` | `number` | 过期时间戳 |
| `tenantId` | `number` | 租户ID |

### `AgentProcessLogDetail`

**说明**: 助手处理日志详情表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenantId` | `number` | 租户ID |
| `agentApiName` | `string` | 助手API Name |
| `sessionId` | `string` | 会话ID |
| `createTime` | `number` | 创建时间戳 |
| `tokens` | `number` | token数 |
| `duration` | `number` | 耗时毫秒 |
| `errorMessage` | `string` | 错误信息 |
| `expireTime` | `number` | 过期时间戳 |
| `version` | `number` | 版本号 |

### `AgentPersonalKnowledgeSource`

**说明**: 助手个人知识来源表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `employeeId` | `number` | 员工ID |
| `agentApiName` | `string` | 助手API Name |
| `knowledgeIdList` | `object` | 知识库ID列表 |
| `fileIndexApiName` | `string` | 文件索引API Name |
| `fileIndexExpireTime` | `number` | 索引过期时间 |
| `files` | `array` | 文件列表 |
| `name` | `string` | 名称 |
| `apiName` | `string` | API Name |
| `description` | `object` | 描述 |
| `createBy` | `number` | 创建人ID |
| `lastUpdateBy` | `number` | 修改人ID |
| `status` | `number` | 状态码 |
| `delete` | `object` | 删除标记 |
| `createTime` | `number` | 创建时间戳 |
| `updateTime` | `number` | 更新时间戳 |
| `visible` | `boolean` | 是否可见 |
| `editable` | `boolean` | 是否可编辑 |
| `copyable` | `boolean` | 是否可复制 |
| `tenantId` | `number` | 租户ID |

### `AgentUserConfigPo`

**说明**: 助手用户配置表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `agentApiName` | `string` | 助手API Name |
| `configType` | `string` | 配置类型 |
| `employeeId` | `number` | 员工ID |
| `tenantId` | `number` | 租户ID |
| `configContent` | `string` | 配置内容 |
| `createTime` | `number` | 创建时间戳 |
| `updateTime` | `number` | 更新时间戳 |

### `ConversationPo`

**说明**: 对话主表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `unionKey` | `string` | 联合键 |
| `userId` | `number` | 用户ID |
| `sessionId` | `string` | 会话ID |
| `conversationId` | `string` | 对话ID |
| `conversationName` | `string` | 对话名称 |
| `agentApiName` | `string` | 助手API Name |
| `pinnedTime` | `number` | 置顶时间 |
| `expireAt` | `object` | 过期时间 |
| `createTime` | `number` | 创建时间戳 |
| `updateTime` | `number` | 更新时间戳 |
| `createBy` | `number` | 创建人ID |
| `lastUpdateBy` | `number` | 修改人ID |
| `delete` | `boolean` | 是否删除 |
| `tenantId` | `number` | 租户ID |

### `ConversationMessagePo`

**说明**: 对话消息表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `messageId` | `string` | 消息ID |
| `sessionId` | `string` | 会话ID |
| `instanceId` | `string` | 实例ID |
| `conversationId` | `string` | 对话ID |
| `agentApiName` | `string` | 助手API Name |
| `userId` | `number` | 用户ID |
| `role` | `string` | 角色 |
| `contentJson` | `string` | 内容JSON |
| `artifactsJson` | `object` | 制品JSON |
| `processJson` | `object` | 处理过程JSON |
| `suggestJson` | `object` | 建议JSON |
| `thinkingJson` | `object` | 思考过程JSON |
| `tipsJson` | `object` | 提示JSON |
| `feedbackType` | `object` | 反馈类型 |
| `expireAt` | `object` | 过期时间 |
| `createTime` | `number` | 创建时间戳 |
| `updateTime` | `number` | 更新时间戳 |
| `createBy` | `number` | 创建人ID |
| `lastUpdateBy` | `number` | 修改人ID |
| `delete` | `boolean` | 是否删除 |
| `tenantId` | `number` | 租户ID |

### `ConversationOutput`

**说明**: 对话输出表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `conversationId` | `string` | 对话ID |
| `sessionId` | `string` | 会话ID |
| `messageId` | `string` | 消息ID |
| `userId` | `number` | 用户ID |
| `agentApiName` | `string` | 助手API Name |
| `type` | `string` | 输出类型 |
| `componentType` | `object` | 组件类型 |
| `data` | `string` | 数据JSON |
| `createTime` | `number` | 创建时间戳 |
| `updateTime` | `number` | 更新时间戳 |
| `createdBy` | `object` | 创建者 |
| `updatedBy` | `object` | 更新者 |
| `valid` | `boolean` | 是否有效 |
| `tenantId` | `number` | 租户ID |

### `ConversationFile`

**说明**: 对话文件表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `conversationId` | `string` | 对话ID |
| `messageId` | `string` | 消息ID |
| `userId` | `number` | 用户ID |
| `agentApiName` | `string` | 助手API Name |
| `fileJson` | `string` | 文件信息JSON |
| `createTime` | `number` | 创建时间戳 |
| `tenantId` | `number` | 租户ID |

### `MessagePo`

**说明**: 消息表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `conversationId` | `string` | 对话ID |
| `userId` | `number` | 用户ID |
| `instruction` | `string` | 用户指令 |
| `assistantMessage` | `string` | 助手回复 |
| `attachment` | `object` | 附件 |
| `createTime` | `number` | 创建时间戳 |
| `paddingSkill` | `object` | 补全技能 |
| `confirmMessage` | `object` | 确认消息 |
| `jsonData` | `object` | JSON数据 |
| `tenantId` | `number` | 租户ID |

### `SessionPo`

**说明**: 会话表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `sessionId` | `string` | 会话ID |
| `tenantId` | `number` | 租户ID |
| `userId` | `number` | 用户ID |
| `conversationId` | `string` | 对话ID |
| `createTime` | `number` | 创建时间戳 |

### `Skill`

**说明**: 技能表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenantId` | `number` | 租户ID |
| `name` | `string` | 技能名称 |
| `apiName` | `string` | API Name |
| `description` | `string` | 技能描述 |
| `actions` | `array` | 动作列表 |
| `createBy` | `number` | 创建人ID |
| `lastUpdateBy` | `number` | 修改人ID |
| `status` | `number` | 状态码 |
| `createTime` | `number` | 创建时间戳 |
| `updateTime` | `number` | 更新时间戳 |
| `visible` | `boolean` | 是否可见 |
| `editable` | `boolean` | 是否可编辑 |
| `useType` | `string` | 使用类型 |
| `copyable` | `boolean` | 是否可复制 |
| `scopeOwnerId` | `number` | 范围拥有者ID |

### `SkillVersion`

**说明**: 技能版本表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `apiName` | `string` | API Name |
| `useType` | `string` | 使用类型 |
| `scopeOwnerId` | `number` | 范围拥有者ID |
| `versionNo` | `number` | 版本号 |
| `name` | `string` | 技能名称 |
| `description` | `string` | 技能描述 |
| `instructions` | `array` | 指令列表 |
| `actions` | `array` | 动作列表 |
| `examples` | `array` | 示例列表 |
| `alwaysExeWhenAlone` | `boolean` | 单独时总执行 |
| `objectApiNames` | `array` | 对象API Name列表 |
| `allowEmployeeAdd` | `boolean` | 允许员工添加 |
| `tenantOverridePersonal` | `boolean` | 租户覆盖个人 |
| `sourceType` | `string` | 来源类型 |
| `sourceFileType` | `string` | 源文件类型 |
| `sourceFile` | `object` | 源文件 |
| `sourceFileTree` | `object` | 文件树 |
| `createBy` | `number` | 创建人ID |
| `createTime` | `number` | 创建时间戳 |
| `tenantId` | `number` | 租户ID |

### `Prompt`

**说明**: 提示词模板表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `apiName` | `string` | API Name |
| `tenantId` | `number` | 租户ID |
| `createBy` | `number` | 创建人ID |
| `createTime` | `number` | 创建时间戳 |
| `status` | `number` | 状态码 |
| `role` | `string` | 角色设定 |
| `description` | `string` | 描述 |
| `bindingObjectApiName` | `string` | 绑定对象API Name |
| `updateTime` | `number` | 更新时间戳 |
| `language` | `string` | 语言 |
| `type` | `string` | 类型 |
| `content` | `string` | 模板内容 |
| `name` | `string` | 名称 |
| `style` | `string` | 风格 |
| `model` | `string` | 模型 |
| `llmProvider` | `string` | LLM服务商 |
| `contentLength` | `number` | 内容长度 |
| `lastUpdateBy` | `number` | 修改人ID |
| `supportAdvanced` | `boolean` | 支持高级 |
| `copyable` | `boolean` | 是否可复制 |
| `visible` | `boolean` | 是否可见 |
| `editable` | `boolean` | 是否可编辑 |
| `searchEnabled` | `boolean` | 搜索启用 |
| `expansionPrompt` | `boolean` | 扩展提示 |

### `PromptTemplateVersionEntity`

**说明**: 提示词模板版本实体表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `apiName` | `string` | API Name |
| `tenantId` | `object` | 租户ID |
| `version` | `number` | 版本号 |
| `content` | `string` | 模板内容 |
| `contentLength` | `number` | 内容长度 |
| `copyable` | `boolean` | 是否可复制 |
| `createBy` | `number` | 创建人ID |
| `createTime` | `number` | 创建时间戳 |
| `editable` | `boolean` | 是否可编辑 |
| `editorContent` | `string` | 编辑器内容 |
| `isCurrent` | `boolean` | 是否当前版本 |
| `language` | `string` | 语言 |
| `llmProvider` | `string` | LLM服务商 |
| `model` | `string` | 模型 |
| `modelApiName` | `string` | 模型API Name |
| `outputSetting` | `object` | 输出设置 |
| `ragVariables` | `array` | RAG变量 |
| `role` | `object` | 角色 |
| `sceneVariable` | `array` | 场景变量 |
| `searchEnabled` | `boolean` | 搜索启用 |
| `status` | `number` | 状态码 |
| `style` | `string` | 风格 |
| `supportAdvanced` | `boolean` | 支持高级 |
| `updateTime` | `number` | 更新时间戳 |
| `visible` | `boolean` | 是否可见 |
| `webSearchVariables` | `array` | 网页搜索变量 |

### `Action`

**说明**: 动作表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `definitionApiName` | `string` | 定义API Name |
| `type` | `object` | 类型 |
| `bizApiName` | `object` | 业务API Name |
| `dataCount` | `object` | 数据数量 |
| `properties` | `array` | 属性列表 |
| `needConfirm` | `boolean` | 需确认 |
| `output` | `object` | 输出定义 |
| `version` | `string` | 版本号 |
| `name` | `string` | 动作名称 |
| `apiName` | `string` | API Name |
| `description` | `string` | 描述 |
| `createBy` | `number` | 创建人ID |
| `lastUpdateBy` | `number` | 修改人ID |
| `status` | `number` | 状态码 |
| `delete` | `object` | 删除标记 |
| `createTime` | `number` | 创建时间戳 |
| `updateTime` | `number` | 更新时间戳 |
| `visible` | `boolean` | 是否可见 |
| `editable` | `boolean` | 是否可编辑 |
| `copyable` | `boolean` | 是否可复制 |
| `tenantId` | `number` | 租户ID |

### `ActionV2`

**说明**: 动作V2表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `definitionApiName` | `string` | 定义API Name |
| `needConfirm` | `boolean` | 需确认 |
| `input` | `object` | 输入定义 |
| `output` | `object` | 输出定义 |
| `name` | `string` | 动作名称 |
| `apiName` | `string` | API Name |
| `description` | `string` | 描述 |
| `createBy` | `number` | 创建人ID |
| `lastUpdateBy` | `number` | 修改人ID |
| `status` | `number` | 状态码 |
| `delete` | `object` | 删除标记 |
| `createTime` | `number` | 创建时间戳 |
| `updateTime` | `number` | 更新时间戳 |
| `visible` | `boolean` | 是否可见 |
| `editable` | `boolean` | 是否可编辑 |
| `copyable` | `boolean` | 是否可复制 |
| `tenantId` | `number` | 租户ID |

### `ActionDefinition`

**说明**: 动作定义表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenantId` | `number` | 租户ID |
| `apiName` | `string` | API Name |
| `name` | `string` | 名称 |
| `icon` | `object` | 图标 |
| `description` | `string` | 描述 |
| `type` | `string` | 类型 |
| `nameTranslations` | `object` | 名称翻译 |
| `bizType` | `string` | 业务类型 |
| `status` | `number` | 状态码 |
| `configuration` | `string` | 配置JSON |
| `configurationLang` | `string` | 配置语言 |
| `configurationType` | `string` | 配置类型 |
| `apiKey` | `object` | API密钥 |
| `auth` | `object` | 认证配置 |
| `tools` | `array` | 工具列表 |
| `createBy` | `number` | 创建人ID |
| `lastUpdateBy` | `number` | 修改人ID |
| `createTime` | `number` | 创建时间戳 |
| `updateTime` | `number` | 更新时间戳 |
| `source` | `string` | 来源 |

### `ActionDefinitionEntity`

**说明**: 动作定义实体表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenantId` | `number` | 租户ID |
| `apiName` | `string` | API Name |
| `name` | `string` | 名称 |
| `icon` | `object` | 图标 |
| `description` | `string` | 描述 |
| `type` | `string` | 类型 |
| `nameTranslations` | `object` | 名称翻译 |
| `bizType` | `object` | 业务类型 |
| `status` | `object` | 状态 |
| `configuration` | `string` | 配置JSON |
| `configurationLang` | `string` | 配置语言 |
| `configurationType` | `string` | 配置类型 |
| `apiKey` | `object` | API密钥 |
| `auth` | `object` | 认证配置 |
| `tools` | `array` | 工具列表 |
| `createBy` | `number` | 创建人ID |
| `lastUpdateBy` | `number` | 修改人ID |
| `createTime` | `object` | 创建时间 |
| `updateTime` | `object` | 更新时间 |

### `ActionCategory`

**说明**: 动作分类表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `string` | 分类ID |
| `tenantId` | `number` | 租户ID |
| `parentId` | `string` | 父分类ID |
| `name` | `string` | 名称 |
| `description` | `string` | 描述 |
| `cliCode` | `string` | CLI代码 |
| `delete` | `boolean` | 是否删除 |
| `version` | `number` | 版本号 |
| `createBy` | `number` | 创建人ID |
| `lastUpdateBy` | `number` | 修改人ID |
| `createTime` | `number` | 创建时间戳 |
| `updateTime` | `number` | 更新时间戳 |

### `Button`

**说明**: 按钮表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenantId` | `number` | 租户ID |
| `name` | `string` | 按钮名称 |
| `apiName` | `string` | API Name |
| `description` | `string` | 描述 |
| `createBy` | `number` | 创建人ID |
| `lastUpdateBy` | `number` | 修改人ID |
| `status` | `number` | 状态码 |
| `createTime` | `number` | 创建时间戳 |
| `updateTime` | `number` | 更新时间戳 |
| `visible` | `boolean` | 是否可见 |
| `editable` | `boolean` | 是否可编辑 |
| `version` | `number` | 版本号 |
| `copyable` | `boolean` | 是否可复制 |
| `isCurrent` | `boolean` | 是否当前版本 |

### `ButtonVersionEntity`

**说明**: 按钮版本实体表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `status` | `number` | 状态码 |
| `updateTime` | `number` | 更新时间戳 |
| `lastUpdateBy` | `number` | 修改人ID |

### `RagPo`

**说明**: RAG 配置表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `apiName` | `string` | API Name |
| `tenantId` | `number` | 租户ID |
| `rewriterPrompt` | `string` | 改写提示词 |
| `generatorPrompt` | `string` | 生成提示词 |
| `embeddingPrompt` | `string` | 嵌入提示词 |
| `bindingApiName` | `string` | 绑定对象API Name |
| `currentVersion` | `number` | 当前版本 |
| `updateTime` | `number` | 更新时间戳 |
| `createTime` | `number` | 创建时间戳 |
| `currentVersionId` | `number` | 当前版本ID |
| `maxArticleCount` | `number` | 最大文章数 |
| `minArticleCount` | `number` | 最小文章数 |
| `maxInputToken` | `number` | 最大输入token |
| `modelConfig` | `string` | 模型配置 |
| `useHNSWIndex` | `boolean` | 使用HNSW索引 |
| `status` | `number` | 状态码 |
| `deleted` | `number` | 是否删除 |
| `name` | `string` | 名称 |
| `dataSourceType` | `string` | 数据源类型 |
| `enableStatus` | `number` | 启用状态 |
| `updater` | `number` | 更新人 |
| `creator` | `number` | 创建人 |
| `describe` | `string` | 描述 |

### `RagVersionPo`

**说明**: RAG 版本表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `apiName` | `string` | API Name |
| `tenantId` | `number` | 租户ID |
| `className` | `string` | 类名 |
| `versionId` | `number` | 版本ID |
| `embeddingModel` | `string` | 嵌入模型 |
| `rerankModel` | `string` | 重排序模型 |
| `mapping` | `object` | 字段映射 |
| `updateTime` | `number` | 更新时间戳 |
| `createTime` | `number` | 创建时间戳 |
| `indexName` | `string` | 索引名称 |
| `status` | `number` | 状态码 |
| `deleted` | `number` | 是否删除 |
| `documentCount` | `number` | 文档数 |

### `RagObjectSpecialChunkConfigPo`

**说明**: RAG 对象特殊分块配置表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `objectDataId` | `string` | 对象数据ID |
| `fieldApiName` | `string` | 字段API Name |
| `filePath` | `string` | 文件路径 |
| `fieldConfig` | `string` | 字段配置 |
| `tenantId` | `number` | 租户ID |
| `apiName` | `string` | RAG API Name |
| `createTime` | `number` | 创建时间戳 |
| `updateTime` | `number` | 更新时间戳 |
| `updater` | `number` | 更新人 |
| `creator` | `number` | 创建人 |

### `RagVersionDeleteTaskPo`

**说明**: RAG 版本删除任务表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `apiName` | `string` | API Name |
| `tenantId` | `number` | 租户ID |
| `versionId` | `number` | 版本ID |
| `status` | `number` | 状态码 |
| `retryCount` | `number` | 重试次数 |
| `updateTime` | `number` | 更新时间戳 |
| `createTime` | `number` | 创建时间戳 |
| `failReason` | `object` | 失败原因 |

### `RagFileJob`

**说明**: RAG 文件处理任务表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `jobId` | `string` | 任务ID |
| `jobStatus` | `string` | 任务状态 |
| `tenantId` | `string` | 租户ID |
| `ragApiName` | `string` | RAG API Name |
| `filePath` | `string` | 文件路径 |
| `fileName` | `string` | 文件名 |
| `fileExt` | `string` | 文件扩展名 |
| `source` | `string` | 来源ID |
| `versionId` | `number` | 版本ID |
| `articleTime` | `object` | 文章时间 |
| `createTime` | `number` | 创建时间戳 |
| `convertFileType` | `object` | 转换文件类型 |

### `ModelManage`

**说明**: 模型管理表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `modelType` | `string` | 模型类型 |
| `bindingFuncApiName` | `object` | 绑定函数API Name |
| `functionCall` | `boolean` | 函数调用 |
| `multiModal` | `boolean` | 多模态 |
| `icon` | `string` | 图标URL |
| `quoteNum` | `object` | 引用数 |
| `modelMaker` | `string` | 模型厂商 |
| `modelKeyMap` | `object` | 模型密钥映射 |
| `models` | `array` | 模型列表 |
| `name` | `string` | 名称 |
| `apiName` | `string` | API Name |
| `description` | `string` | 描述 |
| `createBy` | `number` | 创建人ID |
| `lastUpdateBy` | `number` | 修改人ID |
| `status` | `number` | 状态码 |
| `delete` | `object` | 删除标记 |
| `createTime` | `number` | 创建时间戳 |
| `updateTime` | `number` | 更新时间戳 |
| `tenantId` | `number` | 租户ID |
| `visible` | `boolean` | 是否可见 |
| `editable` | `boolean` | 是否可编辑 |
| `copyable` | `boolean` | 是否可复制 |

### `ModelGenerator`

**说明**: 模型生成器表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `bindObjectApiName` | `string` | 绑定对象API Name |
| `deployStatus` | `string` | 部署状态 |
| `markFieldApiName` | `string` | 标记字段API Name |
| `positiveMarkValue` | `string` | 正向标记值 |
| `negativeMarkValue` | `string` | 负向标记值 |
| `trainTime` | `number` | 训练时间 |
| `createTimeFilterValue` | `string` | 创建时间过滤值 |
| `filters` | `string` | 过滤条件 |
| `tenantId` | `number` | 租户ID |
| `name` | `string` | 名称 |
| `apiName` | `string` | API Name |
| `description` | `object` | 描述 |
| `createBy` | `number` | 创建人ID |
| `lastUpdateBy` | `number` | 修改人ID |
| `status` | `number` | 状态码 |
| `createTime` | `number` | 创建时间戳 |
| `updateTime` | `number` | 更新时间戳 |

### `AIResource`

**说明**: AI 资源配额表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `moduleCode` | `string` | 模块代码 |
| `paraKey` | `string` | 参数键 |
| `paraValue` | `number` | 参数值 |
| `startTime` | `number` | 开始时间 |
| `createTime` | `number` | 创建时间戳 |
| `expiredTime` | `number` | 过期时间 |
| `orderId` | `string` | 订单ID |
| `remain` | `number` | 剩余量 |
| `updateTime` | `number` | 更新时间戳 |
| `tenantId` | `number` | 租户ID |

### `UsageDetail`

**说明**: 使用量明细表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `userId` | `number` | 用户ID |
| `model` | `string` | 模型 |
| `prompt_token` | `number` | 提示token数 |
| `completion_tokens` | `number` | 完成token数 |
| `total_token` | `number` | 总token数 |
| `createTime` | `number` | 创建时间戳 |
| `business` | `string` | 业务类型 |
| `tenantId` | `number` | 租户ID |

### `FeedBack`

**说明**: 反馈表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `messageId` | `string` | 消息ID |
| `sessionId` | `string` | 会话ID |
| `tenantId` | `number` | 租户ID |
| `createTime` | `number` | 创建时间戳 |
| `createBy` | `string` | 创建人ID |
| `feedbackId` | `string` | 反馈ID |
| `feedbackType` | `number` | 反馈类型 |
| `updateTime` | `number` | 更新时间戳 |
| `lastUpdateBy` | `string` | 修改人ID |
| `feedbackDetails` | `array` | 反馈详情 |
| `sendFlag` | `boolean` | 发送标记 |

### `Monitor`

**说明**: AI 监控配置表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenantId` | `number` | 租户ID |
| `createBy` | `number` | 创建人ID |
| `createTime` | `number` | 创建时间戳 |
| `lastUpdateBy` | `number` | 修改人ID |
| `openToxicityDetection` | `boolean` | 开启毒性检测 |
| `status` | `number` | 状态码 |
| `updateTime` | `number` | 更新时间戳 |

### `SecuritySetting`

**说明**: AI 安全设置表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenantId` | `number` | 租户ID |
| `core` | `boolean` | 核心安全 |
| `createBy` | `number` | 创建人ID |
| `createTime` | `number` | 创建时间戳 |
| `general` | `boolean` | 通用安全 |
| `important` | `boolean` | 重要安全 |
| `lastUpdateBy` | `number` | 修改人ID |
| `updateTime` | `number` | 更新时间戳 |

### `EmployeeSkillRelation`

**说明**: 员工技能关联表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `employeeId` | `number` | 员工ID |
| `scopeOwnerId` | `number` | 范围拥有者ID |
| `skillApiName` | `string` | 技能API Name |
| `tenantId` | `number` | 租户ID |
| `useType` | `string` | 使用类型 |
| `addSource` | `string` | 添加来源 |
| `createBy` | `number` | 创建人ID |
| `createTime` | `number` | 创建时间戳 |
| `delete` | `boolean` | 是否删除 |
| `enabled` | `boolean` | 是否启用 |
| `lastUpdateBy` | `number` | 修改人ID |
| `updateTime` | `number` | 更新时间戳 |

### `DescribeField`

**说明**: 描述字段配置表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `apiName` | `string` | API Name |
| `describeApiName` | `string` | 描述API Name |
| `tenantId` | `number` | 租户ID |
| `createTime` | `number` | 创建时间戳 |
| `quotaField` | `string` | 配额字段 |
| `quotaFieldType` | `string` | 配额字段类型 |
| `targetApiName` | `string` | 目标API Name |
| `targetRelatedListName` | `string` | 目标关联列表名 |
| `targetRelatedListLabel` | `string` | 目标关联列表标签 |
| `options` | `string` | 选项 |
| `type` | `string` | 字段类型 |
| `active` | `boolean` | 是否激活 |
| `label` | `string` | 标签 |
| `describeDisplayName` | `string` | 描述显示名称 |

### `Insight`

**说明**: AI 洞察表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `userId` | `number` | 用户ID |
| `objectId` | `string` | 对象ID |
| `objectApiName` | `string` | 对象API Name |
| `apiName` | `string` | API Name |
| `aiContent` | `string` | AI生成内容 |
| `updateTime` | `number` | 更新时间戳 |
| `createTime` | `number` | 创建时间戳 |
| `tenantId` | `number` | 租户ID |

> 其余 11 张表请 `table list` / `table get -j`。
