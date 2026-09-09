# TAPD ↔ 企微智能表格双向增量同步

## 概述

支持 TAPD 数据与企微智能表格的**双向增量同步**和**单向导出**。

- **双向同步**：三向 Diff 检测变更，冲突可控，增量更新
- **单向导出**：从 TAPD 拉数据直接写入智能表格，无需复杂 Diff

`tapd-cli` 只负责 TAPD 侧读写。智能表格侧依赖当前环境中单独提供的客户端；执行前必须阅读该客户端的帮助或接口文档，并确认其支持本文所需能力。

## 快速开始（双向同步）

1. **确认参数**：workspace_id、entity_type（stories/tasks/bugs）、智能表格 URL 或创建新表
2. **写权限自检**：对目标表格做一次无害写入探测，失败则自动新建表
3. **拉数据 + Diff**：从 TAPD 和智能表格拉取数据，用脚本做三向 Diff
4. **确认策略**：展示 Diff 结果，等用户选择冲突策略后才能执行写入
5. **执行同步 + 存状态**：按 Diff 结果写入两侧，保存同步快照

## 同步参数

| 参数 | 必填 | 说明 | 默认/获取方式 |
| --- | --- | --- | --- |
| workspace_id | ✅ | TAPD 项目 ID | `tapd-cli user workspaces` 获取 |
| entity_type | ✅ | 工作项类型 | `stories`（可选 `tasks`/`bugs`） |
| docid | ✅ | 智能表格 docid | 用户提供 URL 或新建 |
| sheet_client | ✅ | 智能表格客户端 | 从当前环境确认并阅读帮助 |
| conflict_strategy |  | 冲突策略 | `tapd_wins` |
| sheet_id |  | 子表 ID | 自动获取，默认第一个 |
| config |  | 自定义字段映射配置文件路径 | 模板见 `${SKILL_DIR}/templates/sync-config.example.json` |
| extended |  | 是否全字段同步 | false（仅核心字段） |

> `SKILL_DIR` = `~/.workbuddy/skills/tapd-cli`

## 同步执行步骤

### 第 0 步：写权限自检 ⚠️ 必须

**在拉数据之前**，必须先确认智能表格客户端对目标表格有写权限。

1. 使用智能表格客户端添加 `TAPD_ID` 列；如已存在，则将一条记录更新为相同值，执行一次 no-op 写入探测
2. **返回 `errcode 851003`（无权限）** → 自动新建表兜底
3. **探测成功** → 继续第 1 步

### 第 1 步：加载同步状态

检查状态文件（默认 `~/.workbuddy/sync-states/tapd_sync_{workspace_id}.json`）：
- **存在** → 读取快照，执行增量同步
- **不存在** → 首次全量同步

```bash
python3 ${SKILL_DIR}/scripts/bidirectional_sync_engine.py \
  --action show-state \
  --state-file ~/.workbuddy/sync-states/tapd_sync_{WORKSPACE_ID}.json
```

### 第 2 步：获取 TAPD 侧数据

使用 `tapd-cli` 拉取数据：

```bash
tapd-cli story list workspaceid={WORKSPACE_ID} limit=200
```

> Bug 类型用 `tapd-cli bug list`，字段有差异（`title` 非 `name`，`current_owner` 非 `owner`）。
> 分页：返回数 = limit 时继续查下一页。

将返回结果写入 `/tmp/tapd_current_{WORKSPACE_ID}.json`。

### 第 2.5 步：获取迭代/分类名称映射 ⚠️ 必须

TAPD 的 `iteration_id`、`category_id`、`workitem_type_id` 返回的是 ID，**写入智能表格前必须转换为可读名称**。

通过 `tapd-cli story fields` 获取映射（此 API 在 options 字段中包含完整的 ID→名称映射）：

```bash
tapd-cli story fields workspaceid={WORKSPACE_ID}
```

从返回的 JSON 中提取：
- `data.iteration_id.options` → `{ "ID": "迭代名称", ... }`
- `data.category_id.options` → `{ "ID": "分类名称", ... }`
- `data.workitem_type_id.options` → `{ "ID": "需求类别名称", ... }`
- `data.status.options` → `{ "英文状态": "中文状态名", ... }`

> ⚠️ 注意：`iterations` 和 `story_categories` API 可能因 token scope 限制返回 403，但 `story fields` API 的 options 字段始终可用。
> 写入智能表格时，用映射后的名称替代原始 ID。

### 第 3 步：获取智能表格侧数据

使用智能表格客户端列出目标 `file_id` 和 `sheet_id` 下的记录。响应至少需要包含记录 ID、字段值和修改时间；字段名及分页参数以客户端帮助为准，禁止猜测。

将返回的 records 写入 `/tmp/sheet_current_{FILE_ID}.json`。

### 第 4 步：三向 Diff

