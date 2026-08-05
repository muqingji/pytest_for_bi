# 从零手写框架学习路线

这份文档不是 API 手册，而是一条复写路线。目标是你在另一个空目录中，
不复制本项目代码，也能自己搭出一套可运行的 pytest 接口自动化框架。

建议每完成一个阶段就运行一次测试。不要一开始就写 HTTP、RPC、数据库和
IDL 生成器，这会让问题无法定位。先完成最小 HTTP 用例闭环，再逐层扩展。

## 先跑一次

```bash
source .venv/bin/activate
make test
make allure
```

测试入口是 `tests/test_api_cases.py`。示例业务用例默认禁用，因此测试通过
不代表会调用外部服务。运行结果会写到 `allure-results/`，HTML 报告在
`allure-report/`。

## 目录结构

```text
.
├── pyproject.toml                 # Python 依赖、pytest 配置、src 包发现规则
├── Makefile                       # 安装、执行测试、生成 Allure 报告的快捷命令
├── config/
│   ├── environment.test.json      # 测试环境模板
│   ├── environment.hk.json        # 香港环境模板
│   └── environment.prod.json      # 线上环境模板
├── test_data/
│   ├── demo.test.json             # 示例用例，文件后缀就是环境标识
│   ├── demo.prod.json
│   └── templates/                 # 新 case 的复制模板，不会被 pytest 收集
├── idl/                           # 输入的 Thrift / Proto IDL
├── scripts/
│   └── sync_idl.py                # 根据 IDL 增量生成 RPC API 方法
├── src/framework/
│   ├── clients/                   # HTTP、RPC、数据库等基础客户端
│   ├── config/                    # 环境配置、环境变量替换、case 文件加载
│   ├── core/                      # 断言与 data-driven 步骤执行器
│   ├── adapters/                  # 原生 RPC 传输适配器，例如 Thrift
│   └── api/generated/             # 脚本生成的 API 类，禁止手改
└── tests/                         # 框架自身单元测试和唯一的通用用例入口
```

以下文件不是框架业务代码：`.venv/`、`.pytest_cache/`、`allure-results/`、
`allure-report/`、`__pycache__/` 和 `*.egg-info/`。复写时不要参考或提交它们。

## 先理解一次执行流

```text
pytest
  -> tests/conftest.py: pytest_generate_tests
  -> 读取 test_data/**/*.当前环境.json
  -> tests/test_api_cases.py: 通用测试函数
  -> CaseRunner.run(case)
  -> 每个 step 根据 protocol 调用 HTTP / RPC / DB 客户端
  -> extract 提取变量，expect 调用通用断言
  -> allure 记录步骤和响应
```

你需要抓住一个边界：`test_data` 只描述“测什么”，`src/framework` 只负责
“怎样执行”。业务接口地址、参数和断言不能写死在 Python 测试函数里。

## 推荐阅读与复写顺序

### 第 1 步：工程最小骨架

先看 `pyproject.toml`、`Makefile` 和 `tests/test_assertions.py`。

自己创建一个新项目时，只做这些事情：

1. 用 `src` 布局创建 `src/framework` 和 `tests`。
2. 在 `pyproject.toml` 声明 `pytest`、`httpx`、`allure-pytest`。
3. 配置 pytest 的 `testpaths = ["tests"]` 和 `pythonpath = ["src"]`。
4. 写一个普通断言测试，确认 `pytest` 能找到测试。

完成标准：执行 `python -m pytest` 至少有一条通过。

### 第 2 步：统一响应对象和 HTTP 客户端

按顺序读：

1. `src/framework/clients/models.py`
2. `src/framework/clients/http.py`
3. `tests/test_runner.py` 里的 `FakeHttpClient`

先写 `ApiResponse`，统一保存 `status_code`、`body`、`headers`、耗时和原始文本。
然后写一个只有 `request(method, path_or_url, ...)` 的 `HttpClient`。`get`、`post`
等方法只应调用 `request`，不要在每个方法重复发送逻辑。

完成标准：传入假客户端时，调用层只依赖 `ApiResponse`，而不依赖 `httpx.Response`。
这样以后 RPC 与数据库查询也可以共用断言。

### 第 3 步：通用断言

按顺序读：

1. `src/framework/core/assertions.py`
2. `tests/test_assertions.py`

建议自己先实现三个能力：

1. `status_code` 相等。
2. `body` 的递归部分匹配，例如期望 `{ "code": 0 }` 不要求响应没有其他字段。
3. `json_path` 取值，例如 `data.users[0].name`。

之后再增加轻量 schema 校验。不要一开始接入完整 JSON Schema 库；先把框架
自己的断言输入格式设计稳定。

完成标准：失败信息能指出具体路径，例如 `body.data.id: expected 1, got 2`。

### 第 4 步：环境配置和数据文件加载

按顺序读：

1. `config/environment.test.json`
2. `src/framework/config/environment.py`
3. `tests/test_data_loader.py`
4. `test_data/demo.test.json`

先只实现 `environment.<env>.json` 和 `*.{env}.json` 的约定。核心函数是：

```python
EnvironmentConfig.load("test")
load_cases("test")
```

再实现本项目已有的两个增强：

- `${TEST_HTTP_BASE_URL}` 环境变量替换；
- `environment.test.local.json` 的深度覆盖，且把它加入 `.gitignore`。

