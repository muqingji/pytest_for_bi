"""Generated RPC API. Regenerate with: python3 scripts/sync_idl.py --idl-dir idl"""

from __future__ import annotations

from typing import Any

from framework.clients.models import ApiResponse
from framework.clients.rpc import RpcClient

GENERATED_FROM = "example.thrift"
IDL_SHA256 = "2eb9ddd8fc71914a7bc8c2078482cd80e3642bf2b7e570e07027056100b110bd"

class UserServiceApi:
    """Facade for IDL service ``UserService``."""

    def __init__(self, rpc: RpcClient) -> None:
        self.rpc = rpc

    def get_user(self, user_id: Any = None) -> ApiResponse:
        """Call ``UserService.get_user``."""
        params = {"user_id": user_id}
        return self.rpc.call(
            "UserService", "get_user", {key: value for key, value in params.items() if value is not None}
        )

    def delete_user(self, user_id: Any = None) -> ApiResponse:
        """Call ``UserService.delete_user``."""
        params = {"user_id": user_id}
        return self.rpc.call(
            "UserService", "delete_user", {key: value for key, value in params.items() if value is not None}
        )
