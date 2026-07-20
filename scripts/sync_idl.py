#!/usr/bin/env python3
"""Incrementally generate RPC API facades from Thrift and Proto IDL files.

Only generated files whose service definition changed are rewritten. Files for
removed services are intentionally retained so an IDL cleanup cannot silently
break an existing test suite; remove them explicitly after migration.
"""

from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class RpcMethod:
    name: str
    arguments: tuple[str, ...]


@dataclass(frozen=True)
class RpcService:
    name: str
    methods: tuple[RpcMethod, ...]
    source: Path
    definition: str


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*|#[^\n]*", "", text)


def _braced_blocks(text: str, keyword: str) -> Iterable[tuple[str, str]]:
    pattern = re.compile(rf"\b{keyword}\s+([A-Za-z_]\w*)(?:\s+extends\s+\w+)?\s*\{{")
    for match in pattern.finditer(text):
        depth = 1
        position = match.end()
        start = position
        while position < len(text) and depth:
            depth += (text[position] == "{") - (text[position] == "}")
            position += 1
        if depth:
            raise ValueError(f"Unclosed {keyword} block for {match.group(1)}")
        yield match.group(1), text[start : position - 1]


def _split_top_level(value: str, delimiter: str = ",") -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(value):
        if char in "<([{":
            depth += 1
        elif char in ">)]}":
            depth -= 1
        elif char == delimiter and depth == 0:
            parts.append(value[start:index])
            start = index + 1
    parts.append(value[start:])
    return parts


def _argument_names(arguments: str, thrift: bool) -> tuple[str, ...]:
    names: list[str] = []
    for argument in _split_top_level(arguments):
        argument = argument.strip()
        if not argument:
            continue
        if thrift:
            argument = re.sub(r"^\d+\s*:\s*", "", argument)
            argument = re.sub(r"^(required|optional)\s+", "", argument)
        argument = argument.split("=")[0].strip()
        match = re.search(r"([A-Za-z_]\w*)\s*$", argument)
        if match:
            names.append(match.group(1))
    return tuple(names)


def parse_thrift(path: Path) -> list[RpcService]:
    clean = _strip_comments(path.read_text(encoding="utf-8"))
    services: list[RpcService] = []
    for name, body in _braced_blocks(clean, "service"):
        methods: list[RpcMethod] = []
        for match in re.finditer(
            r"(?:oneway\s+)?[A-Za-z_][\w.<>, ]*?\s+([A-Za-z_]\w*)\s*\((.*?)\)", body, re.DOTALL
        ):
            methods.append(RpcMethod(match.group(1), _argument_names(match.group(2), thrift=True)))
        services.append(RpcService(name, tuple(methods), path, body))
    return services


def parse_proto(path: Path) -> list[RpcService]:
    clean = _strip_comments(path.read_text(encoding="utf-8"))
    services: list[RpcService] = []
    for name, body in _braced_blocks(clean, "service"):
        methods = []
        for method_name, request_type in re.findall(
            r"\brpc\s+([A-Za-z_]\w*)\s*\(\s*(?:stream\s+)?([\w.]+)\s*\)\s*returns", body
        ):
            # Protobuf request fields are unavailable without protoc descriptors.
            # The API accepts one request object under the type's snake-case name.
            parameter = _snake_case(request_type.rsplit(".", 1)[-1])
            methods.append(RpcMethod(method_name, (parameter,)))
        services.append(RpcService(name, tuple(methods), path, body))
    return services


def _snake_case(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _render(service: RpcService, source_root: Path) -> str:
    relative_source = service.source.relative_to(source_root).as_posix()
    definition_hash = hashlib.sha256(service.definition.encode()).hexdigest()
    class_name = f"{service.name}Api"
    lines = [
        '"""Generated RPC API. Regenerate with: python3 scripts/sync_idl.py --idl-dir idl"""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Any",
        "",
        "from framework.clients.models import ApiResponse",
        "from framework.clients.rpc import RpcClient",
        "",
        f'GENERATED_FROM = "{relative_source}"',
        f'IDL_SHA256 = "{definition_hash}"',
        "",
        f"class {class_name}:",
        f'    """Facade for IDL service ``{service.name}``."""',
        "",
        "    def __init__(self, rpc: RpcClient) -> None:",
        "        self.rpc = rpc",
    ]
    if not service.methods:
        lines.extend(["", "    pass"])
    for method in service.methods:
        signature = ", ".join(f"{argument}: Any = None" for argument in method.arguments)
        signature = f", {signature}" if signature else ""
        params = ", ".join(f'"{argument}": {argument}' for argument in method.arguments)
        lines.extend(
            [
                "",
                f"    def {method.name}(self{signature}) -> ApiResponse:",
                f'        """Call ``{service.name}.{method.name}``."""',
                f"        params = {{{params}}}",
                "        return self.rpc.call(",
                f'            "{service.name}", "{method.name}", {{key: value for key, value in params.items() if value is not None}}',
                "        )",
            ]
        )
    return "\n".join(lines) + "\n"


def _target_path(service: RpcService, idl_dir: Path, output_dir: Path) -> Path:
    relative = service.source.relative_to(idl_dir).with_suffix("")
    stem = "_".join(relative.parts + (_snake_case(service.name), "api"))
    return output_dir / f"{stem}.py"


def sync(idl_dir: Path, output_dir: Path, dry_run: bool = False) -> dict[str, int]:
    if not idl_dir.is_dir():
        raise FileNotFoundError(f"IDL directory does not exist: {idl_dir}")
    services: list[RpcService] = []
    for path in sorted(idl_dir.rglob("*.thrift")):
        services.extend(parse_thrift(path))
    for path in sorted(idl_dir.rglob("*.proto")):
        services.extend(parse_proto(path))
    if not services:
        print(f"No .thrift or .proto service definitions found in {idl_dir}")
        return {"created": 0, "updated": 0, "unchanged": 0}
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    for service in services:
        target = _target_path(service, idl_dir, output_dir)
        rendered = _render(service, idl_dir)
        old_content = target.read_text(encoding="utf-8") if target.exists() else None
        if old_content == rendered:
            counts["unchanged"] += 1
            print(f"unchanged {target}")
            continue
        state = "created" if old_content is None else "updated"
        counts[state] += 1
        print(f"{state} {target}")
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered, encoding="utf-8")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate incremental RPC API facades from IDL")
    parser.add_argument("--idl-dir", type=Path, required=True, help="Directory containing .thrift and/or .proto files")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("src/framework/api/generated"), help="Generated API directory"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print files that would change without writing them")
    args = parser.parse_args()
    counts = sync(args.idl_dir, args.output_dir, args.dry_run)
    print("sync summary: " + ", ".join(f"{key}={value}" for key, value in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
