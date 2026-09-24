# 三星 Android 通知不可达：先 TAPD/Wiki，生产日志未跑不要编造成功零行

## 问题类型
Android 三星系统提示缺失，怀疑厂商通道未接入。

## 本单已验证
- TAPD bug list：可读。附件 by-entity 成功零行（客户日志不在 TAPD 附件）
- Wiki 168821835：可读。厂商通道名单无三星
- foneshare whoami / stone / object_y31e4__c：401 认证失败，不是成功零行

## 失败教训
- 客户 16:00 错误日志应在 CRM object_y31e4__c（待办 name 字段，禁止把 name 当 TAPD ID），不要先查 TAPD 附件
- 截图走 fx-ops idp stone get-by-path --profile foneshare；401 就停，不写「没有截图」当现象不成立
- 日志未命中 ≠ 请求未到达；401 ≠ 成功零行

## 有权限后再跑（本单未跑，不要当已查）
不要把下面写成已确认根因查询。仅作后续入口：
- 设备/App：front_trace 类日志，userId=<ea>.<userId>
- 推送应用日志：app_log 中待办/消息服务，需先确认实际 appName
- 过滤先用企业/用户/时间窗（CST 与 UTC 同时写）

## 来源
`output/evidence/20260911-samsung-push-1120019471001436945`（历史取证路径，不保证当前工作区存在）
