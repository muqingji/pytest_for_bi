#!/usr/bin/env python3
"""Sourcebot CLI — 直接调用 Sourcebot MCP HTTP API，不做能力裁剪。

用法（cwd = .agents/skills/code-search）:
  uv run python scripts/sourcebot-cli.py <command> [options]

所有命令都等价于对应 MCP 工具，参数名完全一致。
可选 --compact 输出精简格式，--evidence-dir 直接落盘证据文件。

命令:
  grep         按内容搜索（正则匹配文件内容）
  glob         按文件名模式搜索
  read-file    读取文件内容
  symbol-def   查符号定义
  symbol-ref   查符号引用
  commits      列出提交历史
  diff         查看变更差异
  list-repos   列出仓库列表
  list-tree    浏览目录结构
  list-models  列出可用语言模型
  list-tools   列出 MCP 工具（探测自建实例工具面）
  list-branches 列出仓库分支（实例未开放则失败）
  ask          自然语言问答（可用 --structured；非 RCA 主路径）

全局选项:
  --compact        精简输出（去除元信息空行缩进，JSON 输出原地保留）
  --json           机读 JSON 输出
  --evidence-dir   证据目录（写入 SRC-*.json 并自动追加 index.md）
  --no-cache       绕过缓存
  --timeout        网络超时秒数（默认 30）

示例:
  # 紧凑搜索（节省 token）
  uv run python scripts/sourcebot-cli.py grep --repo "AppServer/fs-fmcg" --pattern "NullPointerException" --compact

  # 读取文件并落盘到证据目录
  uv run python scripts/sourcebot-cli.py read-file --repo "AppServer/fs-fmcg" --path "OrderService.java" --offset 130 --limit 30 --evidence-dir output/evidence/20260703-npe/

  # 仓库探测（最省 token 的模式）
  uv run python scripts/sourcebot-cli.py grep --pattern "OrderService" --group-by-repo --compact
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

# ─── Config ────────────────────────────────────────────────────────────────

MCP_URL = "https://coder.firstshare.cn/api/mcp"
CACHE_DIR = Path.home() / ".cache" / "sourcebot-cli"
CACHE_TTL = 300  # seconds (5 min for most queries)
CACHE_MAX_FILES = 5000  # max cache files before cleanup

# ─── MCP Session Manager ───────────────────────────────────────────────────


class McpSession:
    """管理 Sourcebot MCP 的 JSON-RPC over HTTP 会话。"""

    def __init__(self, token: str, timeout: int = 30):
        self._headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {token}",
        }
        self.session_id: str | None = None
        self._timeout = timeout
        self._next_request_id = 100  # monotonic JSON-RPC request id

    @staticmethod
    def _read_sse(body: bytes) -> str:
        """从 SSE 格式响应中提取 data: 行的内容。"""
        text = body.decode("utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("data:"):
                return stripped[5:].strip()
        # 非 SSE 格式（如纯 JSON 错误），按原样返回
        return text

    def initialize(self) -> None:
        """初始化 MCP 会话，获取 session_id。"""
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "sourcebot-cli", "version": "1.0.0"},
            },
        }
        self._next_request_id += 1
        req = urllib.request.Request(
            MCP_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            body = self._read_sse(resp.read())
            result = json.loads(body)
            if "result" in result:
                self.session_id = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
                self._send_initialized_notification()
            elif "error" in result:
                raise RuntimeError(f"MCP init error: {result['error']}")

    def _send_initialized_notification(self) -> None:
        """MCP 2024-11-05：initialize 成功后必须发 notifications/initialized，否则 tools/call 会 401。"""
        if not self.session_id:
            return
        payload = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        headers = dict(self._headers)
        headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(
            MCP_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                resp.read()
        except urllib.error.HTTPError as e:
            if e.code not in (202, 204):
                raise

    # HTTP statuses that indicate the session is no longer valid and should be re-established.
    # 400/401/403 are all observed from the Sourcebot MCP gateway on session/token expiry.
    _SESSION_EXPIRED_STATUS = {400, 401, 403}

    def call(self, method: str, params: dict | None = None) -> dict:
        """调用 MCP 方法。自动管理初始化状态与会话过期重试。

        会话过期由两类信号判定：
          1. HTTP 400/401/403（网关层）；
          2. JSON-RPC error code -32000（MCP 协议层"会话无效"）。
        命中任一即丢弃 session_id、重新 initialize 并重试一次。
        """
        if self.session_id is None:
            self.initialize()

        request_id = self._next_request_id
        self._next_request_id += 1

        def _do_request() -> dict:
            payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params or {},
            }
            headers = dict(self._headers)
            if self.session_id:
                headers["Mcp-Session-Id"] = self.session_id
            req = urllib.request.Request(
                MCP_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = self._read_sse(resp.read())
                return json.loads(body)

        try:
            result = _do_request()
        except urllib.error.HTTPError as e:
            if e.code in self._SESSION_EXPIRED_STATUS and self.session_id is not None:
                # Session (or token) rejected by the gateway — re-establish once.
                self.session_id = None
                self.initialize()
                return _do_request()
            raise

        # JSON-RPC protocol-level session error — same recovery path.
        if "error" in result and result["error"].get("code") == -32000 and self.session_id is not None:
            self.session_id = None
            self.initialize()
            return _do_request()

        return result


# ─── Token ─────────────────────────────────────────────────────────────────


def _find_env_file() -> Path | None:
    """从 CWD 向上查找仓库根的 .env.local（最多上溯 6 层）。"""
    cwd = Path.cwd()
    for path in [cwd, *cwd.parents[:6]]:
        candidate = path / ".env.local"
        if candidate.is_file():
            return candidate
    return None


def _parse_env_value(raw: str) -> str:
    """解析 .env.local 单行值：去引号、去行内注释（仅当 # 前有空格分隔）。"""
    val = raw.strip()
    # strip wrapping quotes (single or double)
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
        return val[1:-1]
    # only treat a space-separated ' #...' as inline comment, so URLs with # are safe
    if " #" in val:
        val = val.split(" #", 1)[0].rstrip()
    return val


