# Dubbo 注册中心只读查询

> 适用于：当排障需要确认某接口有哪些 provider/consumer、某应用暴露了哪些服务、注册是否存活时，调用平台只读 CLI `fx-ops idp dubbo show ...`。
>
> **红线**：禁止在 skill 内直连 Zookeeper；禁止做 Dubbo 治理写操作或泛化试调；禁止把 Dubbo 伪装成 `biz-list` SQL dialect 去 `idp query`。

## 与调用链路日志的边界

| 你要查 | 走哪个 |
|--------|--------|
| 接口在注册中心的 provider/consumer 列表 | → `idp dubbo show providers/consumers` |
| 接口被调了多少次、耗时、成功率（采样统计） | → `biz-app-log` 的 `rpc_dist` / `service_dist` |
| 某次调用的完整链路（traceId → 各节点耗时） | → `fx-ops-tracing` |

**关键区分**：
- **注册信息**：接口在 Zookeeper/Nacos 等注册中心当前持久化的 provider/consumer 地址列表，反映的是"理论上谁能调谁"
- **调用日志**：请求流经网关后的实际采样记录，反映的是"实际上谁调了谁、耗时如何"

两者没有替代关系。

## 命令索引

> 完整命令以 `fx-ops idp dubbo -h` 和 `fx-ops idp dubbo show -h` 为准。

### 1. 查看所有服务组

```bash
fx-ops idp --profile <PROFILE> dubbo show groups [-j]
```

响应示例：

```json
{"data":{"resource":"groups","items":["Lock","dubbo","fs-bi-crm-report",...],"total":57,"page":1,"pageSize":20,"hasMore":true}}
```

### 2. 查看服务列表

```bash
# 查看指定 group 下的所有服务（默认 group 来自服务端配置，通常为 dubbo）
fx-ops idp --profile <PROFILE> dubbo show services --group dubbo [-j]

# 搜索服务名（模糊匹配）
fx-ops idp --profile <PROFILE> dubbo show services --group dubbo -q <KEYWORD> [-j]

# 只看当前有 live provider 的服务
fx-ops idp --profile <PROFILE> dubbo show services --group dubbo --live-only [-j]
```

响应示例：

```json
{"data":{"resource":"services","group":"dubbo","items":[{"interfaceName":"com.facishare.approve.api.service.ApproveFormFlowService"},...],"total":2846,"page":1,"pageSize":20,"hasMore":true}}
```

### 3. 查看单个服务的 provider 和 consumer

```bash
fx-ops idp --profile <PROFILE> dubbo show service <INTERFACE> [--group <GROUP>] [-j]
```

返回该接口的完整注册信息，包括所有 provider 和 consumer。

### 4. 查看 provider 列表

```bash
fx-ops idp --profile <PROFILE> dubbo show providers <INTERFACE> [--group <GROUP>] [-j]
```

**最常用**：确认某接口当前有哪些 provider 在注册。

响应示例：

```json
{
  "data": {
    "resource": "providers",
    "group": "dubbo",
    "interfaceName": "com.facishare.approve.api.service.ApproveFormFlowService",
    "items": [
      {
        "application": "fs-feeds-next-provider",
        "side": "provider",
        "host": "10.34.39.217",
        "port": "28055",
        "interfaceName": "...",
        "methods": ["getApproveFormFlowV1"],
        "dubboVersion": "2.9.5",
        "url": "dubbo://10.34.39.217:28055/...?"
      }
    ],
    "total": 2,
    "page": 1,
    "pageSize": 20,
    "hasMore": false
  }
}
```

### 5. 查看 consumer 列表

```bash
fx-ops idp --profile <PROFILE> dubbo show consumers <INTERFACE> [--group <GROUP>] [-j]
```

响应示例：

```json
{
  "data": {
    "resource": "consumers",
    "group": "dubbo",
    "interfaceName": "...",
    "items": [
      {
        "application": "fs-feeds-biz",
        "side": "consumer",
        "host": "10.34.10.17",
        "port": "",
        "methods": ["getApproveFormFlowV1"],
        "dubboVersion": "2.9.5",
        "group": "urgent",
        "url": "consumer://10.34.10.17/...?"
      }
    ],
    "total": 4,
    "page": 1,
    "pageSize": 20,
    "hasMore": false
  }
}
```

### 6. 按应用名查找

```bash
# 查找某应用作为 provider 暴露的所有接口
fx-ops idp --profile <PROFILE> dubbo show applications --side provider [-j]

# 查找某应用作为 consumer 引用的所有接口
fx-ops idp --profile <PROFILE> dubbo show applications --side consumer [-j]
```

响应示例：

```json
{
  "data": {
    "resource": "applications",
    "group": "dubbo",
    "side": "provider",
    "items": [
      {"application": "fs-eservice-cases-provider", "sides": ["provider"], "serviceCount": 212},
      {"application": "fs-feeds-next-provider", "sides": ["provider"], "serviceCount": 15}
    ],
    "total": 110,
    "page": 1,
    "pageSize": 20,
    "hasMore": true
  }
}
```

## 典型排查场景

### 场景 1：接口调不通，怀疑没有可用 provider

```
用户：某服务调不通，说是 no provider
排查：fx-ops idp dubbo show providers <INTERFACE>
判断：total=0 → 注册中心无 provider，可能是应用未启动或注册 group 写错
     items 为空数组但 total>0 → 可能是残留空壳节点
```

### 场景 2：灰度环境和主环境注册不一致

```
用户：灰度能调通，主环境不行
排查：分别查两个 profile
     fx-ops idp --profile gray dubbo show providers <INTERFACE>
     fx-ops idp --profile prod dubbo show providers <INTERFACE>
对比两边 provider 列表的 host、port、methods
```

### 场景 3：某个 consumer 收不到消息

```
用户：某应用订阅了服务但收不到消息
排查：fx-ops idp dubbo show consumers <INTERFACE>
     对比 provider 列表，确认网络直通配置是否正确
```

## 与 rpc_dist / service_dist 的配合

```
rpc_dist / service_dist（biz-app-log）：回答「调用了多少次、耗时多少」
dubbo show providers/consumers：回答「谁能被调用、谁在调用」
两者联合可判断：
  - 注册中心有 provider 且调用日志有记录 → 正常
  - 注册中心有 provider 但调用日志无记录 → 消费者未启动或网络问题
  - 注册中心无 provider → 应用未部署或注册失败
```
