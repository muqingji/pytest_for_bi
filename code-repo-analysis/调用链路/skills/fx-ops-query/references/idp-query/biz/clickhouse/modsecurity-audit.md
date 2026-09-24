# modsecurity-audit（WAF审计日志）

> schema_verified_at: 2026-08-01 | platform: v5.10.0
> [!WARNING]
> **已废弃 / 不可查询**：platform v4.37.0 已将 `modsecurity_audit_log_dist` 从 tenant-filters 移除（variant `all_inactive` / scan 排除）。勿作为查询目标。

**说明**: ModSecurity WAF审计日志，记录Web应用防火墙检测到的请求和响应详情，用于安全攻击检测

**租户ID字段**: 无

**时间字段**: `_time_second_`、`collect_time`

---

## 表：modsecurity_audit_log_dist

### 存储与索引

| 项 | 值 |
| --- | --- |
| 状态 | **已废弃**，platform 无 `modsecurity_audit_log_dist.yaml` |

### 字段定义（历史参考，勿查询）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second_` | DateTime64(3) | 日志采集时间（秒级） |
| `collect_time` | DateTime64(3) | 日志采集时间 |
| `client_ip` | IPv4 | 客户端IP地址 |
| `server_id` | String | 服务器标识 |
| `client_port` | Int16 | 客户端端口 |
| `host_ip` | IPv4 | 目标主机IP |
| `host_port` | Int16 | 目标主机端口 |
| `unique_id` | String | 审计日志唯一ID |
| `request` | String | HTTP请求详情 |
| `response` | String | HTTP响应详情 |
| `producer` | String | 日志生产者模块标识 |
| `messages` | String | ModSecurity规则匹配消息 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 客户端IP | `client_ip` |
| 主机IP | `host_ip` |
| 唯一ID | `unique_id` |
| 时间 | `_time_second_`、`collect_time` |

### 查询示例

```bash
# 查询近1小时WAF拦截记录
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, client_ip, host_ip, host_port, messages FROM modsecurity_audit_log_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR ORDER BY _time_second_ DESC LIMIT 50"

# 统计被攻击目标分布
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT host_ip, host_port, COUNT(*) as cnt FROM modsecurity_audit_log_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR GROUP BY host_ip, host_port ORDER BY cnt DESC"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
- ./security-event-tracking.md - 安全事件追踪
