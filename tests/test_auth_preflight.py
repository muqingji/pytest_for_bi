from __future__ import annotations

import json
import os

import pytest

from framework.auth.preflight import validate_credential_source


NAMES = (
    "FXIAOKE_112_ENTERPRISE_ACCOUNT",
    "FXIAOKE_112_USERNAME",
    "FXIAOKE_112_PASSWORD",
)


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)


def test_complete_environment_credentials_are_selected(monkeypatch, tmp_path) -> None:
    for name in NAMES:
        monkeypatch.setenv(name, "configured")
    assert validate_credential_source("112", root=tmp_path) == "environment_variables"


def test_partial_environment_credentials_fail_closed(monkeypatch, tmp_path) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv(NAMES[0], "configured")
    with pytest.raises(ValueError, match="partially configured"):
        validate_credential_source("112", root=tmp_path)


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission contract")
def test_local_credential_file_requires_private_permissions(monkeypatch, tmp_path) -> None:
    _clear(monkeypatch)
    path = tmp_path / "config/environment.112.local.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"auth": {}}), encoding="utf-8")
    path.chmod(0o644)
    with pytest.raises(PermissionError, match="chmod 600"):
        validate_credential_source("112", root=tmp_path)
    path.chmod(0o600)
    assert validate_credential_source("112", root=tmp_path) == "environment_local_config"
