# fx-ops-bi Playbook 索引

按模块选择 playbook，命中后直接读对应文件。

## 模块路由表

| 模块 | 场景 | Playbook |
| --- | --- | --- |
| `sync-delay` | 同步延迟、推送延迟、MQ 积压、copier 报错、数据未更新 | sync-delay.md |
| `data-consistency` | BI 数据与源数据不一致、多算/漏算/数据重复；**先过作废/离职/驾驶舱默认值/主题权限口径** | data-consistency.md |
| `slow-query` | 报表/驾驶舱加载慢、CH 查询超时、SQL 慢 | slow-query.md |
| `join-splice` | 拼表结果异常、JOIN 数据不正确、宽表字段缺失 | join-splice.md |
| `aggregation` | 聚合计算错误、统计值偏差、去重计数异常 | aggregation.md |
| `render-failure` | 报表/驾驶舱白屏、渲染异常、组件加载失败；**有框架没数不是白屏，转权限口径** | render-failure.md |
| `field-issue` | 字段选不到/不显示、计算字段未生效、对象显示字段、不落库计算字段；**先过产品口径，字段描述同步走 fs-paas-metadata-rest（bi_field_desc 已实测不存在）** | field-issue.md |
| `export-failure` | 报表导出失败/无反应/超时、CH OOM、没有导出按钮；**无按钮先按 PaaS 2 小时功能权限** | export-failure.md |
| `permission-issue` | 列表有数据但报表看不到、改完权限看不到图、统计图没数；**先分三层缓存，再查 dt_auth** | permission-issue.md |
| `goal-management` | 目标值不显示、完成值为空、完成值与报表不一致、目标规则初始化中、完成值能看明细不能看；**完成值走考核对象共享** | goal-management.md |
| `subscription` | 订阅不推送、推送空白、推送数据与报表不一致；**当天改点次日生效，实时订阅无人员变量** | subscription.md |

## 共享约束

所有 playbook 共用 _common.md 中的全局约定和反模式（含**查询入口总表**：bi-clickhouse / bi-postgresql / bi-system / biz-app-log 四类入口与租户过滤规则）。

权限 / 对数 / 字段 / 目标 / 导出 / 订阅类问题：**先过对应 playbook 的 Step 0 产品口径**，再进 SQL / CH / dt_auth。FAQ 口径互殴不是产品 bug。收口按模块类别：产品口径类必须 `排查结论：设计如此` 或 `排查结论：需要研发处理` 二选一；运维性能类（同步延迟/慢查询/聚合/拼表/渲染）用 `排查结论：需要研发处理` / `排查结论：需要基础设施或运维处理` / `排查结论：已定位，建议动作如下`。
