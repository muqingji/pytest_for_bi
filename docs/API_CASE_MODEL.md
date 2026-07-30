# 接口与测试场景维护规范

## 分层

```text
idl/http/*.openapi.json          HTTP 接口契约
config/environment.<env>.json   环境域名与登录配置
test_data/<subject>.<env>.json  测试主题在某个环境下的实际 case
tests/test_api_cases.py          唯一 pytest 通用执行入口
```

接口契约维护 `operationId`、HTTP method、path、请求/响应 schema 和鉴权注入规则。
case 文件不得重复维护 URL、method、登录 Cookie 或 `_fs_token`。

## 测试主题

一个 `test_case` 表示一个测试主题。同一主题通过文件后缀区分环境：

```text
test_data/bi/query_dynamic_type_info_and_options.112.json
test_data/bi/query_dynamic_type_info_and_options.online.json
```

每个文件可以包含多条实际 case：

```json
{
  "test_case": {
    "id": "bi_dynamic_type",
    "name": "BI 动态分类查询",
    "api": "bi.query_dynamic_type_info_and_options",
    "tags": ["bi"]
  },
  "cases": [
    {
      "id": "example",
      "name": "具体测试场景",
      "priority": "P1",
      "req": {
        "params": {},
        "body": {}
      },
      "resp": {
        "status_code": 200,
        "body": {}
      }
    }
  ]
}
```

pytest 会把每条实际 case 展开为独立测试，测试 ID 为：

```text
<test_case.id>::<case.id>[<priority>]
```

`req.body` 作为 JSON 请求体，`req.params` 为业务查询参数，`resp` 使用框架通用
断言格式。每条实际 case 必须包含 `id`、`priority`、`req` 和 `resp`。

## 优先级过滤

不指定优先级时执行当前环境的全部 case。精确选择优先级：

```bash
python3 -m pytest --env=112 --priority=P0
python3 -m pytest --env=112 --priority=P0,P1
TEST_PRIORITIES=P0,P1 python3 -m pytest --env=112
```

过滤发生在 pytest 收集阶段，没有命中的 case 不会发起登录或接口请求。

## 鉴权

CRM 登录由 session 级 pytest fixture 完成。登录响应 Cookie 保存在共享 HTTP
会话中。接口契约中的 `x-auth-cookie-query` 声明如何把 Cookie 注入请求，例如：

```json
{
  "x-auth-cookie-query": {
    "cookie": "fs_token",
    "parameter": "_fs_token"
  }
}
```

框架会读取会话中的 `fs_token` 并生成 `_fs_token` 参数。以下内容禁止写入接口契约
或 case 文件：

- `_fs_token` 的实际值
- `FSAuthX`、`FSAuthXC`、`JSESSIONID`
- 企业账号、用户名和密码
- 从浏览器复制的完整 Cookie

112 环境凭据只通过 `FXIAOKE_112_*` 环境变量、CI Secret 或被 Git 忽略的
`config/environment.112.local.json` 提供。

## 新增接口

1. 在 `idl/http` 下对应 OpenAPI 文件中增加 path 和 operation。
2. 为 operation 设置全局唯一的 `operationId`。
3. 补充请求和响应 schema。
4. 若接口要求 `_fs_token`，配置 `x-auth-cookie-query`。
5. case 的 `test_case.api` 只引用 `operationId`。

当前 BI 分类接口定义在 `idl/http/bi.openapi.json`。
