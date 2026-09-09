# TAPD 项目文档与附件管理

## 术语与边界判定

- **项目文档（Document）**：TAPD 项目中的在线/上传类文档，CLI 目前支持通过 `tapd-cli document download` 获取文档的下载链接（`GET /documents/down`）。
- **实体附件（Attachment）**：绑定在需求、缺陷、任务上的文件附件，使用 `tapd-cli attachment` 系列命令进行上传、列表、下载与图片处理。
- **Wiki 页面（Wiki）**：在线可协同编辑的富文本/Markdown 页面，使用 `tapd-cli wiki` 系列命令管理。

> **判定原则**：
> - 用户明确要求“获取/下载项目文档”时，使用 `tapd-cli document download`。
> - 用户要求“上传附件到需求/缺陷/任务”时，使用 `tapd-cli attachment upload`。
> - 用户明确要求“创建/修改 Wiki 页面”时，使用 `tapd-cli wiki add/update`。

## 项目文档下载

获取指定项目文档的下载链接：

```bash
tapd-cli document download workspaceid=20019471 id=1120019471001009040
```

参数说明：
- `workspaceid`：项目 ID。
- `id`：文档 ID（字符串）。

## 实体附件管理

### 1. 查询实体下的附件

```bash
tapd-cli attachment by-entity workspaceid=20019471 entry-id=1120019471001400908
```

### 2. 获取附件下载链接

```bash
tapd-cli attachment download workspaceid=20019471 id=1120019471001001410
```

> **注意**：返回的附件下载链接有效期为 300 秒，获取后应及时下载或处理。

### 3. 上传附件到实体

```bash
tapd-cli attachment upload workspaceid=20019471 type=bug entry-id=1120019471001056789 file=/tmp/screenshot.png
```

参数说明：
- `type`：实体类型，支持 `story` / `bug` / `task`。
- `entry-id`：目标实体 ID。
- `file`：本地文件绝对路径或相对路径（文件大小 < 250MB）。
- `owner`：（可选）附件上传人。

### 4. 上传图片到富文本描述

当需要在需求、缺陷或评论中插入图片时，使用 `upload-image` 获取图片路径与 HTML 标签：

```bash
tapd-cli attachment upload-image workspaceid=20019471 file=/tmp/diagram.png
```

返回包含 `image_src` 和 `html_code`（如 `<img src="/tfl/pictures/...">`），可直接拼入 `description` 字段。
