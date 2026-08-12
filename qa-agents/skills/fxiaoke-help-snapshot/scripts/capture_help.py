#!/usr/bin/env python3
"""Crawl an approved Fxiaoke help subtree without external dependencies."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.text: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        value = re.sub(r"\s+", " ", data).strip()
        if value:
            self.text.append(value)
            if self._in_title:
                self.title += value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-pages", type=int, default=1000)
    args = parser.parse_args()
    root = urlparse(args.url)
    if root.scheme != "https" or root.hostname != "help.fxiaoke.com":
        raise SystemExit("unapproved help host")
    root_path = root.path.rstrip("/") + "/"
    queue = [args.url]
    seen: set[str] = set()
    pages: list[dict] = []
    failures: list[dict] = []
    while queue and len(seen) < args.max_pages:
        url = urldefrag(queue.pop(0))[0].rstrip("/")
        if url in seen:
            continue
        seen.add(url)
        try:
            request = Request(url, headers={"User-Agent": "K01-PTKB-Snapshot/1.0"})
            with urlopen(request, timeout=20) as response:
                effective = response.geturl()
                body = response.read().decode("utf-8", errors="replace")
            parsed_effective = urlparse(effective)
            if parsed_effective.hostname != "help.fxiaoke.com":
                raise RuntimeError("cross-origin redirect")
            page = PageParser()
            page.feed(body)
            content = "\n".join(page.text)
            if len(content) < 50:
                raise RuntimeError("page content is empty")
            pages.append({
                "source_url": url,
                "effective_url": effective,
                "title": page.title,
                "content": content,
                "content_hash": "sha256:" + hashlib.sha256(content.encode()).hexdigest(),
            })
            for href in page.links:
                child = urldefrag(urljoin(effective, href))[0]
                parsed = urlparse(child)
                if parsed.scheme == "https" and parsed.hostname == root.hostname and (
                    parsed.path.rstrip("/") == root.path.rstrip("/")
                    or parsed.path.startswith(root_path)
                ):
                    queue.append(child)
        except Exception as error:
            failures.append({"source_url": url, "error": str(error)})
    snapshot = {
        "schema_version": "product-help-snapshot/1.0",
        "source_url": args.url,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "page_count": len(pages),
        "failure_count": len(failures),
        "truncated": bool(queue),
        "pages": pages,
        "failures": failures,
    }
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    snapshot["manifest_hash"] = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"page_count": len(pages), "failure_count": len(failures), "truncated": bool(queue), "manifest_hash": snapshot["manifest_hash"]}))


if __name__ == "__main__":
    main()
