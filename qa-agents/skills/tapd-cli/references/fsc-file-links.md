# FSC 文件链接处理

## 背景

Bug 的 `description` 内容中可能包含指向纷享内部文件存储的链接：

```text
https://www.fxiaoke.com/FSC/EM/File/GetByPath?path=N_202606_15_f8fe4d2f311c438e9b0622c9156de41f1.jpeg
```

这些链接**无法直接通过浏览器访问**，必须使用 `fx-ops` CLI 下载并转换为本地文件。

## 识别与提取

在 `description` 字段中匹配以下路径特征：

- `www.fxiaoke.com/FSC/EM/File/GetByPath`

常见存在形式：

| 格式 | 示例 |
| --- | --- |
| Markdown 链接 | `[截图](https://www.fxiaoke.com/FSC/EM/File/GetByPath?path=N_202606_...jpeg)` |
| 纯文本 URL | `https://www.fxiaoke.com/FSC/EM/File/GetByPath?path=N_202606_...jpeg` |
| HTML `<img>` | `<img src="https://www.fxiaoke.com/FSC/EM/File/GetByPath?path=N_202606_...jpeg">` |

从 URL 的 `?path=` 查询参数中提取 `path` 值（**不要传完整 URL**）：

| 原始 URL | 提取的 path 参数 |
| --- | --- |
| `https://www.fxiaoke.com/FSC/EM/File/GetByPath?path=N_202606_15_f8fe4d2f311c438e9b0622c9156de41f1.jpeg` | `N_202606_15_f8fe4d2f311c438e9b0622c9156de41f1.jpeg` |

## 转换与下载命令

```bash
# 默认输出到当前目录（文件名同 path）
fx-ops idp stone get-by-path --path N_202606_15_f8fe4d2f311c438e9b0622c9156de41f1.jpeg --profile foneshare

# 指定保存路径
fx-ops idp stone get-by-path --path N_202606_15_f8fe4d2f311c438e9b0622c9156de41f1.jpeg --profile foneshare -O /tmp/screenshot.jpeg
```

### 环境要求

`--profile foneshare` 环境支持此命令。若当前环境未配置 `foneshare` profile，需先切换或准备对应 profile。

## 批量处理

当 `description` 中包含多个 FSC 链接时，可逐一提取 `path` 并批量下载：

```bash
echo "$desc" | grep -oP 'GetByPath\?path=\K[^"&\s<>)]+' | while read -r path; do
  fx-ops idp stone get-by-path --path "$path" --profile foneshare -O "tmp/$path"
done
```

## 执行纪律

- Bug `description` 中包含 FSC 链接时，**必须告知用户**原始链接无法直接浏览器打开，需先下载或转换；禁止直接把原始 FSC 链接发给用户并声称“可点击查看”。
- 如果当前环境未配置 `foneshare` profile，不要盲目执行命令，应先指出环境要求。
- 下载的文件保存在 `tmp/` 或 `output/` 临时目录中，不得将临时文件直接提交入仓。
