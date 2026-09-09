---
name: tapd-story-branch
description: Extract a TAPD story ID and commit test candidates to one stable branch per requirement.
version: 1.0.0
---

# TAPD 需求分支提交

## 目标

一个 TAPD 需求只对应一个测试结论分支。同一需求重复运行时必须复用既有分支，不允许产生
`feature-xxx-1`、`feature-xxx-final` 这类重复分支。

## 输入规则

1. 输入可以是 TAPD 需求链接，也可以是复制的需求标题、链接和 `ID: xxx` 文本。
2. 优先读取显式 `ID: xxx`；例如
   `https://www.tapd.cn/tapd_fe/20097211/story/detail/1120097211001406418`
   的可见需求 ID 是 `1406418`。
3. 分支名固定为 `qa/tapd-story-<story_id>`。

## 仓库配置

仓库配置必须使用 `test-repository-config/1.0`，并包含：

- `repository_id`
- `repository_path`
- `access_class=approved_test_repository`
- `base_ref`
- `remote`
- `push`
- `purpose`
- `dedicated_results_repository_todo`

`push=false` 时只创建本地分支和提交；`push=true` 时必须提供显式远端，且禁止强推。
当前可临时使用共享仓库；新建专用测试结论仓库后，只需替换
`repository_path/repository_id`，并保留迁移 TODO，不改变分支契约。

## 安全规则

- 只接受 `N29` 产出的已完成 landing Artifact。
- 写入前重新校验每个候选内容哈希。
- 目标 Git 工作区必须是 clean 状态。
- 不写入业务仓库，不改路径白名单外的文件，不强制覆盖远端分支。
