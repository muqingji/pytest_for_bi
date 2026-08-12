#!/usr/bin/env python3
"""Fail-fast 112 authentication check that never prints credential values."""

from framework.auth.preflight import authentication_preflight


def main() -> int:
    result = authentication_preflight("112")
    print(
        f"112 authentication ready: source={result.credential_source}, "
        f"session_cookies={result.session_cookie_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
