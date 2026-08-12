from __future__ import annotations


def require_capability(capability: str, available: bool, reason: str) -> None:
    assert available, f"{capability} is not ready: {reason}"
