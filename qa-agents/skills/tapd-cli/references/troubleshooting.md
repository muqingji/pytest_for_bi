# 故障排查

## 快速可用性检查

执行 TAPD 操作前，可使用以下步骤确认环境状态：

1. **检查环境变量**：
   - 确认当前 shell 已注入 `TAPD_TOKEN` 与 `TAPD_API_ENDPOINT`。
   - 注意：环境变量沿进程树继承。新开的 subagent 或终端若缺失变量，需重新配置。
2. **探测 CLI 命令**：

   ```bash
   tapd-cli user workspaces
   ```

   若能成功列出项目列表，说明 CLI 与 Token 均可用。

## CLI 常见问题

| 现象 | 可能原因 | 解决方案 |
| --- | --- | --- |
| `command not found: tapd-cli` | CLI 未安装或未加入 `PATH` | 按主文档说明运行一键安装脚本，或确认 `~/.local/bin`（Windows: `%USERPROFILE%\.local\bin`）已在 `PATH` 中 |
| 报错缺少 Token (`missing token`) | 未设置 `TAPD_TOKEN` | 在环境中导出 `export TAPD_TOKEN="xxx"` 或在配置中注入 |
| 参数值含空格被拆分 | 未加引号包裹 | 参数值含空格时使用双引号包裹，如 `"order=created DESC"` |
| 管道过滤报错（如 `jq` 失败） | 过滤表达式有误 | 检查 `jq` / Python 过滤逻辑；非 CLI 错误，无需重新执行 API 查询 |

### Windows PowerShell 特殊字符问题

在 Windows PowerShell 下执行命令时：

| 现象 | 原因 | 解决方案 |
| --- | --- | --- |
| 提示 `'xxx' 不是内部或外部命令...` | 参数中的 `\|` 被 PowerShell 误当作管道运算符 | 将包含 `\|` 的整个参数用单引号包裹，如 `'severity=fatal\|serious'` 或 `'status=new\|in_progress'` |
| 提示找不到文件或重定向错误 | 参数中的 `<>` 被误当作重定向字符 | 将包含 `<>` 的整个参数用单引号包裹，如 `'custom_field_8=EQ<基础业务团队>'` |

## API 常见错误

| 现象 | 原因 | 解决方案 |
| --- | --- | --- |
| HTTP 401 认证失败 | Token 过期、无效或无权限 | 检查 `TAPD_TOKEN` 是否有效，确认是否有对应项目的访问权限 |
| 列表返回空数组 | 分页参数超出、查询条件过窄或状态不存在 | 调整 `limit` 与 `page`，检查筛选字段是否正确 |
| 状态筛选查不到数据 | 项目采用了自定义状态，与默认英文 key 不一致 | 使用 `v_status="状态中文名"` 传中文状态，或用 `tapd-cli bug fields workspaceid=XXX` 查看状态映射 |
| 字段更新失败 / 静默存为脏值 | 下拉/单选自定义字段传入了序号而非候选项文案 | 阅读 [custom-fields.md](custom-fields.md)，按合法文案本身传值 |
