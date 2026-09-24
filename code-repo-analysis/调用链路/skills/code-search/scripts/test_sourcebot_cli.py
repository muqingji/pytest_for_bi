"""sourcebot-cli 的行为测试（不依赖真实 Sourcebot 服务）。

覆盖（按 skill-scripts.md §10）：
- `-h` 含 Examples
- 缓存命中：第二次调用不打 MCP（mock session.calls == 1）
- 证据落盘：完整内容、唯一文件名、index.md 行完整
- compact 不破坏源码缩进（回归 S2）
- list-tree 的 --no-include-files / --no-include-dirs 真正生效（回归 S1）
- get_token 优先级与 .env.local 解析（回归 P8）
- 会话过期重试覆盖 401/403（回归 P5）

注：CLI 文件名是 `sourcebot-cli.py`（带连字符），不是合法 Python 模块名，
故用 importlib spec 从路径加载，避免重命名这个被 SKILL 文档广泛引用的入口名。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

# repo root: .../code-search/scripts -> parents[4]
REPO_ROOT = Path(__file__).resolve().parents[4]
CODE_SEARCH_DIR = Path(__file__).resolve().parents[1]
CLI_PATH = Path(__file__).resolve().parent / "sourcebot-cli.py"

_spec = importlib.util.spec_from_file_location("sourcebot_cli", CLI_PATH)
assert _spec is not None and _spec.loader is not None
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)


# ─── fixtures ────────────────────────────────────────────────────────────────


class FakeSession:
    """记录调用次数与返回值的假 McpSession，避免真实网络。"""

    def __init__(self, response: dict):
        self.response = response
        self.calls: list[tuple[str, dict | None]] = []

    def call(self, method: str, params: dict | None = None) -> dict:
        self.calls.append((method, params))
        return self.response


@pytest.fixture()
def isolated_cache(tmp_path, monkeypatch):
    """每个测试用独立缓存目录，避免相互污染或读取真实缓存。"""
    monkeypatch.setattr(cli, "CACHE_DIR", tmp_path / "sb-cache")
    return tmp_path


# ─── -h / Examples ───────────────────────────────────────────────────────────


def test_help_includes_examples() -> None:
    """-h 必须含 Examples 段（skill-scripts.md §6 硬性要求）。"""
    result = subprocess.run(
        [sys.executable, str(CLI_PATH), "-h"],
        capture_output=True,
        text=True,
        cwd=CODE_SEARCH_DIR,
    )
    assert result.returncode == 0
    assert "示例:" in result.stdout
    assert "sourcebot-cli.py grep" in result.stdout
    assert "--evidence-dir" in result.stdout


# ─── S1: BooleanOptionalAction regression ─────────────────────────────────────


def test_list_tree_no_include_flags_actually_disable() -> None:
    """回归 S1：--no-include-files / --no-include-dirs 必须真正关掉对应输出。

    旧的 type=bool 实现里 bool('false')==True，开关永久失效。
    """
    parser = cli.build_parser()
    args = parser.parse_args(["list-tree", "--repo", "r", "--no-include-files", "--no-include-dirs"])
    assert args.include_files is False
    assert args.include_dirs is False

    # 默认值仍是 True（向后兼容）
    default = parser.parse_args(["list-tree", "--repo", "r"])
    assert default.include_files is True
    assert default.include_dirs is True


# ─── S2: compact preserves indentation regression ────────────────────────────


def test_compact_preserves_source_indentation() -> None:
    """回归 S2：compact 不能删行首缩进，否则 Python/YAML 源码被破坏。"""
    src = (
        "    if order is None:\n"
        '        raise ValueError("x")\n'
        "\n"  # 空行应被删
        "    return order.id\n"
    )
    result = {"result": {"content": [{"type": "text", "text": src}]}}
    out = cli._format_compact(result)
    assert "    if order is None:" in out, "顶层缩进被破坏"
    assert '        raise ValueError("x")' in out, "嵌套缩进被破坏"
    assert "\n\n" not in out, "空行未被删除"


def test_compact_json_passthrough() -> None:
    """JSON 输出原样返回，不被压缩。"""
    result = {"result": {"content": [{"type": "text", "text": '{"a": 1, "b": 2}'}]}}
    out = cli._format_compact(result)
    assert json.loads(out) == {"a": 1, "b": 2}


# ─── cache hit (reuse path) ──────────────────────────────────────────────────


def _text_response(text: str) -> dict:
    return {"result": {"content": [{"type": "text", "text": text}]}}


def test_grep_cache_hit_no_second_call(isolated_cache, tmp_path) -> None:
    """第二次 grep 命中缓存，不再打 MCP（calls==1）。"""
    fake = FakeSession(_text_response("hit1"))
    args = cli.build_parser().parse_args(["grep", "--repo", "r", "--pattern", "NPE", "--compact"])
    cli.cmd_grep(fake, args)
    cli.cmd_grep(fake, args)
    assert len(fake.calls) == 1, "第二次 grep 应命中缓存而不调用 MCP"


def test_no_cache_bypasses_cache(isolated_cache) -> None:
    """--no-cache 时每次都打 MCP。"""
    fake = FakeSession(_text_response("hit"))
    args = cli.build_parser().parse_args(["grep", "--repo", "r", "--pattern", "NPE", "--no-cache"])
    cli.cmd_grep(fake, args)
    cli.cmd_grep(fake, args)
    assert len(fake.calls) == 2


def test_diff_is_cached(isolated_cache) -> None:
    """回归 S7：diff 现在也走缓存（确定性查询）。"""
    fake = FakeSession(_text_response("diff body"))
    args = cli.build_parser().parse_args(["diff", "--repo", "r", "--base", "a", "--head", "b"])
    cli.cmd_diff(fake, args)
    cli.cmd_diff(fake, args)
    assert len(fake.calls) == 1


# ─── P1: evidence stores FULL content ────────────────────────────────────────


def test_evidence_stores_full_content_not_truncated(isolated_cache, tmp_path) -> None:
    """回归 P1：证据文件必须存完整内容，不能截断为 2KB 预览。

    read-file 单次最多 5KB，截断会让 fx-ops converge 阶段无法引用而不重读。
    """
    big = "x" * 5000  # 远超旧的 2KB 预览上限
    ev_root = tmp_path / "ev"
    ev_path = cli.write_evidence(
        str(ev_root),
        {"tool": "read-file", "content": big},
        kind="SRC-code-snippet",
    )
    assert ev_path is not None
    assert ev_path.parent == ev_root / "evidence"
    data = json.loads(ev_path.read_text(encoding="utf-8"))
    assert data["data"]["content"] == big, "内容被截断"
    assert len(data["data"]["content"]) == 5000
    index = (ev_root / "index.md").read_text(encoding="utf-8")
    assert f"`evidence/{ev_path.name}`" in index


def test_output_result_for_read_file_writes_structured_code_snippet(isolated_cache, tmp_path, capsys) -> None:
    """read-file 落盘时必须额外产出结构化 SRC-code-snippet 供 fx-ops converge 直接消费。"""
    args = cli.build_parser().parse_args(
        [
            "read-file",
            "--repo",
            "AppServer/fs-fmcg",
            "--path",
            "src/main/java/com/example/OrderService.java",
            "--offset",
            "130",
            "--limit",
            "3",
            "--evidence-dir",
            str(tmp_path / "ev"),
        ]
    )
    result = {
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": "if (order == null) {\n    throw new NullPointerException();\n}\n",
                }
            ]
        }
    }

    cli.output_result(result, args)
    captured = capsys.readouterr()
    assert "if (order == null)" in captured.out

    ev_dir = tmp_path / "ev"
    snippet_files = sorted((ev_dir / "evidence").glob("SRC-code-snippet-*.json"))
    search_files = sorted((ev_dir / "evidence").glob("SRC-search-result-*.json"))
    assert len(snippet_files) == 1, "缺少结构化源码片段证据"
    assert len(search_files) == 1, "通用搜索证据不应丢失"

    snippet = json.loads(snippet_files[0].read_text(encoding="utf-8"))
    assert snippet["data"] == {
        "repo": "AppServer/fs-fmcg",
        "filePath": "src/main/java/com/example/OrderService.java",
        "lineStart": 130,
        "lineEnd": 132,
        "highlightedLines": [130],
        "context": "if (order == null) {\n    throw new NullPointerException();\n}\n",
    }


# ─── P2: unique filenames under concurrency ───────────────────────────────────


def test_evidence_filenames_unique_within_same_second(isolated_cache, tmp_path) -> None:
    """回归 P2：同一秒内多次写证据不能覆写（fx-ops 并行派子 agent）。

    旧的秒级时间戳文件名会在并发下覆写、静默丢证据。
    """
    ev_dir = tmp_path / "ev"
    names = set()
    for _ in range(30):
        f = cli.write_evidence(str(ev_dir), {"content": "x"}, "SRC-search-result")
        names.add(f.name)
        assert f.parent == ev_dir / "evidence"
    assert len(names) == 30, "文件名发生碰撞"


# ─── P3: index.md lines intact ───────────────────────────────────────────────


def test_index_md_keeps_all_lines(isolated_cache, tmp_path) -> None:
    """回归 P3：多次写证据后 index.md 行数完整、格式一致。

    旧的非原子 append 在并发下会交错；现改为 read-modify-write + os.replace。
    """
    ev_dir = tmp_path / "ev"
    for i in range(5):
        cli.write_evidence(str(ev_dir), {"content": f"hit{i}"}, "SRC-search-result")
    index = (ev_dir / "index.md").read_text(encoding="utf-8")
    lines = [ln for ln in index.splitlines() if ln.strip()]
    assert len(lines) == 5
    for ln in lines:
        assert ln.startswith("- `evidence/SRC-search-result-") and ln.endswith(" bytes)"), ln


def test_explicit_evidence_subdir_updates_parent_index(isolated_cache, tmp_path) -> None:
    """如果传入的已经是 .../evidence 子目录，文件写子目录本身，但 index 仍更新父目录。"""
    ev_root = tmp_path / "run"
    ev_subdir = ev_root / "evidence"
    ev_subdir.mkdir(parents=True)

    f = cli.write_evidence(str(ev_subdir), {"content": "x"}, "SRC-search-result")
    assert f is not None
    assert f.parent == ev_subdir

    index = (ev_root / "index.md").read_text(encoding="utf-8")
    assert f"`evidence/{f.name}`" in index


# ─── P8: token resolution priority + .env.local parsing ──────────────────────


def test_token_env_var_beats_env_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SOURCEBOT_API_KEY", "from_env")
    monkeypatch.delenv("SOURCEBOT_ACCESS_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.local").write_text("SOURCEBOT_API_KEY=from_file\n", encoding="utf-8")
    assert cli.get_token() == "from_env"


def test_token_priority_api_key_over_access_token_in_env_file(monkeypatch, tmp_path) -> None:
    """回归 P8：.env.local 里两个 key 都在时，按优先级返回（不受文件行序影响）。"""
    monkeypatch.delenv("SOURCEBOT_API_KEY", raising=False)
    monkeypatch.delenv("SOURCEBOT_ACCESS_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    # ACCESS_TOKEN 在文件中靠前 —— 旧实现会错误地先返回它
    (tmp_path / ".env.local").write_text(
        'export SOURCEBOT_ACCESS_TOKEN="tok_abc"\nSOURCEBOT_API_KEY=tok_xyz # inline comment\n',
        encoding="utf-8",
    )
    assert cli.get_token() == "tok_xyz"


def test_token_tolerates_export_prefix_and_inline_comment(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("SOURCEBOT_API_KEY", raising=False)
    monkeypatch.delenv("SOURCEBOT_ACCESS_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.local").write_text('export SOURCEBOT_ACCESS_TOKEN="tok_q"\n', encoding="utf-8")
    assert cli.get_token() == "tok_q"


# ─── P5: session-expiry retry covers 401/403 ─────────────────────────────────


def test_session_retry_on_401(monkeypatch) -> None:
    """回归 P5：旧的只在 HTTP 400 重试；401（token/session 过期）也必须重试。"""
    import urllib.error

    sess = cli.McpSession(token="t")
    sess.session_id = "stale"

    call_count = {"n": 0}

    def fake_urlopen(req, timeout=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

        class R:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'data: {"result": {"content": []}}'

            @property
            def headers(self):
                return {"Mcp-Session-Id": "fresh"}

        return R()

    def fake_init(self):
        self.session_id = "fresh"

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(cli.McpSession, "initialize", fake_init)
    result = sess.call("tools/call", {"name": "grep", "arguments": {}})
    assert sess.session_id == "fresh", "session 应被重新初始化"
    assert "result" in result
    assert call_count["n"] == 2, "应重试一次"


def test_session_retry_on_jsonrpc_session_error(monkeypatch) -> None:
    """回归 P5：JSON-RPC error code -32000（会话无效）也触发重试。"""
    sess = cli.McpSession(token="t")
    sess.session_id = "stale"

    responses = [
        {"error": {"code": -32000, "message": "session invalid"}},
        {"result": {"content": [{"type": "text", "text": "ok"}]}},
    ]
    idx = {"i": 0}

    def fake_urlopen(req, timeout=None):
        class R:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return ("data: " + json.dumps(responses[idx["i"]])).encode()

            @property
            def headers(self):
                return {}

        idx["i"] += 1
        return R()

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(cli.McpSession, "initialize", lambda self: setattr(self, "session_id", "fresh"))
    result = sess.call("tools/call", {"name": "grep", "arguments": {}})
    assert result["result"]["content"][0]["text"] == "ok"


def test_parse_ask_answer_extracts_citations_and_strips_footer() -> None:
    sample = (
        "入口是 [JdbcConnection.java:42-57](https://example/blob/src%2Fmain%2Fjava%2FJdbcConnection.java) "
        "与 `src/main/java/com/fxiaoke/jdbc/JdbcConnection.java`。\n\n"
        "---\n**View full research session:** https://coder.example/chat/abc\n"
        "**Model used:** deepseek-v4-flash\n"
    )
    parsed = cli.parse_ask_answer(sample)
    assert parsed["sessionUrl"] == "https://coder.example/chat/abc"
    assert parsed["model"] == "deepseek-v4-flash"
    assert any(c.get("path", "").endswith("JdbcConnection.java") for c in parsed["citations"])
    assert "View full research" not in parsed["answer"]


def test_is_ask_quota_error_detects_subscription_messages() -> None:
    assert cli._is_ask_quota_error("Failed to ask codebase: 订阅额度不足或未配置订阅: subscription")
    assert cli._is_ask_quota_error("insufficient_quota")
    assert not cli._is_ask_quota_error("入口在 JdbcConnection.java，宿主订阅事件总线")


def test_cmd_ask_falls_back_to_next_model_on_quota() -> None:
    class Session:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        def call(self, method: str, params: dict):
            self.calls.append((method, params))
            name = params.get("name")
            args = params.get("arguments") or {}
            if method == "tools/call" and name == "list_language_models":
                models = [
                    {"provider": "anthropic", "model": "qwen3.8-flash"},
                    {"provider": "anthropic", "model": "mimo-v2.5"},
                ]
                return {"result": {"content": [{"type": "text", "text": json.dumps(models)}]}}
            if method == "tools/call" and name == "ask_codebase":
                lm = args.get("languageModel") or {}
                model = lm.get("model")
                if model is None:
                    # server default depleted
                    return {
                        "result": {
                            "isError": True,
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Failed to ask codebase: 订阅额度不足或未配置订阅: subscription",
                                }
                            ],
                        }
                    }
                if model == "qwen3.8-flash":
                    return {
                        "result": {
                            "isError": True,
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Failed to ask codebase: 订阅额度不足或未配置订阅: subscription",
                                }
                            ],
                        }
                    }
                return {
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": "入口 `src/main/java/Foo.java`。\n\n---\n**Model used:** mimo-v2.5\n",
                            }
                        ]
                    }
                }
            raise AssertionError((method, params))

    fake = Session()
    args = cli.build_parser().parse_args(["ask", "--query", "入口？", "--repos", "JavaCommon/jdbc-support"])
    result = cli.cmd_ask(fake, args)
    text = cli._extract_text_content(result)
    assert "Foo.java" in text
    ask_calls = [
        params for method, params in fake.calls if method == "tools/call" and params.get("name") == "ask_codebase"
    ]
    assert len(ask_calls) == 3
    assert ask_calls[0]["arguments"].get("languageModel") is None
    assert ask_calls[1]["arguments"]["languageModel"]["model"] == "qwen3.8-flash"
    assert ask_calls[2]["arguments"]["languageModel"]["model"] == "mimo-v2.5"


def test_cmd_ask_no_model_fallback_stops_on_quota() -> None:
    class Session:
        def __init__(self) -> None:
            self.asks = 0

        def call(self, method: str, params: dict):
            name = params.get("name")
            if method == "tools/call" and name == "list_language_models":
                return {
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": '[{"provider":"anthropic","model":"mimo-v2.5"}]',
                            }
                        ]
                    }
                }
            if method == "tools/call" and name == "ask_codebase":
                self.asks += 1
                return {
                    "result": {
                        "isError": True,
                        "content": [
                            {
                                "type": "text",
                                "text": "Failed to ask codebase: 订阅额度不足或未配置订阅",
                            }
                        ],
                    }
                }
            raise AssertionError((method, params))

    fake = Session()
    args = cli.build_parser().parse_args(["ask", "--query", "入口？", "--no-model-fallback"])
    result = cli.cmd_ask(fake, args)
    assert fake.asks == 1
    assert "ASK_ALL_MODELS_QUOTA_EXHAUSTED" in result["error"]["message"]


def test_cmd_ask_all_models_quota_returns_exhausted_error() -> None:
    class Session:
        def __init__(self) -> None:
            self.asks = 0

        def call(self, method: str, params: dict):
            name = params.get("name")
            if method == "tools/call" and name == "list_language_models":
                return {
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    [
                                        {"provider": "anthropic", "model": "qwen3.8-flash"},
                                        {"provider": "anthropic", "model": "mimo-v2.5"},
                                    ]
                                ),
                            }
                        ]
                    }
                }
            if method == "tools/call" and name == "ask_codebase":
                self.asks += 1
                return {
                    "result": {
                        "isError": True,
                        "content": [
                            {
                                "type": "text",
                                "text": "Failed to ask codebase: 订阅额度不足或未配置订阅: subscription",
                            }
                        ],
                    }
                }
            raise AssertionError((method, params))

    fake = Session()
    args = cli.build_parser().parse_args(["ask", "--query", "入口？"])
    result = cli.cmd_ask(fake, args)
    assert fake.asks == 3  # default + 2 listed
    assert result["error"]["code"] == "ASK_ALL_MODELS_QUOTA_EXHAUSTED"
    assert "ASK_ALL_MODELS_QUOTA_EXHAUSTED" in result["error"]["message"]