def get_token() -> str:
    """获取 token。优先级：环境变量 SOURCEBOT_API_KEY > SOURCEBOT_ACCESS_TOKEN > .env.local。

    若两个环境变量同时设置且值不同，会在 stderr 提示当前胜出者。
    """
    key_env = os.environ.get("SOURCEBOT_API_KEY")
    tok_env = os.environ.get("SOURCEBOT_ACCESS_TOKEN")
    if key_env and tok_env and key_env != tok_env:
        print(
            "Warning: both SOURCEBOT_API_KEY and SOURCEBOT_ACCESS_TOKEN are set with "
            "different values; using SOURCEBOT_API_KEY.",
            file=sys.stderr,
        )
    for val in (key_env, tok_env):
        if val:
            return _parse_env_value(val)

    # 从 .env.local 读取（容忍 `export ` 前缀与行内注释）。
    # 关键：必须遵守优先级 SOURCEBOT_API_KEY > SOURCEBOT_ACCESS_TOKEN，而不是文件顺序——
    # 两个 key 同时写在 .env.local 里时，先扫全部再按优先级返回，避免被文件行序误导。
    env_local = _find_env_file()
    if env_local:
        found: dict[str, str] = {}
        for line in env_local.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, raw_val = line.partition("=")
            key = key.strip()
            if key.startswith("export "):  # tolerate `export KEY=val`
                key = key[len("export ") :].strip()
            val = _parse_env_value(raw_val)
            if key in ("SOURCEBOT_API_KEY", "SOURCEBOT_ACCESS_TOKEN") and val:
                found[key] = val
        for key in ("SOURCEBOT_API_KEY", "SOURCEBOT_ACCESS_TOKEN"):
            if key in found:
                return found[key]
    raise SystemExit(
        "Error: SOURCEBOT_API_KEY or SOURCEBOT_ACCESS_TOKEN not set.\n"
        "  Set it in .env.local or as environment variable."
    )


# ─── Cache ─────────────────────────────────────────────────────────────────