```bash
python3 ${SKILL_DIR}/scripts/bidirectional_sync_engine.py \
  --action diff \
  --state-file ~/.workbuddy/sync-states/tapd_sync_{WORKSPACE_ID}.json \
  --tapd-data /tmp/tapd_current_{WORKSPACE_ID}.json \
  --sheet-data /tmp/sheet_current_{FILE_ID}.json \
  --entity-type stories \
  --conflict-strategy tapd_wins \
  --output /tmp/sync_diff_{WORKSPACE_ID}.json
```

全字段同步加 `--extended`，Dry-run 模式用 `--action dry-run`。

### 第 5 步：展示 Diff 并等待用户确认 ⚠️ 强制

**无论是否有冲突，都必须先展示 Diff 摘要再等用户确认策略，禁止直接执行写入。**

展示格式：
- 🔵 TAPD 新增 → 智能表格：N 条
- 🟢 智能表格新增 → TAPD：N 条
- 🟠 仅 TAPD 更新（待覆盖到表格）：N 条
- 🟡 仅智能表格更新（待覆盖到 TAPD）：N 条
- 🔴 双侧均更新（冲突）：N 条
- ⚪ 未变化：N 条

必须提供三个选项让用户选择：

| 选项 | 含义 |
| --- | --- |
| **A. 以 TAPD 为准** | TAPD 数据覆盖智能表格 |
| **B. 以智能表格为准** | 表格数据覆盖 TAPD |
| **C. 仅生成报告** | 不写任何一侧，输出冲突详情 |

> **用户未明确回答前，禁止调用任何写入接口**。

### 第 6 步：执行同步

#### 6.1 TAPD 新增 → 智能表格
#### 6.2 智能表格新增 → TAPD

使用 `tapd-cli story add` 创建需求，每创建一条，回写 TAPD_ID 到智能表格。

#### 6.3 仅 TAPD 侧更新 → 同步到智能表格
#### 6.4 仅智能表格侧更新 → 同步到 TAPD

使用 `tapd-cli story update` 更新需求。用 `v_status` 传中文状态名；422 错误标记为"待人工处理"。
#### 6.5 冲突记录（按用户选择的策略处理）

### 第 7 步：保存同步状态

```bash
python3 ${SKILL_DIR}/scripts/bidirectional_sync_engine.py \
  --action save-state \
  --state-file ~/.workbuddy/sync-states/tapd_sync_{WORKSPACE_ID}.json \
  --tapd-data /tmp/tapd_current_{WORKSPACE_ID}.json \
  --sheet-data /tmp/sheet_current_{FILE_ID}.json \
  --workspace-id {WORKSPACE_ID} \
  --entity-type stories \
  --docid {FILE_ID} \
  --sheet-id {SHEET_ID} \
  --conflict-strategy tapd_wins
```

### 第 8 步：输出同步报告

---

## 单向导出（TAPD → 智能表格）

如果只是一次性把 TAPD 数据导入智能表格，无需走双向同步流程。直接：

1. 用 `tapd-cli` 拉取 TAPD 数据
2. 创建/定位智能表格
3. 使用智能表格客户端写入数据

不需要状态文件和 Diff。

---

## 字段映射

### 核心字段（默认）

#### 需求（Story）

| 智能表格列名 | TAPD 字段 | 列类型 | Diff 比较 |
| --- | --- | --- | --- |
| TAPD_ID | id | TEXT (URL) | ❌ 关联键 |
| 标题 | name | TEXT (URL) | ✅ |
| 状态 | status | SINGLE_SELECT | ✅ 需枚举映射 |
| 优先级 | priority_label | SINGLE_SELECT | ✅ |
| 处理人 | owner | TEXT | ✅ |
| 预估工时 | effort | NUMBER | ✅ |
| 预计开始 | begin | DATE_TIME | ✅ |
| 预计结束 | due | DATE_TIME | ✅ |

#### 任务（Task）

| 智能表格列名 | TAPD 字段 | 列类型 |
| --- | --- | --- |
| TAPD_ID | id | TEXT (URL) |
| 标题 | name | TEXT |
| 状态 | status | SINGLE_SELECT |
| 处理人 | owner | TEXT |
| 预计开始 | begin | DATE_TIME |
| 预计结束 | due | DATE_TIME |

#### 缺陷（Bug）

| 智能表格列名 | TAPD 字段 | 列类型 |
| --- | --- | --- |
| TAPD_ID | id | TEXT (URL) |
| 标题 | title | TEXT |
| 状态 | status | SINGLE_SELECT |
| 优先级 | priority_label | SINGLE_SELECT |
| 严重程度 | severity | SINGLE_SELECT |
| 处理人 | current_owner | TEXT |

### 扩展字段（--extended 模式）

加 `--extended` 使用全字段映射，包含：创建人、开发人员、迭代、分类、需求类别、标签、模块、版本、业务价值、规模、工时相关、进度、日期相关、详细描述。

### 需要 ID→名称转换的字段

