# xiaoke TAPD 字段词典

> **注意**：查询接口返回的枚举字段（`status`、`severity`、`resolution`、`custom_field_8` 等）为 **key**（如 `resolved`、`serious`、`fixed`），而非中文 label。展示给用户前，应通过本文档中的映射表将 key 转换为对应的中文 label（如 `resolved` → `已解决`、`serious` → `严重`）。

字段不在本表中时，用 `fields` + `jq` 实时查（见 [cli-advanced.md](cli-advanced.md)）。

## workspace 20019471

### Bug 字段

#### status（状态）

```json
{
  "new": "新",
  "in_progress": "接受/处理",
  "reopened": "重新打开",
  "feedback": "需要再次说明",
  "suspended": "进入技术攻关项目",
  "resolved": "已解决",
  "verified": "已验证",
  "status_1": "fs系统bug已作废",
  "QA_audited": "已上线",
  "rejected": "已拒绝",
  "acknowledged": "已上线待用户验证",
  "closed": "已转需求",
  "unconfirmed": "待产品/技术确认",
  "PMM_audited": "搁置"
}
```

#### severity（严重程度）

```json
{
  "fatal": "致命",
  "serious": "严重",
  "normal": "一般",
  "prompt": "提示",
  "advice": "建议"
}
```

#### platform（软件平台）

Web, Server, Android, 鸿蒙, iOS, 小程序, H5, 客户端, 卡梅隆, Pad, Weex, 需求, UI/UE, 其他

#### resolution（解决方法）

```json
{
  "ignore": "无需解决",
  "fixed": "已修改",
  "fix later": "延期解决",
  "failed to recur": "无法重现",
  "external reason": "外部原因",
  "duplicated": "重复",
  "intentional design": "设计如此",
  "unclear description": "问题描述不准确",
  "feature change": "需求变更",
  "transferred to story": "已转需求",
  "hold": "挂起"
}
```

#### custom_field_one（企业 ID）

纯数字字符串，如 `826885`、`601362`。用于按企业反查 Bug。

#### custom_field_6（企业账号名）

企业登录账号，如 `zetarapower`、`etonkidd`。用于展示和按企业名查询。

#### custom_field_two（企业类型标签）

VIP付费, 付费, 自注册, 开源, 测试

#### custom_field_7（BUG来源，即来源渠道）

400, 纷享客服, 金字招牌, 营销QQ, 微信, 运营群, CSM, 销售, 渠道, 研发内部, 运营管理团队, 意见反馈, 其他

#### custom_field_8（所属团队）

售中团队, 售前业务, 快消团队, 基础业务团队, 协同业务团队, 开发平台, 元数据权限组, 流程团队, IOS架构组, Web架构组, 小程序架构组, Android架构组, BI团队, 大数据团队, 平台架构组, 老协同团队, 运维团队, 订货业务组, 制造行业组, 集成平台组, 营销业务组, 互联平台组, 性能架构团队, 实施团队, 客开团队-制造业, 客开团队-快消行业, 客开团队, H5团队, 其他团队, 项目管理

> 含约 20 个（作废）团队未列出，用 `tapd-cli bug fields workspaceid=20019471 | jq '.data.custom_field_8.options'` 查看。

#### custom_field_15（拒绝原因）

产品设计如此, 技术设计如此, 用户操作错误, 用户不熟悉产品, 产品咨询, 用户无法复现, 用户设备/网络问题, 用户数据问题, 实施问题, 信息不足/错误, 数据延迟更新, 重复bug, 灰度功能未申请, 其他原因

#### custom_field_17（是否重复Bug）

重复bug, 非重复Bug

#### custom_field_24（是否需要补充文档）

无需补充文档, 需补充产品手册/实施指南, 需补充乐享文档, 已补充乐享文档, 有乐享文章未排查

#### custom_field_four（企业类型）

VIP付费, 付费, 自注册, 开源, 测试

#### custom_field_26（客户类型打标）

国际化, 测试2

#### priority_label（优先级）

```json
{
  "High": "高",
  "Middle": "中",
  "Low": "低",
  "Nice To Have": "锦上添花"
}
```

### Story 字段

#### status（状态）

```json
{
  "planning": "规划中",
  "developing": "实现中",
  "resolved": "已实现",
  "rejected": "已拒绝"
}
```

#### priority_label（优先级）

同 Bug 字段，key 与 label 映射一致（`High` → 高，`Middle` → 中，`Low` → 低，`Nice To Have` → 锦上添花）。

#### category_id（分类）

```json
{
  "1120019471001000583": "CRM",
  "1120019471001000584": "社交通讯",
  "1120019471001004404": "快消团队",
  "1120019471001004661": "老协同业务",
  "1120019471001004716": "小程序",
  "1120019471001004936": "已上线",
  "1120019471001004939": "确定不做",
  "1120019471001005321": "社交团队",
  "1120019471001005731": "安全",
  "1120019471001005846": "基础业务",
  "1120019471001005965": "企微SCRM",
  "1120019471001006007": "web架构组",
  "1120019471001006177": "开发平台",
  "1120019471001006446": "互联平台",
  "-1": "未分类"
}
```

#### version（版本）

UAT, 应用市场版本, 内测, H5客开, 发版第一周
