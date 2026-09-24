# Sourcebot 查询语法参考

> 供 `code-search` skill 使用。当需要构建 grep pattern 或 glob pattern 时加载此参考文件。

## grep 正则语法

`pattern` 参数使用标准正则表达式。**始终区分大小写**。

> **CLI 用法对应**：`uv run --no-sync python scripts/sourcebot-cli.py grep --pattern "<regex>" --repo "<repo>" [options] --compact`

| 正则 | 用途 | 示例 CLI 调用 |
|------|------|--------------|
| `foo.*bar` | foo 后面出现 bar | `grep --pattern "null.*return" --repo "<repo>" --compact` |
| `^function\\s+\\w+` | 以 function 开头的定义 | `grep --pattern "^public\\s+void\\s+\\w+" --repo "<repo>" --compact` |
| `\\buserId\\b` | 完整单词 userId | `grep --pattern "\\bNPE\\b" --repo "<repo>" --compact` |
| `class\\s+\\w+Exception` | 异常类定义 | `grep --pattern "class\\s+\\w+Exception" --repo "<repo>" --compact` |
| `throw\\s+new\\s+\\w+` | throw 语句 | `grep --pattern "throw\\s+new\\s+NullPointerException" --repo "<repo>" --compact` |
| `(foo\|bar)` | 匹配 foo 或 bar | `grep --pattern "(NPE\|NullPointerException)" --repo "<repo>" --compact` |

### 常用搜索模式（CLI 版）

```bash
# 搜索异常类定义
uv run --no-sync python scripts/sourcebot-cli.py grep --repo "backend-order" --pattern "class\\s+\\w+Exception" --include "*.java" --compact

# 搜索空值检查缺失
uv run --no-sync python scripts/sourcebot-cli.py grep --repo "backend-order" --pattern "if\\s*\\(\\s*\\w+\\s*==\\s*null\\s*\\)" --include "*.java" --compact

# 搜索特定文件中的方法定义
uv run --no-sync python scripts/sourcebot-cli.py grep --repo "backend-order" --pattern "public\\s+\\w+\\s+createOrder" --path "src/main/java" --compact

# 跨仓库探测（先看哪个仓库命中多）
uv run --no-sync python scripts/sourcebot-cli.py grep --pattern "OrderService" --group-by-repo --compact
```

## glob 语法

`pattern` 参数使用标准 glob 语法。

> **CLI 用法对应**：`uv run --no-sync python scripts/sourcebot-cli.py glob --pattern "<glob>" --repo "<repo>" --compact`

| 示例 | 用途 |
|------|------|
| `**/*Service.java` | 所有 Service 类 |
| `src/**/*Controller.java` | src 下所有 Controller |
| `**/*.{java,kt}` | Java 和 Kotlin 文件 |
| `**/application*.yml` | 配置文件 |
| `**/test/**/*Test*.java` | 测试文件 |

## commits 时间参数

`--since`/`--until` 参数支持 ISO 8601 日期和相对格式。

> **CLI 用法对应**：`uv run --no-sync python scripts/sourcebot-cli.py commits --repo "<repo>" --since "7 days ago" --compact`

| 格式 | 示例 |
|------|------|
| 相对时间 | `"7 days ago"`, `"last week"`, `"yesterday"`, `"today"` |
| ISO 8601 日期 | `"2024-01-01"`, `"2024-12-31"` |

## read-file 注意事项

> **CLI 用法对应**：`uv run --no-sync python scripts/sourcebot-cli.py read-file --repo "<repo>" --path "<path>" [--offset N] [--limit N]`

- `--offset` 是 **1-indexed** 行号，**最小 1**；传 `0` 或负数 CLI 会报错退出（服务端要求 offset ≥ 1）
- 单次最多 500 行
- 输出上限 5KB，超限时用递增 offset 继续读取
- 长行（>2000 字符）会被截断
- read-file 调用**不加** `--compact`（需要全量源码内容做分析）