| TAPD 字段 | 映射来源 |
| --- | --- |
| status | `story fields` → `data.status.options` |
| iteration_id | `story fields` → `data.iteration_id.options` |
| category_id | `story fields` → `data.category_id.options` |
| workitem_type_id | `story fields` → `data.workitem_type_id.options` |

---

## 值格式转换规则

| 列类型 | TAPD 原始值 | 智能表格格式 |
| --- | --- | --- |
| TEXT (URL) | 字符串 + URL | `[{"type": "url", "text": "显示文字", "link": "https://..."}]` |
| TEXT | 字符串 | `[{"type": "text", "text": "内容"}]` |
| SINGLE_SELECT | 字符串 | `[{"text": "选项值"}]` |
| NUMBER | 数字 | 直接传数字 |
| DATE_TIME | YYYY-MM-DD | `"YYYY-MM-DD"` |

> **TAPD_ID 和标题列必须写为带超链接的 URL 格式**，链接指向 TAPD 详情页。
> 公有云：`https://www.tapd.cn/{ws_id}/prong/stories/view/{tapd_id}`
> 司内版：`https://tapd.woa.com/tapd_fe/{ws_id}/story/detail/{tapd_id}`

---

## 创建新智能表格

通过智能表格客户端创建新表。创建后必须**先添加 TAPD 字段列、再删除默认列、最后删除默认空行**：

1. 创建智能表格文件
2. 列出子表并获取 `sheet_id`
3. 列出字段并获取默认字段的 `field_id`
4. 添加 TAPD 字段列，只添加本次同步需要的列
5. 删除默认无用列，包括文本、日期、图片、数字和单选列
6. 列出记录并删除默认空行

> ⚠️ `dateTime` 字段类型会报 `errcode 22018`，日期列统一用 `text` 类型存储。
> ⚠️ 处理人建议用 `text` 而非 `user`，避免 userid 映射问题。
> ⚠️ 智能表格 API 字段类型使用小驼峰：`text`/`singleSelect`/`number`。

---

## 同步引擎脚本

核心脚本 `${SKILL_DIR}/scripts/bidirectional_sync_engine.py` 支持 6 种操作：

| 操作 | 说明 |
| --- | --- |
| `diff` | 三向 Diff 计算 |
| `dry-run` | 预览 Diff + 预估写入量，不实际写入 |
| `save-state` | 保存同步状态快照 |
| `show-state` | 查看当前同步状态摘要 |
| `reset-state` | 清空同步状态（下次将全量同步） |
| `validate` | 校验配置文件与数据一致性 |

---

## 同步注意事项

1. **首次同步是全量的**，之后为增量
2. **冲突策略必须先确认再执行**——用户未选择前禁止写入
3. **TAPD 是默认权威源**（仍需用户确认）
4. **智能表格删除的记录不会同步删除 TAPD 中的记录**（防误删），反之亦然
5. **状态映射因项目而异**——同步前务必获取目标项目的实际状态值
6. **大批量数据建议分批执行**——每次不超过 200 条
7. **TAPD_ID 和标题列必须带超链接**——每次写入都要带 link
8. **反向同步状态可能被工作流卡住**——422 错误时标记为"待人工处理"
9. **创建/更新 TAPD 不要用 unicode escape**——直接传中文字符串

## 排障指南

| 问题 | 排查方向 |
| --- | --- |
| 企微表格无编辑权限 (851003) | 自动新建表格兜底，或在现有表格添加应用协作者 |
| **企微智能表格数据读取需审批** | 见下方「企微数据访问权限」章节 |
| TAPD 创建失败 | 检查 owner 是否为项目成员；检查 priority_label 枚举值 |
| 状态值不匹配 | 调用 `story fields` 获取当前项目状态候选值 |
| Diff 结果异常（大量冲突） | 检查状态文件是否损坏；首次同步 snapshot 为空是正常的 |
| 同步状态文件丢失 | 退化为全量同步 |

---

## 企微数据访问权限（读取智能表格报错）

### 问题表现

读取企微智能表格记录时报错，提示**需要管理员审批数据访问权限**。

### 原因

读取企微智能表格数据涉及企业数据对外，**默认需要管理员审批**。

### 解决方案

#### 方案 A：等待管理员审批（默认）

联系企业微信管理员，在审批流程中通过数据访问权限申请。

#### 方案 B：配置白名单免审（推荐）

由**超级管理员**在管理后台配置白名单，白名单内的机器人获取数据访问权限免审：

**操作路径**：企业微信管理后台 → 管理工具 → 智能机器人 → **管理** → 数据访问权限

在页面中找到：
> **"以下成员创建的机器人，获取数据访问权限无需审批"**

点击「修改」，添加相关成员或部门。可以把整个企业根目录加为白名单，这样所有成员创建的机器人都免审。

配置完成后，即可直接读取企微智能表格数据，无需再等审批。
