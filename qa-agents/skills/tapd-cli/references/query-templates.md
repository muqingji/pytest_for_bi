# 高频查询模板

> 命中模板后直接替换 `{变量}`，跳过逐文件查找。
> 团队/模块枚举值见 [xiaoke-tapd-dict.md](xiaoke-tapd-dict.md)。

## 跨平台命令说明

- **macOS / Linux**：直接使用 `tapd-cli`，含特殊字符参数使用单引号 `'custom_field_8=EQ<团队名>'`。
- **Windows PowerShell**：使用 `tapd-cli`，含 `<>` 或 `|` 的参数必须使用单引号 `'custom_field_8=EQ<团队名>'` 防止被 PowerShell 解析为重定向或管道。

---

## 1. 团队 Bug 查询

### 1a. 按团队 + 严重级别 + 时间范围

**macOS / Linux**：

```bash
tapd-cli bug list workspaceid={workspace_id} limit=200 \
  'custom_field_8=EQ<{团队名}>' \
  'severity=fatal|serious' \
  'created={开始日期}~{结束日期}' \
  'order=created DESC' \
  fields=id,title,status,severity,current_owner,created,custom_field_one,custom_field_6,custom_field_two
```

**Windows PowerShell**：

```powershell
tapd-cli bug list workspaceid={workspace_id} limit=200 `
  'custom_field_8=EQ<{团队名}>' `
  'severity=fatal|serious' `
  'created={开始日期}~{结束日期}' `
  'order=created DESC' `
  fields=id,title,status,severity,current_owner,created,custom_field_one,custom_field_6,custom_field_two
```

**severity 组合速查**：

| 用户说法 | 参数值 |
| --- | --- |
| 致命 | `severity=fatal` |
| 严重及以上 | `severity=fatal\|serious` |
| 一般及以上 | `severity=fatal\|serious\|normal` |
| 全部 | 省略 severity 参数 |

### 1b. 按团队 + 状态

**macOS / Linux**：

```bash
tapd-cli bug list workspaceid={workspace_id} limit=200 \
  'custom_field_8=EQ<{团队名}>' \
  'status=new|in_progress|reopened' \
  'order=created DESC' \
  fields=id,title,status,severity,current_owner,created
```

**Windows PowerShell**：

```powershell
tapd-cli bug list workspaceid={workspace_id} limit=200 `
  'custom_field_8=EQ<{团队名}>' `
  'status=new|in_progress|reopened' `
  'order=created DESC' `
  fields=id,title,status,severity,current_owner,created
```

**状态 key 参见** [xiaoke-tapd-dict.md](xiaoke-tapd-dict.md) 的 `status` 映射。高频组合：

| 场景 | 参数值 |
| --- | --- |
| 未解决 | `status=new\|in_progress\|reopened\|feedback` |
| 已解决待验证 | `status=resolved\|verified` |
| 已关闭 | `status=closed\|rejected\|QA_audited` |

### 1c. 快速计数

结果集预期 <200 时，直接用 `list limit=200` 一次获取，省掉 count 调用；确需计数时使用 count：

```bash
tapd-cli bug count workspaceid={workspace_id} \
  'custom_field_8=EQ<{团队名}>' \
  'severity=fatal|serious'
```

---

## 2. 团队需求查询

> 需求的团队归属可能与 Bug 不同（Bug 用 `custom_field_8`）。
> 如需按团队查需求，可先确认自定义字段映射：`tapd-cli story fields workspaceid={workspace_id}`

### 2a. 按状态 + 时间范围

**macOS / Linux**：

```bash
tapd-cli story list workspaceid={workspace_id} limit=200 \
  'status=developing|planning|resolved|rejected' \
  'created={开始日期}~{结束日期}' \
  'order=created DESC' \
  fields=id,name,status,owner,priority_label,created
```

**Windows PowerShell**：

```powershell
tapd-cli story list workspaceid={workspace_id} limit=200 `
  'status=developing|planning|resolved|rejected' `
  'created={开始日期}~{结束日期}' `
  'order=created DESC' `
  fields=id,name,status,owner,priority_label,created
```

### 2b. 按分类

```bash
tapd-cli story list workspaceid={workspace_id} limit=200 \
  category_id={分类ID} \
  'order=created DESC' \
  fields=id,name,status,owner,priority_label,created
```

分类 ID 参见 [xiaoke-tapd-dict.md](xiaoke-tapd-dict.md) 的 `category_id` 映射。

### 2c. 按处理人

```bash
tapd-cli story list workspaceid={workspace_id} limit=200 \
  owner={TAPD用户名} \
  'status=developing|planning' \
  'order=created DESC' \
  fields=id,name,status,owner,priority_label,created
```

---

## 3. Bug 影响企业

### 关键字段映射

Bug 返回数据中，企业信息分布在以下字段：

| 字段 | 含义 | 示例 |
| --- | --- | --- |
| `custom_field_one` | 企业 ID | `826885` |
| `custom_field_6` | 企业账号名 | `zetarapower` |
| `custom_field_two` | 企业类型标签 | `VIP付费` / `付费` |

`fields` 中带上这三个字段即可直接获取企业信息，无需解析 `description`。

### 3a. 查询 Bug 并提取企业列表

```bash
tapd-cli bug list workspaceid={workspace_id} limit=200 \
  'custom_field_8=EQ<{团队名}>' \
  fields=id,title,status,severity,custom_field_one,custom_field_6,custom_field_two
```

返回后，按 `custom_field_6` 去重即可得到受影响企业清单。

### 3b. 按企业反查 Bug

**按企业账号名**：

```bash
tapd-cli bug list workspaceid={workspace_id} limit=200 \
  'custom_field_6=EQ<{企业账号名}>' \
  'order=created DESC' \
  fields=id,title,status,severity,created
```

**按企业 ID**：

```bash
tapd-cli bug list workspaceid={workspace_id} limit=200 \
  'custom_field_one=EQ<{企业ID}>' \
  'order=created DESC' \
  fields=id,title,status,severity,created
```

### 3c. 企业类型分布

```bash
tapd-cli bug list workspaceid={workspace_id} limit=200 \
  fields=id,custom_field_two
```

`custom_field_two` 枚举：`VIP付费` / `付费` / `自注册` / `开源` / `测试`。

---

## 4. 团队枚举速查

完整列表见 [xiaoke-tapd-dict.md](xiaoke-tapd-dict.md)，以下为高频团队：

| 团队名 | custom_field_8 值 |
| --- | --- |
| 平台架构组 | `'custom_field_8=EQ<平台架构组>'` |
| 基础业务团队 | `'custom_field_8=EQ<基础业务团队>'` |
| 协同业务团队 | `'custom_field_8=EQ<协同业务团队>'` |
| 开发平台 | `'custom_field_8=EQ<开发平台>'` |
| 大数据团队 | `'custom_field_8=EQ<大数据团队>'` |
| 运维团队 | `'custom_field_8=EQ<运维团队>'` |
| 售中团队 | `'custom_field_8=EQ<售中团队>'` |
| 流程团队 | `'custom_field_8=EQ<流程团队>'` |
| 集成平台组 | `'custom_field_8=EQ<集成平台组>'` |
