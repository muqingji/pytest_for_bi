# fx-ops idp function — 自定义函数（APL）查询

自定义函数（User-Defined Function，也称 APL）的定义查询、执行日志和调用分析。

## 数据源

| 用途 | 数据源 | biz |
| --- | --- | --- |
| 函数定义、版本、参数 | paas PostgreSQL | `paas` |
| 函数插件 | paas PostgreSQL | `paas` |
| 函数执行日志 | ClickHouse | `biz-app-log` (表: `biz_log_function_dist`) |
| 函数调用详情（入参/返回值） | ClickHouse | `biz-app-log` (表: `biz_log_function_user_execute_dist`) |

## 查询模板

### 1. 列出租户所有当前生效的函数

```bash
fx-ops idp --profile <profile> query paas --tenant-id <id> --sql "SELECT api_name, function_name, binding_object_api_name, return_type, version, is_current, is_deleted, created_time, last_modified_time FROM mt_udef_function WHERE tenant_id = '<id>' AND is_current = true AND is_deleted = false ORDER BY api_name" -j
```

### 2. 查某个函数的所有版本

```bash
fx-ops idp --profile <profile> query paas --tenant-id <id> --sql "SELECT api_name, function_name, version, is_current, is_deleted, created_time FROM mt_udef_function WHERE tenant_id = '<id>' AND api_name = '<apiName>' ORDER BY version" -j
```

### 3. 查函数定义详情（含参数和函数体）

```bash
fx-ops idp --profile <profile> query paas --tenant-id <id> --sql "SELECT api_name, function_name, binding_object_api_name, parameters, return_type, body, version, is_current FROM mt_udef_function WHERE tenant_id = '<id>' AND api_name = '<apiName>' AND is_current = true" -j
```

### 4. 查函数插件列表

```bash
fx-ops idp --profile <profile> query paas --tenant-id <id> --sql "SELECT * FROM mt_function_plugin WHERE tenant_id = '<id>' LIMIT 50" -j
```

### 5. 函数执行日志（最近 1 小时）

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT apiName, type, version, errorCode, cost, _time_second_, error FROM biz_log_function_dist WHERE tenantId = '<id>' AND _time_second_ > now() - INTERVAL 1 HOUR ORDER BY _time_second_ DESC LIMIT 50" -j
```

### 6. 函数执行错误日志

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT apiName, error, errorCode, cost, _time_second_, traceId FROM biz_log_function_dist WHERE tenantId = '<id>' AND errorCode != '' AND _time_second_ > now() - INTERVAL 1 HOUR ORDER BY _time_second_ DESC LIMIT 50" -j
```

### 7. 按函数统计调用量和平均耗时

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT apiName, COUNT(*) as call_count, AVG(cost) as avg_cost_ms, countIf(errorCode != '') as error_count FROM biz_log_function_dist WHERE tenantId = '<id>' AND _time_second_ > now() - INTERVAL 1 HOUR GROUP BY apiName ORDER BY call_count DESC LIMIT 30" -j
```

### 8. 函数调用详情（入参、返回值、异常）

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT functionApiName, parameters, returnType, returnValue, success, exception, bindingApiName, objectId, module, createTime, durationTime, _time_second_ FROM biz_log_function_user_execute_dist WHERE tenantId = '<id>' AND _time_second_ > now() - INTERVAL 1 HOUR ORDER BY _time_second_ DESC LIMIT 20" -j
```

### 9. 按模块统计函数调用

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT module, COUNT(*) as call_count, AVG(durationTime) as avg_duration_ms, SUM(CAST(NOT success AS UInt8)) as fail_count FROM biz_log_function_user_execute_dist WHERE tenantId = '<id>' AND _time_second_ > now() - INTERVAL 1 HOUR GROUP BY module ORDER BY call_count DESC LIMIT 20" -j
```

### 10. 按 traceId 查函数调用链

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT functionApiName, parameters, returnValue, success, exception, durationTime, createTime, _time_second_ FROM biz_log_function_user_execute_dist WHERE _time_second_ > now() - INTERVAL 1 HOUR AND traceId = '<traceId>' ORDER BY _time_second_" -j
```

## 相关文档

- idp-query-sql.md — PostgreSQL 查询规则
- idp-query-clickhouse.md — ClickHouse 查询规则（必读时间窗口估算流程）
- idp-query/biz/clickhouse/biz-log-function.md — ClickHouse 函数日志表字段详细文档
- idp-query/biz/postgresql/paas-function.md — paas 函数相关表字段详细文档

## 诊断报告映射

当 APL / 自定义函数本身是根因或关键证据时，输出给 `fx-ops` 主控的结论必须包含可映射到 `DIA-diagnostic-data.json` 的 `code_analysis` 字段 的结构：

```json
{
 "trace_path": ["触发入口", "functionApiName@version", "失败语句或慢调用"],
 "source_code": {
  "source_type": "apl",
  "language": "APL",
  "name": "<functionApiName 或 apiName>",
  "version": "<version>",
  "code_snippet": "<函数体或关键片段>"
 },
 "analysis": "说明函数为什么失败、超时、重复执行或返回值异常。",
 "fix_suggestions": [
  {
   "type": "must",
   "title": "修复 APL 空值/幂等/超时逻辑",
   "content": "具体改法和验证方法。",
   "code_snippet": "<建议修改后的 APL 片段，可选>"
  }
 ]
}
```

如果无法拿到完整函数体，也要填 `source_code.name` / `version` / 已知片段，并在 `analysis` 中说明缺失原因和下一步取证命令。不要只返回"自定义函数报错，需要修复"这类笼统结论。
