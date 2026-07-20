from __future__ import annotations

import sys
import types

from framework.clients.rpc import RpcClient


def test_rpc_adapter_receives_its_configuration(monkeypatch) -> None:
    module = types.ModuleType("test_rpc_adapter")
    captured = {}

    def call(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    module.call = call
    monkeypatch.setitem(sys.modules, "test_rpc_adapter", module)
    client = RpcClient({"adapter": "test_rpc_adapter:call", "host": "rpc.local"})
    response = client.call("UserService", "get_user", {"user_id": "1"})
    assert response.body == {"ok": True}
    assert captured["config"]["host"] == "rpc.local"
