# 搜索策略详解

本文件包含 Step 3 代码搜索的详细策略示例。

> **调用约定**：所有策略通过 `sourcebot-cli.py` 直接调用，新增 `--compact` 节省 token、`--evidence-dir` 落盘证据。

统一调用格式：

```
# 默认模式（全量输出，适合读源码）
uv run --no-sync python scripts/sourcebot-cli.py <command> [options]

# 紧凑模式（节省 token，适合搜索/定位/汇总）
uv run --no-sync python scripts/sourcebot-cli.py <command> [options] --compact

# 证据落盘模式（结果写入证据目录供后续引用）
uv run --no-sync python scripts/sourcebot-cli.py <command> [options] --evidence-dir output/evidence/<YYYYMMDD-topic>/
```

---

## 策略 A：堆栈定位（有行号时最精准）

```
已知: OrderService.java:142 抛出 NPE
操作:
  # 第一步：glob 定位文件
  uv run --no-sync python scripts/sourcebot-cli.py glob --repo "backend-order" --pattern "**/OrderService.java" --compact

  # 第二步：读取异常行上下文（不加 --compact，需要全量源码）
  uv run --no-sync python scripts/sourcebot-cli.py read-file \
    --repo "backend-order" \
    --path "src/main/java/com/example/order/service/OrderService.java" \
    --offset 130 --limit 30

  # 第三步（可选）：同时落盘证据
  uv run --no-sync python scripts/sourcebot-cli.py read-file \
    --repo "backend-order" \
    --path "src/main/java/com/example/order/service/OrderService.java" \
    --offset 130 --limit 30 \
    --evidence-dir output/evidence/20260703-npe/
目的: 直接看异常行及其上下文
```

## 策略 B：符号定义查找（有类名/方法名时）

```
已知: OrderService.create 方法
操作:
  # 查类定义
  uv run --no-sync python scripts/sourcebot-cli.py symbol-def \
    --repo "backend-order" \
    --symbol "OrderService" \
    --compact

  # 查方法定义
  uv run --no-sync python scripts/sourcebot-cli.py grep \
    --repo "backend-order" \
    --pattern "public\\s+\\w+\\s+create" \
    --include "*.java" \
    --compact

  # 查方法调用方
  uv run --no-sync python scripts/sourcebot-cli.py symbol-ref \
    --repo "backend-order" \
    --symbol "create" \
    --compact
目的: 定位符号的精确定义，不误匹配注释或部分字符串
```

## 策略 C：错误消息搜索（有异常消息时）

```
已知: "Cannot invoke" "is null"
操作:
  uv run --no-sync python scripts/sourcebot-cli.py grep \
    --repo "backend-order" \
    --pattern "Cannot invoke.*is null" \
    --include "*.java" \
    --compact
目的: 找到所有抛出同类异常的位置
```

> **禁止**：勿将 CEP/`reqId` 错误码（`s311034432`、`1-52bd16` 等）当作策略 C 的 pattern — 见 SKILL「CEP / reqId 错误码熔断」。

## 策略 D：异常类搜索（有异常类型时）

```
已知: DuplicateKeyException
操作:
  # 紧凑搜索（节省 token）
  uv run --no-sync python scripts/sourcebot-cli.py grep \
    --repo "backend-order" \
    --pattern "DuplicateKeyException" \
    --include "*.java" \
    --compact

  # 跨仓库探测（先用 group-by-repo 看哪个仓库命中多）
  uv run --no-sync python scripts/sourcebot-cli.py grep \
    --pattern "DuplicateKeyException" \
    --group-by-repo \
    --compact
目的: 找到 catch/throw 该异常的所有位置
```

## 策略 E：文件名搜索（有文件路径时）

```
已知: OrderService.java
操作:
  # glob 定位文件
  uv run --no-sync python scripts/sourcebot-cli.py glob \
    --repo "backend-order" \
    --pattern "**/OrderService.java" \
    --compact

  # 读取文件内容
  uv run --no-sync python scripts/sourcebot-cli.py read-file \
    --repo "backend-order" \
    --path "src/main/java/com/example/order/service/OrderService.java" \
    --offset 1 --limit 100
目的: 从文件路径定位源码
```