不要把真实 Token、密码和线上地址提交到 `environment.test.json`。模板文件只放
变量名，个人或 CI 的真实值通过环境变量或本地覆盖文件提供。

完成标准：`TEST_ENV=prod` 时只读取 `environment.prod.json` 和 `*.prod.json`。

### 第 5 步：pytest 收集和单一测试入口

按顺序读：

1. `tests/conftest.py`
2. `tests/test_api_cases.py`

重点理解 `pytest_generate_tests`：它在收集阶段把 JSON 中的每个 case 参数化为
一次 pytest 测试。业务测试函数只有一个，不能为每个接口创建 Python 测试文件。

手写时先支持：
gitgit git pull git add .git commit -m ''重新chongxin t重新chongxin ss重新‘啊git push
```python
pytest.param(case, id=case["id"])
```

然后再支持 `tags` 转 pytest marker，及 `enabled: false` 跳过。务必让环境名同时
用于配置加载和 case 加载。本项目之前最容易犯的错误就是只让其中一处读取
`TEST_ENV`。

完成标准：新建一个 JSON case 后，无需新建 Python 文件，`pytest --collect-only`
即可看到它的 `id`。

### 第 6 步：步骤执行器

按顺序读：

1. `src/framework/core/runner.py`
2. `tests/test_runner.py`
3. `test_data/demo.test.json`

这是整个框架最重要的文件。先实现下面最小规则：

```text
case.variables 初始化上下文
for step in case.steps:
    解析 {{ variable }}
    发送 HTTP 请求
    extract 响应字段到上下文
    expect 调用通用断言
```

模板替换建议支持两种情况：整个字符串是 `{{ token }}` 时保留原来的类型；
`Bearer {{ token }}` 这类拼接则转换为字符串。实现后再在每个 step 外加
`allure.step(step_name)` 和响应附件。

完成标准：一个登录 step 提取 token，第二个 step 能在请求头或参数中使用它。

### 第 7 步：数据库和 RPC

按顺序读：

1. `src/framework/clients/database.py`
2. `src/framework/clients/rpc.py`
3. `src/framework/adapters/thrift.py`
4. `tests/test_rpc_adapter.py`

数据库层的关键是只提供 `query(name, sql, parameters)` 与 `execute(...)` 两个通用
入口，根据配置中的 `engine` 分流到 MySQL 或 ClickHouse。驱动包应该延迟导入，
这样只跑 HTTP case 时不会因数据库驱动问题失败。

RPC 层的关键是只有一个 `call(service, method, params)`。默认 JSON-RPC 只是一种
transport；Thrift/Kitex/gRPC 应该通过 adapter 接入，而不是把业务 RPC 逻辑塞进
步骤执行器。

完成标准：`CaseRunner` 不知道 RPC 使用的是 JSON-RPC 还是 Thrift。

### 第 8 步：IDL 代码生成

最后再读：

1. `idl/example.thrift`
2. `scripts/sync_idl.py`
3. `src/framework/api/generated/example_user_service_api.py`
4. `tests/test_idl_sync.py`

先只支持 Thrift 的 `service` 和方法名解析。每个 service 生成一个 `XxxApi` 类，
每个 IDL 方法生成一个同名 Python 方法，方法内部只调用 `RpcClient.call(...)`。

增量同步的判断应该基于“当前目标文件内容与本次生成内容是否相同”。相同则不写入，
避免 IDL 未变化时产生 Git 噪音。对于从 IDL 删除的 service，不要自动删除旧文件；
让维护者在迁移确认后手动删除更安全。

完成标准：连续运行两次 `python scripts/sync_idl.py --idl-dir idl`，第二次显示
`unchanged`。

## 复写时的最小里程碑

按下面顺序提交自己的代码，每一步都保持可运行：

1. pytest 可以运行一个普通单测。
2. HTTP 客户端返回统一 `ApiResponse`。
3. JSON case 被加载并参数化为 pytest case。
4. 单个 HTTP step 支持 `expect.status_code`。
5. 支持 `variables`、`extract` 与多 step 串联。
6. 增加 Allure step 和 response 附件。
7. 支持多环境文件、环境变量和本地覆盖文件。
8. 增加数据库、RPC adapter。
9. 最后实现 IDL 同步。

## 写第一个真实 Case

1. 在 `config/environment.test.local.json` 填写测试环境的真实地址和鉴权信息。
2. 复制 `test_data/templates/http_case.template.json` 为
   `test_data/user/get_user.test.json`。
3. 替换 `id`、`path`、参数和 `expect`；将 `enabled` 设为 `true`。
4. 执行：

```bash
source .venv/bin/activate
python -m pytest --env=test --alluredir=allure-results -k get_user
allure generate allure-results -o allure-report --clean
```

出现失败时，先看 Allure 中对应 step 的 `response` 附件，再修改 JSON 断言；不要
直接在 `CaseRunner` 里为某个业务接口加特殊分支。

## 复写时先不要做的事

- 不要先支持 async、并发、重试、签名、加解密和复杂插件体系。
- 不要在 JSON 中写 Python 表达式或 `eval`。
- 不要把一个具体业务接口封装进 `HttpClient`。
- 不要编辑 `src/framework/api/generated/` 下的生成方法。
- 不要把密码、Cookie、Token 放进 Git 跟踪的环境文件或 case 文件。

这些能力应在最小闭环稳定后，以独立模块或 adapter 的方式逐步加入。
