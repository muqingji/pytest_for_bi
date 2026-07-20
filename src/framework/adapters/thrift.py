"""Thrift adapter loaded through ``rpc.adapter: framework.adapters.thrift:call``."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def call(
    *,
    service: str,
    method: str,
    params: dict[str, Any] | list[Any],
    metadata: dict[str, Any],
    config: dict[str, Any],
) -> Any:
    """Call a Thrift service defined by ``rpc.idl_file``.

    ``metadata`` is accepted for adapter compatibility. Standard Thrift does
    not define a portable per-request metadata mechanism.
    """
    del metadata
    required = ("idl_file", "host", "port")
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise ValueError(f"Thrift RPC adapter requires rpc.{', rpc.'.join(missing)}")
    try:
        import thriftpy2
        from thriftpy2.rpc import make_client
    except ImportError as error:
        raise RuntimeError("Install thriftpy2 to use the Thrift RPC adapter") from error

    idl_path = Path(str(config["idl_file"])).resolve()
    if not idl_path.is_file():
        raise FileNotFoundError(f"Thrift IDL file does not exist: {idl_path}")
    module_name = f"interface_test_{hashlib.sha1(str(idl_path).encode()).hexdigest()}_thrift"
    idl_module = thriftpy2.load(str(idl_path), module_name=module_name)
    try:
        service_class = getattr(idl_module, service)
    except AttributeError as error:
        raise ValueError(f"Service '{service}' does not exist in {idl_path}") from error
    client = make_client(service_class, str(config["host"]), int(config["port"]), timeout=config.get("timeout", 20))
    try:
        rpc_method = getattr(client, method)
        return rpc_method(**params) if isinstance(params, dict) else rpc_method(*params)
    finally:
        client.close()
