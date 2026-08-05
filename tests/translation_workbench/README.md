# 翻译工作台测试主体说明

本文说明 `test_translation_language.py` 的职责、数据来源、执行流程和当前断言范围。

## 1. 文件职责

`test_translation_language.py` 是翻译工作台专项测试的流程调度器，不直接保存具体接口请求和预期结果。

各层职责如下：

| 层级 | 文件 | 职责 |
| --- | --- | --- |
| 测试主体 | `test_translation_language.py` | 组合个人语言与翻译语言，切换登录语言，循环执行翻译 Case |
| 工作台 Case | `../../test_data/translation_workbench.112.json` | 定义 12 条工作台明细请求及目标 `translateKey` |
| 分类 Case | `../../test_data/translation_workbench_classification.112.json` | 定义 16 条分类路径请求及目标 `translateKey` |
| 语言切换 Case | `../../test_data/pass_api.112.json` | 定义个人语言切换成中文和英文的接口请求 |
| 公共 fixture | `../conftest.py` | 创建环境配置、HTTP 客户端、登录会话和 `CaseRunner` |
| Case 执行器 | `../../src/framework/core/runner.py` | 发送请求、遍历分类、展开文件夹并执行响应断言 |

整体执行关系：

```text
pytest
  |
  +-- case_runner fixture
  |     +-- 加载 112 环境配置
  |     +-- 创建 HTTP 客户端
  |     +-- 登录纷享销客
  |     +-- 加载 HTTP API 目录
  |
  +-- translation_language_cases fixture
  |     +-- 2 条个人语言切换 Case
  |     +-- 12 条工作台明细 Case
  |     +-- 16 条工作台分类 Case
  |
  +-- 主体一：个人中文，翻译中文
  +-- 主体二：个人中文，翻译英文
  +-- 主体三：个人英文，翻译中文
  +-- 主体四：个人英文，翻译英文
```

每个主体都会执行全部 28 条翻译 Case，因此一轮完整测试包含 `4 x 28 = 112` 次翻译 Case 执行。每条 Case 内部可能产生多次分类和词条查询，所以实际 HTTP 请求数大于 112。

该专项必须串行执行。四个主体会依次修改同一个账号的个人语言，并共享同一个登录会话；
并行执行会造成语言状态互相覆盖。Makefile 和 Jenkins 均显式使用 `pytest -n 0`，专项
fixture 也会拒绝在 xdist worker 中运行。

## 2. 基础常量

```python
_WORKFLOW = "translation_language"
_LANGUAGE_LABELS = {"zh-CN": "中文", "en": "英文"}
```

`_WORKFLOW` 用于从所有 112 环境数据中筛选翻译工作台专项 Case。

`_LANGUAGE_LABELS` 用于生成可读的 Allure 步骤和失败信息，不参与接口参数判断。

## 3. Case 加载 fixture

```python
@pytest.fixture(scope="session")
def translation_language_cases(pytestconfig: pytest.Config) -> dict[str, Any]:
```

该 fixture 在整个 pytest 会话中只执行一次。

### 3.1 确定运行环境

环境读取顺序为：

1. pytest 命令行参数 `--env`。
2. 环境变量 `TEST_ENV`。
3. 默认值 `test`。

翻译工作台专项当前只允许在 `112` 环境运行。其他环境会调用 `pytest.skip()`，不会发送接口请求。

### 3.2 加载并筛选 Case

```python
cases = [
    case
    for case in load_cases(environment)
    if case.get("workflow") == "translation_language"
]
```

`load_cases("112")` 会递归读取 `test_data` 下所有以 `.112.json` 结尾的文件，并为每条 Case 补充 `workflow` 和 `__source__` 等运行信息。

加载后的 Case 被分成两组：

```json
{
    "switches": {
        "zh-CN": "切换个人语言为中文的 Case",
        "en": "切换个人语言为英文的 Case"
    },
    "translations": [
        "12 条工作台明细 Case",
        "16 条分类 Case"
    ]
}
```

`switches` 根据语言切换请求中的 `language` 字段建立索引。

`translations` 根据 `__source__` 的文件名筛选。文件名以 `translation_workbench` 开头即可被选中，因此当前两个翻译数据文件都会进入该列表。

fixture 会检查：