def _cache_key(method: str, params: dict) -> str:
    raw = json.dumps({"m": method, "p": params}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def _cache_cleanup() -> None:
    """清理过期缓存文件。仅当文件数超过上限时触发。"""
    if not CACHE_DIR.exists():
        return
    entries = list(CACHE_DIR.iterdir())
    if len(entries) <= CACHE_MAX_FILES:
        return
    # 按 mtime 排序，删最旧的
    entries.sort(key=lambda p: p.stat().st_mtime)
    for p in entries[: len(entries) - CACHE_MAX_FILES]:
        try:
            p.unlink()
        except OSError:
            pass


def _cache_read(key: str, ttl: int = CACHE_TTL) -> dict | None:
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        if time.time() - path.stat().st_mtime > ttl:
            return None
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _cache_write(key: str, data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(key).write_text(json.dumps(data, ensure_ascii=False, default=str))
    _cache_cleanup()


# ─── Evidence Writer ──────────────────────────────────────────────────────


def _append_index_atomic(index_path: Path, line: str) -> None:
    """以 read-modify-write 原子更新 index.md，避免并行子 agent append 导致行交错。

    对小索引文件（证据目录级别）比跨平台 flock 更稳健：临时文件 + os.replace 是原子的。
    并发写者最坏情况是后写者覆盖先写者，但每行独立、不交错，不会产生半行损坏。
    """
    index_path.parent.mkdir(parents=True, exist_ok=True)
    existing = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    if not existing.endswith("\n") and existing:
        existing += "\n"
    new_content = existing + line + "\n"
    tmp = index_path.with_suffix(index_path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(new_content, encoding="utf-8")
    os.replace(tmp, index_path)


def _resolve_evidence_layout(evidence_dir: str) -> tuple[Path, Path]:
    """解析业务证据目录与根索引目录。

    当前仓库约定：
    - run 根目录放 `index.md`、`handoffs/`、`logs/` 等控制面/运行面产物；
    - report-visible 业务证据优先放在 `evidence/` 子目录。

    因此：
    - 传入 run 根目录时，实际文件写 `<root>/evidence/`，索引写 `<root>/index.md`
    - 传入的如果已经是 `.../evidence`，则文件写该目录，索引写父目录
    """
    root = Path(evidence_dir)
    if root.name == "evidence":
        return root, root.parent
    return root / "evidence", root


def _slugify_token(raw: str, max_len: int = 48) -> str:
    """将路径/符号片段规范为文件名安全段（字母数字与连字符）。"""
    if not raw:
        return "snippet"
    s = raw.strip()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if not s:
        return "snippet"
    return s[:max_len]


def _code_snippet_slug(file_path: str, line_start: int) -> str:
    """SRC-code-snippet 语义段：{ClassOrFile}-L{line}。"""
    stem = Path(file_path.replace("\\", "/")).stem
    return f"{_slugify_token(stem, 40)}-L{line_start}"


def write_evidence(
    evidence_dir: str | None,
    data: dict,
    kind: str = "SRC-search-result",
    *,
    name_slug: str | None = None,
) -> Path | None:
    """写入证据文件到 evidence_dir，返回证据文件路径。

    设计要点：
    - SRC-code-snippet：优先语义文件名 `{kind}-{slug}-{6hex}.json`（slug 含类名/文件名与行号）。
    - 其它 kind 或未传 slug：保留 `{kind}-{timestamp}-{6hex}.json`。
    - 6 位随机后缀：并行子 agent 同秒落盘不撞名。
    - 写完整内容：供 fx-ops converge 直接引用。
    - index.md 原子追加。
    """
    if not evidence_dir:
        return None
    ev_dir, index_root = _resolve_evidence_layout(evidence_dir)
    ev_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    uniq = os.urandom(3).hex()
    if name_slug:
        slug = _slugify_token(name_slug, 56)
        ev_file = ev_dir / f"{kind}-{slug}-{uniq}.json"
    else:
        ev_file = ev_dir / f"{kind}-{timestamp}-{uniq}.json"
    ev_file.write_text(
        json.dumps(
            {
                "meta": {"source": "sourcebot-cli", "time": timestamp, "name_slug": name_slug or None},
                "data": data,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )
    index_path = index_root / "index.md"
    ev_rel = Path(os.path.relpath(ev_file, index_root)).as_posix()
    size = ev_file.stat().st_size
    _append_index_atomic(index_path, f"- `{ev_rel}` — Sourcebot CLI: {kind} ({size} bytes)")
    return ev_file


# ─── Output Formatting ────────────────────────────────────────────────────


def _extract_text_content(result: dict) -> str:
    """从 MCP 响应中提取文本内容。"""
    if "result" not in result:
        if "error" in result:
            return f"ERROR: {result['error']}"
        return json.dumps(result, indent=2, ensure_ascii=False)
    content = result["result"].get("content", [])
    parts = []
    for item in content:
        if isinstance(item, dict):
            if item.get("type") == "text":
                parts.append(item.get("text", ""))
            else:
                parts.append(json.dumps(item, indent=2, ensure_ascii=False))
        else:
            parts.append(str(item))
    return "\n".join(parts)


_ASK_CITATION_RE = re.compile(
    r"\[([^\]\n]+?\.(?:java|kt|js|jsx|ts|tsx|vue|xml|gradle|kts|md|json|yml|yaml|groovy|py|go|rs|sql))"
    r"(?::(\d+)(?:-(\d+))?)?\]\((https?://[^)\s]+)\)",
    re.IGNORECASE,
)
_ASK_PATH_RE = re.compile(
    r"`((?:src|lib|app|apps|packages|scripts|config|android|ios|pages|components|"
    r"webapp|resources)[/\\][^`\n]{2,160})`",
    re.IGNORECASE,
)
_ASK_SESSION_RE = re.compile(r"\*\*View full research session:\*\*\s*(\S+)", re.IGNORECASE)
_ASK_MODEL_RE = re.compile(r"\*\*Model used:\*\*\s*(\S+)", re.IGNORECASE)
_ASK_FOOTER_RE = re.compile(r"\n?---+\s*\*\*View full research session:\*\*[\s\S]*$", re.IGNORECASE)


def _path_from_browse_url(url: str) -> str | None:
    """从 Sourcebot browse URL 还原仓库相对路径。"""
    if not url:
        return None
    match = re.search(r"/blob/([^?#]+)", url)
    if not match:
        return None
    from urllib.parse import unquote

    path = unquote(match.group(1)).replace("\\", "/").lstrip("./")
    return path or None


def parse_ask_answer(text: str) -> dict:
    """把 ask_codebase 的 Markdown 答文解析成可机读结构。

    供偶发 ask 辅助取证；RCA 主路径仍是 grep/symbol/read-file + --evidence-dir。
    """
    raw = str(text or "")
    citations: list[dict] = []
    seen: set[tuple] = set()
    for match in _ASK_CITATION_RE.finditer(raw):
        link_text = match.group(1).strip().lstrip("./")
        url = match.group(4)
        path = _path_from_browse_url(url) or link_text
        start = int(match.group(2)) if match.group(2) else None
        end = int(match.group(3)) if match.group(3) else start
        key = (path, start, end, url)
        if key in seen:
            continue
        seen.add(key)
        item = {"path": path, "url": url}
        if start is not None:
            item["startLine"] = start
        if end is not None:
            item["endLine"] = end
        citations.append(item)
    for match in _ASK_PATH_RE.finditer(raw):
        path = match.group(1).strip().replace("\\", "/").lstrip("./")
        key = (path, None, None, None)
        if key in seen:
            continue
        seen.add(key)
        citations.append({"path": path})
    session = _ASK_SESSION_RE.search(raw)
    model = _ASK_MODEL_RE.search(raw)
    answer = _ASK_FOOTER_RE.sub("", raw).strip()
    answer = re.sub(r"\n{3,}", "\n\n", answer)
    return {
        "answer": answer,
        "citations": citations,
        "sessionUrl": session.group(1) if session else None,
        "model": model.group(1) if model else None,
    }


def _looks_like_json(text: str) -> bool:
    """快速检测文本首行是否为 JSON。"""
    stripped = text.strip()
    return stripped.startswith("{") or stripped.startswith("[")


def _format_compact(result: dict) -> str:
    """精简输出。

    安全的 token 节省：仅删除空白行与行尾空白，**保留行首缩进**。
    行首缩进对 Python / YAML / JSON / Markdown 嵌套都是结构信息，剥离会破坏源码语义
    （曾经出现 read-file 落盘证据因 compact 丢失缩进而失真）。真正能稳定省 token 的是
    去掉无信息的空行和行尾空白，这两类操作不改变任何结构化内容。

    JSON 响应整体原样返回（避免误判与二次解析）。
    """
    text = _extract_text_content(result)
    if not text:
        return text

    # JSON 整体不改动内容。
    if _looks_like_json(text):
        return text

    # 文本：保留缩进，仅去掉空行和行尾空白。
    compact_lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    return "\n".join(compact_lines)


def _write_read_file_code_snippet(args: argparse.Namespace, text_content: str) -> Path | None:
    """为 read-file 额外落盘结构化源码片段证据。

    fx-ops 的报告门禁会直接消费 `SRC-code-snippet-*`，因此这里不能只写通用搜索摘要。
    行号范围基于请求的 offset 和真实返回行数推导；highlightedLines 默认标出首行锚点。
    """
    line_start = args.offset if (args.offset is not None and args.offset >= 1) else 1
    line_count = len(text_content.splitlines()) or 1
    line_end = line_start + line_count - 1
    highlighted_lines = [line_start] if args.offset is not None else []
    slug = _code_snippet_slug(args.path, line_start)
    return write_evidence(
        args.evidence_dir,
        {
            "repo": args.repo,
            "filePath": args.path,
            "lineStart": line_start,
            "lineEnd": line_end,
            "highlightedLines": highlighted_lines,
            "context": text_content,
        },
        kind="SRC-code-snippet",
        name_slug=slug,
    )


_JSON_SECRET_KEYS = frozenset({"token", "authorization"})


def _json_params(args: argparse.Namespace) -> dict:
    """从 argparse 生成 --json params：去掉 subcommand 与鉴权字段。"""
    return {k: v for k, v in vars(args).items() if k != "subcommand" and k.lower() not in _JSON_SECRET_KEYS}


def _error_text(error: object) -> str:
    if isinstance(error, dict):
        msg = error.get("message")
        if msg:
            return str(msg)
    return str(error)


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _print_json_error(args: argparse.Namespace | None, message: str) -> None:
    tool = getattr(args, "subcommand", None) if args is not None else None
    _print_json({"ok": False, "tool": tool, "error": message})


def _fail(message: str, args: argparse.Namespace | None = None) -> None:
    """stderr 打现有错误，--json 时 stdout 再打失败 JSON，然后 exit 1。"""
    print(f"Error: {message}", file=sys.stderr)
    if args is not None and getattr(args, "json", False):
        _print_json_error(args, message)
    sys.exit(1)


def output_result(result: dict, args: argparse.Namespace) -> None:
    """根据参数输出结果。"""
    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        if getattr(args, "json", False):
            _print_json_error(args, _error_text(result["error"]))
        sys.exit(1)

    if args.compact:
        content = _format_compact(result)
    else:
        content = _extract_text_content(result)

    if args.subcommand == "ask" and getattr(args, "structured", False) and isinstance(content, str):
        content = parse_ask_answer(content)

    if getattr(args, "json", False):
        _print_json(
            {
                "ok": True,
                "tool": args.subcommand,
                "params": _json_params(args),
                "content": content,
            }
        )
    else:
        if isinstance(content, dict):
            print(json.dumps(content, ensure_ascii=False, indent=2))
        else:
            print(content)

    # 写入证据：落盘完整内容，而非截断预览。
    # read-file 证据要让 fx-ops `converge` 阶段直接引用而不重读，截断会让该契约失效。
    if args.evidence_dir:
        text_content = _extract_text_content(result)
        write_evidence(
            args.evidence_dir,
            {
                "tool": args.subcommand,
                "params": {k: v for k, v in vars(args).items() if k != "subcommand"},
                "content": text_content,
                "result_length": len(text_content),
            },
            kind="SRC-search-result",
        )
        if args.subcommand == "read-file":
            _write_read_file_code_snippet(args, text_content)


# ─── Subcommands ──────────────────────────────────────────────────────────


def cmd_grep(session: McpSession, args: argparse.Namespace) -> dict:
    params = {"pattern": args.pattern}
    if args.repo:
        params["repo"] = args.repo
    if args.include:
        params["include"] = args.include
    if args.path:
        params["path"] = args.path
    if args.ref:
        params["ref"] = args.ref
    if args.group_by_repo:
        params["groupByRepo"] = True
    if args.limit is not None:
        params["limit"] = args.limit

    cache_key = _cache_key("grep", params)
    if not args.no_cache:
        cached = _cache_read(cache_key)
        if cached:
            return cached

    result = session.call("tools/call", {"name": "grep", "arguments": params})
    _cache_write(cache_key, result)
    return result


def cmd_glob(session: McpSession, args: argparse.Namespace) -> dict:
    params = {"pattern": args.pattern}
    if args.repo:
        params["repo"] = args.repo
    if args.path:
        params["path"] = args.path
    if args.ref:
        params["ref"] = args.ref
    if args.limit is not None:
        params["limit"] = args.limit

    cache_key = _cache_key("glob", params)
    if not args.no_cache:
        cached = _cache_read(cache_key)
        if cached:
            return cached

    result = session.call("tools/call", {"name": "glob", "arguments": params})
    _cache_write(cache_key, result)
    return result


def cmd_read_file(session: McpSession, args: argparse.Namespace) -> dict:
    if args.offset is not None and args.offset < 1:
        raise RuntimeError("read-file --offset 必须 >= 1（1-indexed），传 0 或负数会被服务端拒绝")
    params = {"path": args.path, "repo": args.repo}
    if args.ref:
        params["ref"] = args.ref
    if args.offset is not None:
        params["offset"] = args.offset
    if args.limit is not None:
        params["limit"] = args.limit

    cache_key = _cache_key("read_file", params)
    if not args.no_cache:
        cached = _cache_read(cache_key, ttl=60)
        if cached:
            return cached

    result = session.call("tools/call", {"name": "read_file", "arguments": params})
    _cache_write(cache_key, result)
    return result


def cmd_symbol_def(session: McpSession, args: argparse.Namespace) -> dict:
    params = {"symbol": args.symbol, "repo": args.repo}
    cache_key = _cache_key("find_symbol_definitions", params)
    if not args.no_cache:
        cached = _cache_read(cache_key)
        if cached:
            return cached

    result = session.call("tools/call", {"name": "find_symbol_definitions", "arguments": params})
    _cache_write(cache_key, result)
    return result


def cmd_symbol_ref(session: McpSession, args: argparse.Namespace) -> dict:
    params = {"symbol": args.symbol, "repo": args.repo}
    cache_key = _cache_key("find_symbol_references", params)
    if not args.no_cache:
        cached = _cache_read(cache_key)
        if cached:
            return cached

    result = session.call("tools/call", {"name": "find_symbol_references", "arguments": params})
    _cache_write(cache_key, result)
    return result


def cmd_commits(session: McpSession, args: argparse.Namespace) -> dict:
    params = {"repo": args.repo}
    if args.query:
        params["query"] = args.query
    if args.since:
        params["since"] = args.since
    if args.until:
        params["until"] = args.until
    if args.author:
        params["author"] = args.author
    if args.ref:
        params["ref"] = args.ref
    if args.path:
        params["path"] = args.path
    if args.page is not None:
        params["page"] = args.page
    if args.per_page is not None:
        params["perPage"] = args.per_page

    cache_key = _cache_key("list_commits", params)
    if not args.no_cache:
        cached = _cache_read(cache_key, ttl=60)
        if cached:
            return cached

    result = session.call("tools/call", {"name": "list_commits", "arguments": params})
    _cache_write(cache_key, result)
    return result


def cmd_diff(session: McpSession, args: argparse.Namespace) -> dict:
    params = {"repo": args.repo, "base": args.base, "head": args.head}
    if args.path:
        params["path"] = args.path

    # diff is fully determined by (repo, base, head, path) — safe to cache like other reads.
    cache_key = _cache_key("get_diff", params)
    if not args.no_cache:
        cached = _cache_read(cache_key, ttl=60)
        if cached:
            return cached

    result = session.call("tools/call", {"name": "get_diff", "arguments": params})
    _cache_write(cache_key, result)
    return result


def cmd_list_repos(session: McpSession, args: argparse.Namespace) -> dict:
    params = {}
    if args.query:
        params["query"] = args.query
    if args.page is not None:
        params["page"] = args.page
    if args.per_page is not None:
        params["perPage"] = args.per_page
    if args.sort:
        params["sort"] = args.sort
    if args.direction:
        params["direction"] = args.direction

    cache_key = _cache_key("list_repos", params)
    if not args.no_cache:
        cached = _cache_read(cache_key)
        if cached:
            return cached

    result = session.call("tools/call", {"name": "list_repos", "arguments": params})
    _cache_write(cache_key, result)
    return result


def cmd_list_tree(session: McpSession, args: argparse.Namespace) -> dict:
    params = {"repo": args.repo}
    if args.path:
        params["path"] = args.path
    if args.ref:
        params["ref"] = args.ref
    if args.depth is not None:
        params["depth"] = args.depth
    if args.include_files is not None:
        params["includeFiles"] = args.include_files
    if args.include_dirs is not None:
        params["includeDirectories"] = args.include_dirs
    if args.max_entries is not None:
        params["maxEntries"] = args.max_entries

    cache_key = _cache_key("list_tree", params)
    if not args.no_cache:
        cached = _cache_read(cache_key)
        if cached:
            return cached

    result = session.call("tools/call", {"name": "list_tree", "arguments": params})
    _cache_write(cache_key, result)
    return result


def cmd_list_models(session: McpSession, args: argparse.Namespace) -> dict:
    result = session.call("tools/call", {"name": "list_language_models", "arguments": {}})
    return result


def _extract_tools(result: dict) -> list:
    """从 tools/list 响应中抽出 tools 数组。"""
    payload = result.get("result")
    if not isinstance(payload, dict):
        return []
    tools = payload.get("tools")
    return tools if isinstance(tools, list) else []


def _tool_schema(tool: dict) -> dict:
    """兼容 inputSchema / input_schema。"""
    if not isinstance(tool, dict):
        return {}
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict):
        schema = tool.get("input_schema")
    return schema if isinstance(schema, dict) else {}


def _format_tools_list(tools: list, *, compact: bool) -> str:
    """人类可读工具面：默认一块一个工具；--compact 只打印名字。"""
    names_and_schemas: list[tuple[str, dict]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = tool.get("name")
        if not name:
            continue
        names_and_schemas.append((str(name), _tool_schema(tool)))

    if compact:
        return "\n".join(name for name, _ in names_and_schemas)

    blocks: list[str] = []
    for name, schema in names_and_schemas:
        required = schema.get("required") or []
        if not isinstance(required, list):
            required = []
        properties = schema.get("properties") or {}
        prop_names = list(properties) if isinstance(properties, dict) else []
        lines = [name]
        if required:
            lines.append("  required: " + ", ".join(str(item) for item in required))
        if prop_names:
            lines.append("  properties: " + ", ".join(str(item) for item in prop_names))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def cmd_list_tools(session: McpSession, args: argparse.Namespace) -> dict:
    """探测 MCP 工具面。不缓存，不根据 list 生成子命令。"""
    result = session.call("tools/list", {})
    if "error" in result:
        return result
    formatted = _format_tools_list(_extract_tools(result), compact=args.compact)
    return {"result": {"content": [{"type": "text", "text": formatted}]}}


_ASK_QUOTA_MARKERS = (
    "订阅额度不足",
    "未配置订阅",
    "额度不足或未配置订阅",
    "insufficient_quota",
    "quota exceeded",
    "quota_exceeded",
)


def _is_ask_quota_error(message: str) -> bool:
    """判断 ask 失败是否为 LLM 订阅/额度问题（可换模型重试）。"""
    text = str(message or "")
    low = text.lower()
    if any(marker.lower() in low for marker in _ASK_QUOTA_MARKERS):
        return True
    if "订阅额度" in text or "未配置订阅" in text:
        return True
    # 英文服务端文案常夹在 Failed to ask 里。
    if "failed to ask codebase" in low and ("subscription" in low or "quota" in low):
        return True
    return False


def _ask_failure_message(result: dict) -> str | None:
    """ask_codebase 失败时返回错误文案；成功返回 None。"""
    if "error" in result:
        return _error_text(result["error"])
    payload = result.get("result")
    text = _extract_text_content(result)
    if isinstance(payload, dict) and payload.get("isError"):
        return text or "ask isError"
    # 服务端常把失败写进 text，而不是 isError。
    if re.search(r"Failed to ask codebase", text or "", re.I):
        return text
    return None


def _parse_language_model_entries(result: dict) -> list[dict]:
    """从 list_language_models 响应抽出 {provider, model} 列表。"""
    raw = _extract_text_content(result)
    data: object = raw
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError:
                data = raw
    entries: list = []
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        for key in ("models", "languageModels", "items", "data"):
            if isinstance(data.get(key), list):
                entries = data[key]
                break
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in entries:
        if not isinstance(item, dict):
            continue
        model = item.get("model") or item.get("id") or item.get("name")
        if not model:
            continue
        provider = item.get("provider") or item.get("vendor")
        key = (str(provider or ""), str(model))
        if key in seen:
            continue
        seen.add(key)
        entry = {"model": str(model)}
        if provider:
            entry["provider"] = str(provider)
        out.append(entry)
    return out


def _ask_model_candidates(session: McpSession, args: argparse.Namespace) -> list[dict | None]:
    """构建 ask 模型候选。None 表示不传 languageModel（走服务端默认）。"""
    listed: list[dict] = []
    try:
        listed = _parse_language_model_entries(cmd_list_models(session, args))
    except Exception as exc:  # noqa: BLE001 — 列表失败时仍可走默认/显式模型
        print(f"ask: list_language_models failed ({exc}); fallback limited", file=sys.stderr)

    candidates: list[dict | None] = []
    if args.model:
        entry: dict = {"model": args.model}
        if args.provider:
            entry["provider"] = args.provider
        candidates.append(entry)
    else:
        candidates.append(None)

    if getattr(args, "no_model_fallback", False):
        return candidates

    for entry in listed:
        model = entry.get("model")
        if not model:
            continue
        if args.model and model == args.model:
            continue
        nxt = {"model": model}
        provider = entry.get("provider") or args.provider
        if provider:
            nxt["provider"] = provider
        candidates.append(nxt)
    return candidates


def _format_ask_model(choice: dict | None) -> str:
    if choice is None:
        return "server-default"
    provider = choice.get("provider")
    model = choice.get("model")
    return f"{provider}/{model}" if provider else str(model)


def cmd_ask(session: McpSession, args: argparse.Namespace) -> dict:
    """自然语言问答。额度/订阅不足时按 list_language_models 顺序切换下一模型。"""
    base: dict = {"query": args.query}
    if args.repos:
        base["repos"] = args.repos.split(",")
    if args.visibility:
        base["visibility"] = args.visibility

    candidates = _ask_model_candidates(session, args)
    last_error: str | None = None

    for index, choice in enumerate(candidates):
        params = dict(base)
        if choice is not None:
            lm: dict = {"model": choice["model"]}
            if choice.get("provider"):
                lm["provider"] = choice["provider"]
            elif args.provider:
                lm["provider"] = args.provider
            params["languageModel"] = lm
        elif args.provider:
            params["languageModel"] = {"provider": args.provider}

        result = session.call("tools/call", {"name": "ask_codebase", "arguments": params})
        failure = _ask_failure_message(result)
        if failure is None:
            if index > 0:
                print(
                    f"ask: succeeded with {_format_ask_model(choice)} after quota fallback",
                    file=sys.stderr,
                )
            return result

        last_error = failure
        if not _is_ask_quota_error(failure):
            return result

        nxt = candidates[index + 1] if index + 1 < len(candidates) else None
        if nxt is None:
            break
        print(
            f"ask: quota/subscription on {_format_ask_model(choice)}; trying {_format_ask_model(nxt)}",
            file=sys.stderr,
        )

    # 全部候选都因额度失败：直接报错退出，避免调用方继续空转。
    tried = ", ".join(_format_ask_model(c) for c in candidates) or "(none)"
    msg = f"ASK_ALL_MODELS_QUOTA_EXHAUSTED: tried {len(candidates)} model(s) [{tried}]; last={last_error}"
    print(f"ask: {msg}; stop", file=sys.stderr)
    return {"error": {"message": msg, "code": "ASK_ALL_MODELS_QUOTA_EXHAUSTED"}}


def cmd_list_branches(session: McpSession, args: argparse.Namespace) -> dict:
    """列出仓库分支（官方 MCP `list_branches`；自建实例常未开放）。"""
    params: dict = {"repo": args.repo}
    if args.query:
        params["query"] = args.query
    if args.page is not None:
        params["page"] = args.page
    if args.per_page is not None:
        params["perPage"] = args.per_page

    cache_key = _cache_key("list_branches", params)
    if not args.no_cache:
        cached = _cache_read(cache_key)
        if cached:
            return cached

    result = session.call("tools/call", {"name": "list_branches", "arguments": params})
    if "error" in result:
        raise RuntimeError(f"list_branches 不可用: {_error_text(result['error'])}")
    text_content = _extract_text_content(result)
    payload = result.get("result") or {}
    if payload.get("isError") or "Tool list_branches not found" in text_content:
        raise RuntimeError(f"list_branches 不可用：当前自建 Sourcebot 实例未开放该 MCP 工具（{text_content[:160]}）")
    _cache_write(cache_key, result)
    return result


# ─── Main ──────────────────────────────────────────────────────────────────


GLOBAL_PARENT = argparse.ArgumentParser(add_help=False)
GLOBAL_PARENT.add_argument(
    "--compact",
    action="store_true",
    help="精简输出（删除空白行与行尾空白，保留缩进；JSON 原样返回）。搜索/定位类推荐",
)
GLOBAL_PARENT.add_argument(
    "--json",
    action="store_true",
    help="机读 JSON 输出（stdout 仅 JSON；可与 --compact 同时使用，compact 只作用于 content）",
)
GLOBAL_PARENT.add_argument("--evidence-dir", help="证据落盘目录（写 SRC-*.json 并更新 index.md）")
GLOBAL_PARENT.add_argument("--no-cache", action="store_true", help="绕过缓存")
GLOBAL_PARENT.add_argument("--timeout", type=int, default=30, help="网络超时秒数（默认 30）")

EXAMPLES = """\
示例:
  # 仓库探测（最省 token）
  uv run python scripts/sourcebot-cli.py grep --pattern "OrderService" --group-by-repo --compact

  # 定库搜索 + 落盘证据
  uv run python scripts/sourcebot-cli.py grep --repo "AppServer/fs-fmcg" \\
      --pattern "NullPointerException" --include "*.java" --compact \\
      --evidence-dir output/evidence/20260704-npe/

  # 源码阅读（不加 --compact，需要全量分析；read-file 必须带 --repo）
  uv run python scripts/sourcebot-cli.py read-file --repo "AppServer/fs-fmcg" \\
      --path "OrderService.java" --offset 130 --limit 30

  # 符号定义
  uv run python scripts/sourcebot-cli.py symbol-def --repo "AppServer/fs-fmcg" --symbol "OrderService"

  # 提交历史 + 变更差异（变更溯源）
  uv run python scripts/sourcebot-cli.py commits --repo "AppServer/fs-fmcg" --since "7 days ago" --compact
  uv run python scripts/sourcebot-cli.py diff --repo "AppServer/fs-fmcg" --base "abc123" --head "def456"

  # 探测自建实例工具面 / 机读输出
  uv run python scripts/sourcebot-cli.py list-tools --compact
  uv run python scripts/sourcebot-cli.py grep --pattern "OrderService" --group-by-repo --compact --json
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sourcebot CLI — Sourcebot HTTP API 直接调用（跨仓库代码搜索/读取/变更溯源）",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[GLOBAL_PARENT],
    )

    sub = parser.add_subparsers(dest="subcommand", required=True)

    # copy 全局参数到各子命令
    def _p(name, **kw):
        return sub.add_parser(name, parents=[GLOBAL_PARENT], **kw)

    # grep
    p = _p("grep", help="按内容搜索")
    p.add_argument("--repo", help="仓库名")
    p.add_argument("--pattern", required=True, help="正则表达式")
    p.add_argument("--include", help="文件过滤（如 *.java）")
    p.add_argument("--path", help="路径过滤")
    p.add_argument("--ref", help="分支/标签/commit")
    p.add_argument("--group-by-repo", action="store_true", help="按仓库分组汇总")
    p.add_argument("--limit", type=int, help="最大匹配数")

    # glob
    p = _p("glob", help="按文件名搜索")
    p.add_argument("--repo", help="仓库名")
    p.add_argument("--pattern", required=True, help="glob 模式")
    p.add_argument("--path", help="路径过滤")
    p.add_argument("--ref", help="分支/标签/commit")
    p.add_argument("--limit", type=int, help="最大返回数")

    # read-file
    p = _p("read-file", help="读取文件内容")
    p.add_argument("--repo", required=True, help="仓库名")
    p.add_argument("--path", required=True, help="文件路径")
    p.add_argument("--ref", help="分支/标签/commit")
    p.add_argument("--offset", type=int, help="起始行号（1-indexed，最小 1，传 0/负数将报错退出）")
    p.add_argument("--limit", type=int, help="读取行数")

    # symbol-def
    p = _p("symbol-def", help="查符号定义")
    p.add_argument("--repo", required=True, help="仓库名")
    p.add_argument("--symbol", required=True, help="符号名（精确）")

    # symbol-ref
    p = _p("symbol-ref", help="查符号引用")
    p.add_argument("--repo", required=True, help="仓库名")
    p.add_argument("--symbol", required=True, help="符号名（精确）")

    # commits
    p = _p("commits", help="列出提交历史")
    p.add_argument("--repo", required=True, help="仓库名")
    p.add_argument("--query", help="按消息搜索")
    p.add_argument("--since", help="开始日期（如 '7 days ago', '2024-01-01'）")
    p.add_argument("--until", help="结束日期")
    p.add_argument("--author", help="按作者过滤")
    p.add_argument("--ref", help="分支/标签/commit")
    p.add_argument("--path", help="文件路径过滤")
    p.add_argument("--page", type=int, default=1, help="页码")
    p.add_argument("--per-page", type=int, default=50, help="每页数量")

    # diff
    p = _p("diff", help="查看变更差异")
    p.add_argument("--repo", required=True, help="仓库名")
    p.add_argument("--base", required=True, help="基础 ref")
    p.add_argument("--head", required=True, help="目标 ref")
    p.add_argument("--path", help="文件路径过滤")

    # list-repos
    p = _p("list-repos", help="列出仓库列表")
    p.add_argument("--query", help="按名称过滤")
    p.add_argument("--page", type=int, default=1, help="页码")
    p.add_argument("--per-page", type=int, default=30, help="每页数量")
    p.add_argument("--sort", choices=["name", "pushed"], default="name", help="排序字段")
    p.add_argument("--direction", choices=["asc", "desc"], default="asc", help="排序方向")

    # list-tree
    p = _p("list-tree", help="浏览目录结构")
    p.add_argument("--repo", required=True, help="仓库名")
    p.add_argument("--path", default="", help="目录路径")
    p.add_argument("--ref", help="分支/标签/commit")
    p.add_argument("--depth", type=int, default=1, help="递归深度（1-10）")
    p.add_argument(
        "--include-files",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="包含文件（用 --no-include-files 关闭）",
    )
    p.add_argument(
        "--include-dirs",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="包含目录（用 --no-include-dirs 关闭）",
    )
    p.add_argument("--max-entries", type=int, default=1000, help="最大条目数")

    # list-models
    _p("list-models", help="列出可用语言模型")

    # list-tools
    _p("list-tools", help="列出 MCP 工具（探测自建实例工具面）")

    # list-branches（官方有；自建实例可能未开放）
    p = _p("list-branches", help="列出仓库分支（需实例开放 list_branches）")
    p.add_argument("--repo", required=True, help="仓库名")
    p.add_argument("--query", help="按分支名过滤")
    p.add_argument("--page", type=int, help="页码")
    p.add_argument("--per-page", type=int, help="每页条数")

    # ask
    p = _p("ask", help="自然语言问答（消耗 LLM token！非 RCA 主路径）")
    p.add_argument("--query", required=True, help="问题")
    p.add_argument("--repos", help="仓库列表（逗号分隔）")
    p.add_argument("--provider", help="LLM provider")
    p.add_argument("--model", help="LLM model ID")
    p.add_argument(
        "--no-model-fallback",
        action="store_true",
        help="禁用额度不足时自动切换 list_language_models 中的下一模型",
    )
    p.add_argument("--visibility", choices=["PRIVATE", "PUBLIC"], default="PRIVATE")
    p.add_argument(
        "--structured",
        action="store_true",
        help="解析 Markdown 引用为 citations/sessionUrl/model（建议配合 --json）",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        token = get_token()
    except SystemExit:
        raise  # 保持友好错误消息

    try:
        session = McpSession(token, timeout=args.timeout)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        print(f"Error: 无法连接 Sourcebot MCP Server ({MCP_URL}): {e}", file=sys.stderr)
        print("  - 检查网络连通性", file=sys.stderr)
        print("  - 确认 token 未过期", file=sys.stderr)
        if getattr(args, "json", False):
            _print_json_error(args, f"无法连接 Sourcebot MCP Server ({MCP_URL}): {e}")
        sys.exit(1)

    cmd_map = {
        "grep": cmd_grep,
        "glob": cmd_glob,
        "read-file": cmd_read_file,
        "symbol-def": cmd_symbol_def,
        "symbol-ref": cmd_symbol_ref,
        "commits": cmd_commits,
        "diff": cmd_diff,
        "list-repos": cmd_list_repos,
        "list-tree": cmd_list_tree,
        "list-models": cmd_list_models,
        "list-tools": cmd_list_tools,
        "list-branches": cmd_list_branches,
        "ask": cmd_ask,
    }

    handler = cmd_map.get(args.subcommand)
    if not handler:
        parser.print_help()
        sys.exit(1)

    try:
        result = handler(session, args)
        output_result(result, args)
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        _fail(f"Sourcebot API 请求失败: {e}", args)
    except json.JSONDecodeError as e:
        _fail(f"Sourcebot 返回了无效的响应: {e}", args)
    except RuntimeError as e:
        _fail(str(e), args)


if __name__ == "__main__":
    main()
