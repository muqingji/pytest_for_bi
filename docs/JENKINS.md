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

Pipeline 会先运行不依赖外部环境和凭据的离线质量门禁，包括基础测试框架和
`qa-agents` 子系统的完整单元测试。两套测试全部通过后，才会进入目标环境接口测试。

## 必须创建的凭据

为每个环境创建一个 **Secret file** 类型凭据，凭据 ID 必须为：

```text
interface-test-test-config
interface-test-hk-config
interface-test-prod-config
interface-test-112-config
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

`interface-test-112-config` 用于翻译工作台专项，至少需要提供 112 环境的
`auth.enterprise_account`、`auth.username` 和 `auth.password`。示例：

```json
{
  "auth": {
    "enterprise_account": "your-enterprise-account",
    "username": "your-username",
    "password": "your-password"
  }
}
```

## 构建参数

| 参数 | 含义 |
| --- | --- |
| `TEST_ENV` | 选择 `112`、`test`、`hk` 或 `prod`。选择 `112` 时只执行翻译工作台专项。 |
| `CASE_FILTER` | 可选 pytest `-k` 表达式，例如 `get_user`。留空运行该环境全部启用 case。 |
| `USE_CONFIG_CREDENTIAL` | 默认开启。关闭时不注入凭据，只适合不需要真实环境配置的框架自测。 |

## 构建产物

- `artifacts/framework-junit.xml`：基础测试框架的离线测试结果；
- `artifacts/qa-agents-junit.xml`：质量编排系统的离线测试结果；
- `artifacts/interface-junit.xml`：目标环境接口测试结果；
- `artifacts/interface-report.txt`：可在 Jenkins 构建产物中直接下载的详细文本报告；
- `allure-results/`：原始 Allure 结果，始终归档；
- Allure Jenkins Plugin 生成的构建报告：在构建页面的 Allure Report 入口查看。

## 远端查看翻译工作台报告

1. 在 Jenkins Credentials 中创建 Secret file，ID 为 `interface-test-112-config`。
2. 创建或更新指向本仓库 `Jenkinsfile` 的 Pipeline/Multibranch Pipeline Job。
3. 触发参数化构建，`TEST_ENV` 选择 `112`。
4. 构建完成后，在构建页面点击 **Allure Report** 查看完整的远端报告。
5. 需要纯文本时，打开 **Build Artifacts**，下载 `artifacts/interface-report.txt`。

对应 URL 通常为：

```text
${JENKINS_URL}/job/<job-name>/<build-number>/allure/
${JENKINS_URL}/job/<job-name>/<build-number>/artifact/artifacts/interface-report.txt
```

Multibranch Pipeline 会在 URL 中增加分支层级，以构建页面实际生成的链接为准。

语言断言失败不会阻止报告发布。Jenkins 构建状态会保持失败，以便持续集成正确告警，
但 Allure 页面、JUnit 结果和文本报告仍会在 `post { always { ... } }` 中生成。

当新增环境时，需要同时完成四件事：新增 `config/environment.<env>.json`、新增
`*.<env>.json` case 文件、创建 `interface-test-<env>-config` Secret file 凭据，
并将该环境加入 Jenkinsfile 的 `TEST_ENV` choices。
