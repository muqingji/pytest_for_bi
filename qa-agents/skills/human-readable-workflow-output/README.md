# 启用方式

当前沙箱把 `~/.codex/skills` 与仓库根 `.codex/skills` 设为只读，无法直接落盘。
在你自己终端执行以下命令启用该 skill：

```bash
ln -s /Users/liushanshan/code/my/pytest_for_bi/qa-agents/skills/human-readable-workflow-output \
  /Users/liushanshan/.codex/skills/human-readable-workflow-output
```

重开 Codex 会话后，任何针对 qa-agents 的 agent/渲染改动都会自动加载本规范。
