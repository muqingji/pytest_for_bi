"""Fxiaoke CRM enterprise-account authentication."""

from __future__ import annotations

import base64
import secrets
from typing import Any

from framework.clients.http import HttpClient, _employee_id_from_body
from framework.config.environment import EnvironmentConfig


PUBLIC_KEY_DER = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCROXqyCKxG8DrQKvrmdwiAHFJseaLHKsdzJ+61EpEGUawyLk5obn2Z2lyVVG"
    "jqT3KECk3DJtAD6Jux/m/gW2/lxspvhUO1YE1P8OZuUq5xhr/3AWuSSXCqLM2q6TEMnI2VE1BzlsRcxQVGVd4kGszzpyLXYS9"
    "ubFTTp1C2A+uZ1QIDAQAB"
)


class FxiaokeAuthenticationError(RuntimeError):
    """Raised when CRM authentication is rejected."""


def _encrypt_password(password: str) -> str:
    modulus, exponent = _parse_rsa_public_key(base64.b64decode(PUBLIC_KEY_DER))
    message = password.encode("utf-8")
    key_size = (modulus.bit_length() + 7) // 8
    if len(message) > key_size - 11:
        raise ValueError("CRM password is too long for the configured RSA key")
    padding = bytearray()
    while len(padding) < key_size - len(message) - 3:
        padding.extend(byte for byte in secrets.token_bytes(key_size) if byte)
    encoded = b"\x00\x02" + bytes(padding[: key_size - len(message) - 3]) + b"\x00" + message
    encrypted = pow(int.from_bytes(encoded, "big"), exponent, modulus).to_bytes(key_size, "big")
    return base64.b64encode(encrypted).decode("ascii")


def _read_der_value(data: bytes, offset: int) -> tuple[int, bytes, int]:
    tag = data[offset]
    length = data[offset + 1]
    cursor = offset + 2
    if length & 0x80:
        length_bytes = length & 0x7F
        length = int.from_bytes(data[cursor : cursor + length_bytes], "big")
        cursor += length_bytes
    end = cursor + length
    return tag, data[cursor:end], end


def _parse_rsa_public_key(subject_public_key_info: bytes) -> tuple[int, int]:
    _, outer, _ = _read_der_value(subject_public_key_info, 0)
    _, _, offset = _read_der_value(outer, 0)  # AlgorithmIdentifier
    bit_string_tag, bit_string, _ = _read_der_value(outer, offset)
    if bit_string_tag != 0x03 or not bit_string or bit_string[0] != 0:
        raise ValueError("Invalid CRM RSA public key")
    _, rsa_sequence, _ = _read_der_value(bit_string[1:], 0)
    _, modulus_bytes, offset = _read_der_value(rsa_sequence, 0)
    _, exponent_bytes, _ = _read_der_value(rsa_sequence, offset)
    return int.from_bytes(modulus_bytes, "big"), int.from_bytes(exponent_bytes, "big")


def authenticate_fxiaoke(environment: EnvironmentConfig, http_client: HttpClient) -> None:
    """Authenticate once and retain the returned cookies in ``http_client``."""
    if not environment.get("auth.enabled", False):
        return
    if environment.get("auth.type") != "fxiaoke_crm":
        raise ValueError(f"Unsupported authentication type: {environment.get('auth.type')}")

    environment.require(
        "auth.login_base_url",
        "auth.enterprise_account",
        "auth.username",
        "auth.password",
    )
    login_base_url = environment.get("auth.login_base_url").rstrip("/")
    login_path = environment.get(
        "auth.login_path", "/FHH/EM0HUL/Authorize/EnterpriseAccountLogin"
    )
    payload = {
        "publickKey": PUBLIC_KEY_DER,
        "userAccount": environment.get("auth.username"),
        "enterpriseAccount": environment.get("auth.enterprise_account"),
        "rsaPassword": _encrypt_password(environment.get("auth.password")),
        "persistenceHint": True,
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": login_base_url,
        "Referer": f"{login_base_url}/XV/UI/Home",
        "User-Agent": environment.get("auth.user_agent", "pytest-interface-client"),
    }
    if hasattr(http_client, "set_trace_identity"):
        http_client.set_trace_identity(str(environment.get("auth.enterprise_account") or ""))
    response = http_client.post(f"{login_base_url}{login_path}", json_body=payload, headers=headers)
    if response.status_code != 200:
        raise FxiaokeAuthenticationError(f"CRM login failed with HTTP {response.status_code}")
    if isinstance(response.body, dict):
        error: dict[str, Any] = response.body.get("Error") or response.body.get("error") or {}
        if error.get("Code") or error.get("code"):
            message = error.get("Message") or error.get("message") or "unknown error"
            raise FxiaokeAuthenticationError(f"CRM login was rejected: {message}")
        if hasattr(http_client, "set_trace_identity"):
            http_client.set_trace_identity(
                str(environment.get("auth.enterprise_account") or ""),
                _employee_id_from_body(response.body),
            )
