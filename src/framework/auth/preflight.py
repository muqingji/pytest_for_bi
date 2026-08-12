"""Credential-source validation and non-secret authentication preflight."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from framework.auth.fxiaoke import authenticate_fxiaoke
from framework.clients.http import HttpClient
from framework.config.environment import EnvironmentConfig, project_root


_CREDENTIAL_ENV_NAMES = (
    "FXIAOKE_112_ENTERPRISE_ACCOUNT",
    "FXIAOKE_112_USERNAME",
    "FXIAOKE_112_PASSWORD",
)


@dataclass(frozen=True)
class AuthenticationPreflightResult:
    environment: str
    credential_source: str
    authenticated: bool
    session_cookie_count: int


def validate_credential_source(
    environment: str, *, root: Path | None = None
) -> str:
    """Select one complete credential source without exposing secret values."""
    base = root or project_root()
    present = [name for name in _CREDENTIAL_ENV_NAMES if os.getenv(name)]
    if present and len(present) != len(_CREDENTIAL_ENV_NAMES):
        missing = sorted(set(_CREDENTIAL_ENV_NAMES) - set(present))
        raise ValueError(
            "112 credential environment variables are only partially configured; missing: "
            + ", ".join(missing)
        )
    if len(present) == len(_CREDENTIAL_ENV_NAMES):
        return "environment_variables"

    local_path = base / "config" / f"environment.{environment}.local.json"
    if not local_path.is_file():
        raise ValueError(
            f"No complete credential source for environment {environment!r}; configure all "
            f"FXIAOKE_112_* variables or {local_path}"
        )
    if os.name != "nt":
        mode = stat.S_IMODE(local_path.stat().st_mode)
        if mode & 0o077:
            raise PermissionError(
                f"Credential file permissions are too broad: {local_path}; require chmod 600"
            )
    return "environment_local_config"


def authentication_preflight(
    environment_name: str = "112", *, root: Path | None = None
) -> AuthenticationPreflightResult:
    """Authenticate once and report only safe readiness metadata."""
    base = root or project_root()
    source = validate_credential_source(environment_name, root=base)
    environment = EnvironmentConfig.load(environment_name, base)
    environment.require_section("auth")
    http = HttpClient(
        base_url=environment.get("http.base_url", ""),
        headers=environment.get("http.headers", {}),
        timeout=environment.get("http.timeout", 20.0),
        verify=environment.get("http.verify", True),
    )
    try:
        authenticate_fxiaoke(environment, http)
        cookie_count = len(list(http.cookies.jar))
        if cookie_count == 0:
            raise RuntimeError("112 authentication returned no session cookies")
        return AuthenticationPreflightResult(
            environment=environment_name,
            credential_source=source,
            authenticated=True,
            session_cookie_count=cookie_count,
        )
    finally:
        http.close()
