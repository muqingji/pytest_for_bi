"""Transport-neutral response structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ApiResponse:
    status_code: int | None
    body: Any = None
    headers: dict[str, str] = field(default_factory=dict)
    elapsed_ms: float | None = None
    raw_text: str = ""

