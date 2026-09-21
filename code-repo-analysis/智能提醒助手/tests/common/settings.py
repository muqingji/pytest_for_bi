"""测试运行配置：读取 testenv/config.json，并允许环境变量覆盖。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PACKAGE_ROOT / "testenv" / "config.json"
CASES_DIR = PACKAGE_ROOT / "tests" / "cases"
REPORTS_DIR = PACKAGE_ROOT / "reports"


@dataclass(frozen=True)
class Settings:
    base_url: str
    token: str
    caller: str
    timeout_seconds: float

    @property
    def authorization(self) -> str:
        return f"Bearer {self.token}"


def _value(env_name: str, fallback):
    value = os.environ.get(env_name)
    return value if value not in (None, "") else fallback


def load_settings() -> Settings:
    raw = {}
    if CONFIG_PATH.is_file():
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return Settings(
        base_url=str(_value("REMINDER_BASE_URL", raw.get("base_url", "http://127.0.0.1:8080"))).rstrip("/"),
        token=str(_value("REMINDER_TOKEN", raw.get("token", "local-dev-token"))),
        caller=str(_value("REMINDER_CALLER", raw.get("caller", "pytest_reminder"))),
        timeout_seconds=float(_value("REMINDER_TIMEOUT", raw.get("timeout_seconds", 5))),
    )