- 必须同时存在 `zh-CN` 和 `en` 两条个人语言切换 Case。
- 必须至少加载到一条翻译工作台 Case。

任一条件不满足都会在测试开始前直接失败。

## 4. Allure 兼容包装

```python
def _allure_step(name: str):
    return allure.step(name) if allure else nullcontext()
```

安装 Allure 时，该函数创建报告步骤；未安装 Allure 时，使用空上下文继续执行，不让报告依赖阻塞普通 pytest 测试。

`_allure_title()` 使用相同思路：安装 Allure 时设置测试标题，否则返回原测试函数。

## 5. 设置目标翻译语言

```python
def _case_for_translation_language(case, translation_language):
```

这个函数根据当前测试主体修改 Case 中的目标语言。

第一步是深拷贝：

```python
prepared = deepcopy(case)
```

同一条原始 Case 会被四个主体重复使用。使用深拷贝可以避免主体一修改语言后污染主体二、主体三和主体四。

随后函数遍历 Case 的全部步骤，同时兼容两种请求体格式：

```python
request["body"]["language"]
request["json"]["language"]
```

分类接口可能把语言放在 `argMap` 中，因此还会更新：

```python
body["argMap"]["language"]
```

该函数只修改复制后的 Case，不修改 JSON 加载得到的原始对象。

## 6. 执行一个语言主体

```python
def _run_language_subject(
    case_runner,
    workflow_cases,
    personal_language,
    translation_language,
):
```

这里有两个独立概念：

| 参数 | 含义 | 示例 |
| --- | --- | --- |
| `personal_language` | 当前登录用户的个人语言 | `zh-CN` |
| `translation_language` | 翻译工作台本次查询使用的目标语言 | `en` |

个人语言为中文，不代表只能查询中文翻译；这两个维度需要独立组合验证。

### 6.1 切换个人语言

```python
case_runner.run(workflow_cases["switches"][personal_language])
```

该调用执行 `pass_api.112.json` 中对应的个人语言切换 Case。

语言切换请求会复用切换前的 `lang` Cookie，并按照页面请求补充 `Accept-Language`、`Origin`、`Referer`、`traceId` 和 `X-Trace-Id`。认证 Cookie 和 `_fs_token` 仍来自自动登录会话，不在测试数据中保存。

接口返回切换成功后，将 `lang` Cookie 更新为目标个人语言，再固定等待 5 秒，让个人语言设置在后端完成同步。等待结束后才会执行该主体下的 28 条翻译 Case：

```python
case_runner.run(workflow_cases["switches"][personal_language])
case_runner.http_client.set_cookie("lang", personal_language)
case_runner.http_client.default_headers["Accept-Language"] = personal_language_header
sleep(5)
```

目标个人语言会同时同步到后续分类查询和 `sub_query_optimize` 请求的 `Accept-Language`。该请求头直接影响响应中的 `headerFields` 和 `needTransName`，不能只修改 Cookie。

每个测试主体只切换一次个人语言。主体一至主体四各自在开始时执行一次切换和等待，同一主体下的 28 条翻译 Case 共用已经生效的个人语言环境。

语言切换后不会重新登录，避免新登录会话覆盖刚刚切换的个人语言上下文。

### 6.2 执行全部翻译 Case

```python
for case in workflow_cases["translations"]:
    prepared_case = _case_for_translation_language(case, translation_language)
    case_runner.run(prepared_case)
```

`case_runner` 由父目录 `conftest.py` 自动注入。测试函数只要声明同名参数，pytest 就会创建并传入该 fixture。

`CaseRunner.run()` 负责：

1. 解析 Case 变量和请求模板。
2. 根据 BI 对象逐级查询分类选项。
3. 查询文件夹或最终词条列表。
4. 必要时展开目标文件夹。
5. 查询最终翻译词条。
6. 执行 Case 中配置的响应断言。

## 7. 失败收集策略

每条翻译 Case 都在独立的 `try/except` 中运行：

```python
try:
    case_runner.run(prepared_case)
except Exception as error:
    failures.append(f"{case_name}: {error}")
```

这种设计不会在第一条失败时终止整个主体，而是继续执行剩余 Case。全部执行结束后，再统一抛出汇总异常，例如：

