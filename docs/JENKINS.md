# Jenkins 配置说明

根目录 `Jenkinsfile` 使用 Declarative Pipeline，适合创建为 Jenkins 的
Pipeline job 或 Multibranch Pipeline job。

## Jenkins 前置条件

构建节点需要具备：

- `python3.11` 命令；
- 能访问项目依赖的 Python 包源；
- 能访问目标 HTTP/RPC/数据库网络；
- Jenkins 插件：Pipeline、JUnit、Credentials Binding、Allure Jenkins Plugin；
- Allure Jenkins Plugin 中已配置一个 Allure Commandline 工具。

Jenkinsfile 会自行创建工作区下的 `.venv` 并安装 `requirements.txt`，不需要
在节点全局安装 pytest 或数据库驱动。

## 必须创建的凭据

为每个环境创建一个 **Secret file** 类型凭据，凭据 ID 必须为：

```text
interface-test-test-config
interface-test-hk-config
interface-test-prod-config
```

凭据文件内容是对应的本地环境覆盖 JSON。不要在凭据文件中放进 Git。下面是
`interface-test-test-config` 的示例：

```json
{
  "http": {
    "base_url": "https://test-api.company.internal",
    "headers": {
      "Authorization": "Bearer real-token"
    }
  },
  "rpc": {
    "endpoint": "https://test-rpc.company.internal/jsonrpc"
  },
  "databases": {
    "mysql": {
      "host": "mysql.internal",
      "user": "tester",
      "password": "secret",
      "database": "app"
    }
  }
}
```

构建时该文件只会临时复制为
`config/environment.<TEST_ENV>.local.json`，测试结束后通过 shell trap 删除。

## 构建参数

| 参数 | 含义 |
| --- | --- |
| `TEST_ENV` | 选择 `test`、`hk` 或 `prod`，同时决定配置与 `*.环境.json` case 文件。 |
| `CASE_FILTER` | 可选 pytest `-k` 表达式，例如 `get_user`。留空运行该环境全部启用 case。 |
| `USE_CONFIG_CREDENTIAL` | 默认开启。关闭时不注入凭据，只适合不需要真实环境配置的框架自测。 |

## 构建产物

- `artifacts/junit.xml`：Jenkins Tests 页面显示的 pytest 结果；
- `allure-results/`：原始 Allure 结果，始终归档；
- Allure Jenkins Plugin 生成的构建报告：在构建页面的 Allure Report 入口查看。

当新增环境时，需要同时完成四件事：新增 `config/environment.<env>.json`、新增
`*.<env>.json` case 文件、创建 `interface-test-<env>-config` Secret file 凭据，
并将该环境加入 Jenkinsfile 的 `TEST_ENV` choices。
