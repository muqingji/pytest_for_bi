# MongoDB 业务线

按业务含义查找 `fx-ops idp query <biz>`。**各 biz 表级筛选（JSON filter 模板）** 见 [index.md](./mongodb/index.md)。

完整列表见 [mongodb/index.md](./mongodb/index.md)（44 个 biz）。常用：

| biz 命令 | 说明 | 筛选文档 |
| --- | --- | --- |
| `cross-enterprise-sharedisk` | 互联网盘（勿用 `oa-netdisk`） | [cross-enterprise-sharedisk.md](./mongodb/cross-enterprise-sharedisk.md) |
| `link-eip-data-sync` | EIP Mongo 缓冲 `buf_*`（**双方言**，须 `--dialect mongodb`） | [link-eip-data-sync.md](./mongodb/link-eip-data-sync.md) |
| `open-message` | 开放消息 | [open-message.md](./mongodb/open-message.md) |
| `paas-bpm` | 审批流 | [paas-bpm.md](./mongodb/paas-bpm.md) |
| `paas-workflow` | 工作流 | [paas-workflow.md](./mongodb/paas-workflow.md) |
| `qixin-message` | 企信消息 | [qixin-message.md](./mongodb/qixin-message.md) |
| `org-data` | 组织数据 | [org-data.md](./mongodb/org-data.md) |
| `sandbox` | 沙箱 | [sandbox.md](./mongodb/sandbox.md) |
| `paas-ai` | AI 平台（配置以 scan 为准） | [paas-ai.md](./mongodb/paas-ai.md) |
| `user-session` | 用户会话（登录/过期/终端） | [user-session.md](./mongodb/user-session.md) |

## 相关文档

- [业务线总览](index.md)
- [表级筛选索引](./mongodb/index.md)
- [filterHint 拼 SQL](../../idp-query-filter-hint.md)
- [MongoDB 查询规则](../../idp-query-mongodb.md)