```text
个人语言为中文、翻译成英文时，3/28 条翻译 case 未通过：
  1. 图表配置-报表列表-统计图: ...
  2. 目标-目标名称: ...
  3. 数据驾驶舱-数据驾驶舱名称: ...
```

这样一次报告可以展示该语言组合下的全部失败项。

## 8. 四个 pytest 测试主体

文件底部的四个函数只是四种语言组合的显式入口：

| 测试主体 | `personal_language` | `translation_language` |
| --- | --- | --- |
| 主体一 | `zh-CN` | `zh-CN` |
| 主体二 | `zh-CN` | `en` |
| 主体三 | `en` | `zh-CN` |
| 主体四 | `en` | `en` |

四个函数的公共逻辑全部由 `_run_language_subject()` 实现。分别声明四个测试函数，是为了让 pytest 和 Allure 将它们展示成四个独立测试主体。

## 9. 当前断言范围

每条翻译 Case 显式配置以下基础断言：

- HTTP 状态码必须是 `200`。
- 响应中必须包含该场景指定的精确 `translateKey`。

执行器还会检查分类选项、目标行唯一性、JSON 格式、`dataRowsAll` 结构，以及部分内部请求的业务状态。

测试主体会对命中词条的最终结果执行语言断言：

- `query_optimize.dataRowsAll[]` 返回可展开文件夹行时，文件夹的 `needTransName` 按当前个人语言断言。
- `sub_query_optimize.dataRowsAll[].needTransName` 是原始“名称”，只按当前个人语言断言。
- `sub_query_optimize.dataRowsAll[].translateValue` 是翻译后的“名称翻译”，只按请求中的目标翻译语言断言。

| 个人语言 | 目标翻译语言 | 文件夹 `needTransName` | 名称 `needTransName` | 名称翻译 `translateValue` |
| --- | --- | --- | --- | --- |
| 英文 | 英文 | 英文 | 英文 | 英文 |
| 英文 | 中文 | 英文 | 英文 | 中文 |
| 中文 | 英文 | 中文 | 中文 | 英文 |
| 中文 | 中文 | 中文 | 中文 | 中文 |

`translateValue` 同时兼容行顶层字段和 `returnRowUdef.translateValue`。字段缺失、空字符串或语言不匹配都会导致该条 Case 失败。

文件夹断言只检查 `query_optimize` 接口中实际返回并命中的可展开文件夹行。如果接口列表中
没有返回目标文件夹，执行器仍可使用 Case 配置的 `rowKey` 和 `rowKeyLabel` 继续查询最终词条，
但静态 `rowKeyLabel` 只用于构造请求和展示路径，不会冒充接口返回的文件夹名参与语言断言。

当前尚未检查：

- `translateValue` 的具体翻译语义是否正确。
- 翻译内容的保存、修改和同步流程。

因此当前测试会验证：指定语言组合下分类查询链路可用、能够找到预期翻译词条，并且接口
实际返回的文件夹名称、最终名称符合个人语言，名称翻译符合目标翻译语言。

## 10. 运行方式

只收集测试主体，不发送接口请求：

```bash
PYTHONPATH=.:src .venv/bin/pytest --collect-only -q \
  -n 0 --env=112 tests/translation_workbench/test_translation_language.py
```

执行翻译工作台专项：

```bash
make interface-test
```

执行专项并生成文本报告：

```bash
make interface-report
```

不重新请求接口，重新生成并查看最近一次可读摘要：

```bash
make print-interface-report
```

默认摘要保存在 `reports/interface-automation/report.txt`，按语言场景列出每条翻译
路径 Case 的通过/失败状态，并将文件夹名称、最终名称和名称翻译的检查结果转换成期望语言、
实际值和识别语言。有分组的词条会在 Case 路径后追加“分组 > 名称”，平铺词条则只
追加“名称”。只有接口实际返回分组行时，报告中才会额外出现“分组名称”断言结果。

需要排查原始请求和响应时再生成详细附录：

```bash
make print-interface-report-details
```

详细附录保存在 `reports/interface-automation/report-details.txt`，其中敏感字段会被脱敏。

专项需要有效的 112 环境登录配置。认证信息应通过环境变量或被忽略的 `config/environment.112.local.json` 提供，不应写入测试代码或 Case 文件。
