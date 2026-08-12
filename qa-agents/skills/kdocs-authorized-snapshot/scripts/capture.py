#!/usr/bin/env python3
"""Capture a KDocs document through official CLI or visible Chrome."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

LEXIANG_SCRIPTS = Path(__file__).parents[2] / "lexiang-authorized-snapshot/scripts"
sys.path.insert(0, str(LEXIANG_SCRIPTS))
from browser_snapshot import capture  # noqa: E402


def _cli(url: str) -> dict | None:
    result = subprocess.run(
        ["kdocs-cli", "drive", "read_file", f"url={url}", "--compact"],
        capture_output=True,
        text=True,
    )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if result.returncode or value.get("code") not in (None, 0):
        return None
    data = value.get("data", value)
    content = data.get("content") or data.get("text") or data.get("markdown")
    if not isinstance(content, str) or not content.strip():
        return None
    return {"title": data.get("title") or data.get("name"), "content": content, "method": "kdocs-cli"}


def _browser(url: str) -> dict:
    js = """JSON.stringify((()=>{const u=location.href;const t=document.title;const x=(document.querySelector('article,[role=main],main,.doc-content,.content')||document.body).innerText||'';return {effective_url:u,title:t,content:x,method:'visible-chrome'};})())"""
    value = capture(url, js, wait_seconds=5)
    effective = str(value.get("effective_url", ""))
    content = str(value.get("content", "")).strip()
    if any(item in effective.lower() for item in ("passport", "login", "singlesign")):
        raise RuntimeError("KDocs redirected to authentication page")
    if len(content) < 100:
        raise RuntimeError("KDocs content is empty or not readable")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.url.startswith(("https://365.kdocs.cn/", "https://www.kdocs.cn/")):
        raise SystemExit("unapproved KDocs host")
    value = _cli(args.url) or _browser(args.url)
    content = str(value["content"]).strip()
    snapshot = {
        "schema_version": "authorized-web-snapshot/1.0",
        "source_url": args.url,
        "effective_url": value.get("effective_url", args.url),
        "title": value.get("title"),
        "capture_method": value["method"],
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "content": content,
        "content_hash": "sha256:" + hashlib.sha256(content.encode()).hexdigest(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: snapshot[key] for key in ("title", "capture_method", "content_hash")}))


if __name__ == "__main__":
    main()
