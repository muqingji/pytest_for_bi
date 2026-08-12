#!/usr/bin/env python3
"""Read a visible Chrome tab without extracting browser credentials."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time


def _osa(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script], check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _playwright(url: str, javascript: str) -> dict:
    script = Path(__file__).with_name("playwright_snapshot.js")
    profile = Path("/private/tmp/k01-authorized-browser-profile")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as handle:
        handle.write(javascript)
        js_path = Path(handle.name)
    try:
        result = subprocess.run(
            ["node", str(script), url, str(js_path), str(profile), "false"],
            capture_output=True,
            text=True,
            timeout=45,
        )
        if result.returncode:
            message = result.stderr.strip().replace(str(Path.home()), "<home>")
            raise RuntimeError(f"authorized browser failed: {message[:1000]}")
        value = json.loads(result.stdout)
        if not isinstance(value, dict):
            raise RuntimeError("Playwright snapshot result must be an object")
        return value
    finally:
        js_path.unlink(missing_ok=True)


def capture(url: str, javascript: str, *, wait_seconds: float = 3.0) -> dict:
    quoted_url = json.dumps(url)
    try:
        _osa(
            'tell application "Google Chrome"\n'
            "activate\n"
            "if (count of windows) = 0 then make new window\n"
            f"set URL of active tab of front window to {quoted_url}\n"
            "end tell"
        )
    except subprocess.CalledProcessError:
        return _playwright(url, javascript)
    time.sleep(wait_seconds)
    encoded_js = json.dumps(javascript)
    output = _osa(
        'tell application "Google Chrome"\n'
        f"set resultText to execute active tab of front window javascript {encoded_js}\n"
        "return resultText\n"
        "end tell"
    )
    value = json.loads(output)
    if not isinstance(value, dict):
        raise RuntimeError("browser snapshot result must be an object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--javascript", required=True)
    parser.add_argument("--wait-seconds", type=float, default=3.0)
    args = parser.parse_args()
    print(json.dumps(capture(args.url, args.javascript, wait_seconds=args.wait_seconds)))


if __name__ == "__main__":
    main()
