#!/usr/bin/env python3
"""Generate OpenAPI contracts and Python callers from the fs-bi Java repository."""

from __future__ import annotations

import argparse
import hashlib
import json
import keyword
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable


HTTP_ANNOTATIONS = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "PatchMapping": "PATCH",
    "DeleteMapping": "DELETE",
    "GET": "GET",
    "POST": "POST",
    "PUT": "PUT",
    "DELETE": "DELETE",
}

# Verified by fs-bi-stat/src/test/resources/auto-test-script/dialingTest.js.
CRM_GATEWAY_PREFIXES = {"fs-bi-stat": "/FHH/EM1HBISTAT"}


@dataclass(frozen=True)
class JavaParameter:
    name: str
    java_type: str
    location: str
    wire_name: str
    required: bool = True


@dataclass(frozen=True)
class JavaEndpoint:
    module: str
    controller: str
    java_method: str
    http_method: str
    path: str
    return_type: str
    parameters: tuple[JavaParameter, ...]
    source: str
    line: int
    description: str = ""


def _strip_comments(text: str) -> str:
    def blank(match: re.Match[str]) -> str:
        return "".join("\n" if char == "\n" else " " for char in match.group())

    text = re.sub(r"/\*.*?\*/", blank, text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", blank, text)


def _javadoc_description(raw: str, declaration_start: int) -> str:
    comments = list(re.finditer(r"/\*\*(.*?)\*/", raw[:declaration_start], flags=re.DOTALL))
    if not comments:
        return ""
    comment = comments[-1]
    tail = _strip_comments(raw[comment.end() : declaration_start])
    if ";" in tail:
        return ""
    depth = 0
    for char in tail:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "}" and depth == 0:
            return ""
    lines: list[str] = []
    for raw_line in comment.group(1).splitlines():
        line = re.sub(r"^\s*\*?\s?", "", raw_line).strip()
        if not line:
            if lines:
                break
            continue
        if line.startswith("@") or line.startswith("{@"):
            break
        line = re.sub(r"<[^>]+>", "", line).strip()
        if line:
            lines.append(line)
    return " ".join(lines)


def _balanced_end(text: str, start: int, opening: str = "(", closing: str = ")") -> int:
    depth = 0
    quote_char = ""
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quote_char:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote_char:
                quote_char = ""
            continue
        if char in {'"', "'"}:
            quote_char = char
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index + 1
    raise ValueError("Unbalanced Java declaration")


def _annotations(text: str, start: int, end: int) -> list[tuple[str, str, int]]:
    found = []
    position = start
    pattern = re.compile(r"@([A-Za-z_$][\w$]*)")
    while match := pattern.search(text, position, end):
        name = match.group(1)
        args = ""
        annotation_end = match.end()
        opening = annotation_end
        while opening < end and text[opening].isspace():
            opening += 1
        if opening < end and text[opening] == "(":
            annotation_end = _balanced_end(text, opening)
            args = text[opening + 1 : annotation_end - 1]
        found.append((name, args, match.start()))
        position = annotation_end
    return found


def _leading_region(text: str, declaration_start: int) -> tuple[int, str]:
    boundary = 0
    quote_char = ""
    escaped = False
    parenthesis_depth = 0
    bracket_depth = 0
    for index, char in enumerate(text[:declaration_start]):
        if quote_char:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote_char:
                quote_char = ""
            continue
        if char in {'"', "'"}:
            quote_char = char
        elif char == "(":
            parenthesis_depth += 1
        elif char == ")":
            parenthesis_depth = max(0, parenthesis_depth - 1)
        elif char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth = max(0, bracket_depth - 1)
        elif char in "};" and parenthesis_depth == 0 and bracket_depth == 0:
            boundary = index + 1
    region = text[boundary:declaration_start]
    first_annotation = region.find("@")
    if first_annotation < 0:
        return declaration_start, ""
    return boundary + first_annotation, region[first_annotation:]


def _annotation_values(args: str) -> list[str]:
    value_match = re.search(r"(?:^|,)\s*(?:value|path)\s*=\s*(\{.*?\}|\".*?\")", args, re.DOTALL)
    candidate = value_match.group(1) if value_match else args
    return re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', candidate)


def _mapping_paths(annotations: list[tuple[str, str, int]], class_level: bool = False) -> list[tuple[str, str]]:
    mappings: list[tuple[str, str]] = []
    for name, args, _ in annotations:
        if name in HTTP_ANNOTATIONS:
            paths = _annotation_values(args) if args else [""]
            for path in paths or [""]:
                mappings.append((HTTP_ANNOTATIONS[name], path))
        elif name == "RequestMapping":
            paths = _annotation_values(args) or [""]
            method_match = re.search(r"RequestMethod\.([A-Z]+)", args)
            method = method_match.group(1) if method_match else ("ANY" if class_level else "POST")
            mappings.extend((method, path) for path in paths)
        elif name == "Path":
            paths = _annotation_values(args) or [""]
            mappings.extend(("ANY", path) for path in paths)
    return mappings


def _join_path(*parts: str) -> str:
    populated = [part.strip("/") for part in parts if part and part != "/"]
    return "/" + "/".join(populated) if populated else "/"


def _split_top_level(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depths = {"(": 0, "[": 0, "{": 0, "<": 0}
    pairs = {")": "(", "]": "[", "}": "{", ">": "<"}
    for index, char in enumerate(value):
        if char in depths:
            depths[char] += 1
        elif char in pairs:
            depths[pairs[char]] -= 1
        elif char == "," and not any(depths.values()):
            parts.append(value[start:index])
            start = index + 1
    parts.append(value[start:])
    return [part.strip() for part in parts if part.strip()]


def _wire_name(annotation_args: str, fallback: str) -> str:
    values = _annotation_values(annotation_args)
    return values[0] if values else fallback


def _parse_parameter(raw: str) -> JavaParameter | None:
    annotations = _annotations(raw, 0, len(raw))
    clean = re.sub(r"@[A-Za-z_$][\w$]*(?:\s*\([^)]*\))?", "", raw).strip()
    clean = re.sub(r"\b(final|@NotNull|@Nullable)\b", "", clean).strip()
    match = re.search(r"(.+?)\s+([A-Za-z_$][\w$]*)$", clean, re.DOTALL)
    if not match:
        return None
    java_type, name = " ".join(match.group(1).split()), match.group(2)
    location = "context"
    wire_name = name
    required = True
    for annotation_name, args, _ in annotations:
        if annotation_name in {"RequestBody", "Body"}:
            location = "body"
        elif annotation_name in {"PathVariable", "PathParam"}:
            location = "path"
            wire_name = _wire_name(args, name)
        elif annotation_name in {"RequestParam", "QueryParam"}:
            location = "query"
            wire_name = _wire_name(args, name)
            required_match = re.search(r"required\s*=\s*(false|true)", args)
            required = not required_match or required_match.group(1) == "true"
    if location == "context" and not re.search(r"HttpServlet|ServletRequest|ServletResponse|Principal", java_type):
        location = "body"
    if location == "context":
        return None
    return JavaParameter(name, java_type, location, wire_name, required)


METHOD_PATTERN = re.compile(
    r"\bpublic\s+(?:static\s+)?(?:final\s+)?(?:<[^>{}]+>\s+)?"
    r"(?P<return>[A-Za-z_$][\w$.,<>? \[\]]*?)\s+"
    r"(?P<name>[A-Za-z_$][\w$]*)\s*\(",
    re.DOTALL,
)


def parse_java_file(path: Path, repo_root: Path) -> list[JavaEndpoint]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    text = _strip_comments(raw)
    relative = path.relative_to(repo_root)
    module = relative.parts[0]
    class_match = re.search(r"\b(?:class|interface)\s+([A-Za-z_$][\w$]*)", text)
    if not class_match:
        return []
    controller = class_match.group(1)
    class_body_start = text.find("{", class_match.end())
    if class_body_start < 0:
        return []
    class_region_start, _ = _leading_region(text, class_match.start())
    class_annotations = _annotations(text, class_region_start, class_match.start())
    annotation_names = {name for name, _, _ in class_annotations}
    if not annotation_names.intersection({"Controller", "RestController", "Path"}):
        return []
    class_mappings = _mapping_paths(class_annotations, class_level=True) or [("ANY", "")]

    endpoints: list[JavaEndpoint] = []
    for method_match in METHOD_PATTERN.finditer(text, class_match.end()):
        open_paren = text.find("(", method_match.start(), method_match.end())
        close_paren = _balanced_end(text, open_paren)
        declaration_tail = text[close_paren : min(close_paren + 500, len(text))]
        if not re.match(r"\s*(?:throws\s+[^\{;]+)?[\{;]", declaration_tail):
            continue
        region_start, _ = _leading_region(text, method_match.start())
        region_start = max(region_start, class_body_start + 1)
        method_annotations = _annotations(text, region_start, method_match.start())
        names = {name for name, _, _ in method_annotations}
        method_mappings = _mapping_paths(method_annotations)
        if not method_mappings and not names.intersection(HTTP_ANNOTATIONS):
            continue
        # JAX-RS places @Path and @POST separately; combine them into one mapping.
        verbs = [HTTP_ANNOTATIONS[name] for name in names if name in HTTP_ANNOTATIONS]
        jax_paths = [path_value for method, path_value in method_mappings if method == "ANY"]
        if verbs and jax_paths:
            method_mappings = [(verb, path_value) for verb in verbs for path_value in jax_paths]
        parameters = tuple(
            parameter
            for raw_parameter in _split_top_level(text[open_paren + 1 : close_paren - 1])
            if (parameter := _parse_parameter(raw_parameter)) is not None
        )
        for class_method, class_path in class_mappings:
            for http_method, method_path in method_mappings:
                effective_method = http_method if http_method != "ANY" else class_method
                if effective_method == "ANY":
                    effective_method = "POST"
                endpoints.append(
                    JavaEndpoint(
                        module=module,
                        controller=controller,
                        java_method=method_match.group("name"),
                        http_method=effective_method,
                        path=_join_path(class_path, method_path),
                        return_type=" ".join(method_match.group("return").split()),
                        parameters=parameters,
                        source=relative.as_posix(),
                        line=raw[: method_match.start()].count("\n") + 1,
                        description=_javadoc_description(raw, method_match.start()),
                    )
                )
    return endpoints


def scan_repository(repo_root: Path) -> list[JavaEndpoint]:
    endpoints = []
    for path in sorted(repo_root.glob("*/src/main/java/**/*.java")):
        endpoints.extend(parse_java_file(path, repo_root))
    return endpoints


def _external_endpoint(endpoint: JavaEndpoint) -> JavaEndpoint | None:
    gateway_prefix = CRM_GATEWAY_PREFIXES.get(endpoint.module)
    if gateway_prefix is None:
        return None
    context_path = f"/{endpoint.module}"
    internal_path = endpoint.path
    if internal_path != context_path and not internal_path.startswith(f"{context_path}/"):
        internal_path = _join_path(context_path, internal_path)
    return replace(endpoint, path=_join_path(gateway_prefix, internal_path))


def externally_callable_endpoints(endpoints: Iterable[JavaEndpoint]) -> list[JavaEndpoint]:
    callable_endpoints: list[JavaEndpoint] = []
    routes: dict[tuple[str, str, str], JavaEndpoint] = {}
    for endpoint in endpoints:
        external = _external_endpoint(endpoint)
        if external is None:
            continue
        route = (external.module, external.http_method, external.path)
        previous = routes.get(route)
        if previous:
            if (previous.controller, previous.java_method) == (external.controller, external.java_method):
                continue
            raise ValueError(
                f"Duplicate external HTTP route {external.http_method} {external.path}: "
                f"{previous.source}:{previous.line} and {external.source}:{external.line}"
            )
        routes[route] = external
        callable_endpoints.append(external)
    return callable_endpoints


def _snake_case(name: str) -> str:
    name = re.sub(r"Controller$|Resource$|ServiceImpl$", "", name)
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).replace("$", "_").lower()


def _python_name(name: str) -> str:
    value = re.sub(r"\W", "_", name)
    if not value or value[0].isdigit():
        value = f"value_{value}"
    return f"{value}_" if keyword.iskeyword(value) else value


def _java_schema(java_type: str) -> dict[str, Any]:
    normalized = java_type.replace(" ", "")
    if normalized in {"boolean", "Boolean"}:
        return {"type": "boolean", "x-java-type": java_type}
    if normalized in {"byte", "short", "int", "long", "Integer", "Long", "Short", "BigInteger"}:
        return {"type": "integer", "x-java-type": java_type}
    if normalized in {"float", "double", "Float", "Double", "BigDecimal"}:
        return {"type": "number", "x-java-type": java_type}
    if normalized.startswith(("List<", "Set<", "Collection<", "Iterable<")) or normalized.endswith("[]"):
        return {"type": "array", "items": {}, "x-java-type": java_type}
    if normalized in {"String", "char", "Character"}:
        return {"type": "string", "x-java-type": java_type}
    return {"type": "object", "x-java-type": java_type}


def _operation_identity(endpoint: JavaEndpoint, used: set[str]) -> tuple[str, str]:
    controller = _snake_case(endpoint.controller)
    method = _snake_case(endpoint.java_method)
    operation_id = f"{endpoint.module.replace('-', '_')}.{controller}.{method}"
    python_method = _python_name(f"{controller}_{method}")
    if operation_id in used:
        digest = hashlib.sha1(f"{endpoint.http_method}:{endpoint.path}".encode()).hexdigest()[:8]
        operation_id = f"{operation_id}_{digest}"
        python_method = f"{python_method}_{digest}"
    used.add(operation_id)
    return operation_id, python_method


def build_documents(endpoints: Iterable[JavaEndpoint]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    documents: dict[str, dict[str, Any]] = {}
    generated_methods: dict[str, list[dict[str, Any]]] = {}
    used: set[str] = set()
    routes: dict[tuple[str, str, str], JavaEndpoint] = {}
    for endpoint in endpoints:
        route = (endpoint.module, endpoint.http_method, endpoint.path)
        if previous := routes.get(route):
            raise ValueError(
                f"Duplicate HTTP route {endpoint.http_method} {endpoint.path} in {endpoint.module}: "
                f"{previous.source}:{previous.line} and {endpoint.source}:{endpoint.line}"
            )
        routes[route] = endpoint
        operation_id, python_method = _operation_identity(endpoint, used)
        document = documents.setdefault(
            endpoint.module,
            {
                "openapi": "3.1.0",
                "info": {"title": f"{endpoint.module} generated HTTP API", "version": "generated"},
                "paths": {},
            },
        )
        operation: dict[str, Any] = {
            "operationId": operation_id,
            "summary": f"{endpoint.controller}.{endpoint.java_method}",
            "x-java-return-type": endpoint.return_type,
            "x-auth-cookie-query": {"cookie": "fs_token", "parameter": "_fs_token"},
            "x-default-headers": {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
            },
            "parameters": [],
            "responses": {"200": {"description": "Successful response", "content": {"application/json": {"schema": _java_schema(endpoint.return_type)}}}},
        }
        body_parameters = [parameter for parameter in endpoint.parameters if parameter.location == "body"]
        for parameter in endpoint.parameters:
            if parameter.location not in {"path", "query"}:
                continue
            operation["parameters"].append(
                {
                    "name": parameter.wire_name,
                    "in": parameter.location,
                    "required": True if parameter.location == "path" else parameter.required,
                    "schema": _java_schema(parameter.java_type),
                    "x-java-name": parameter.name,
                }
            )
        if body_parameters:
            body_schema = _java_schema(body_parameters[0].java_type)
            if len(body_parameters) > 1:
                body_schema = {
                    "type": "object",
                    "properties": {parameter.name: _java_schema(parameter.java_type) for parameter in body_parameters},
                    "required": [parameter.name for parameter in body_parameters if parameter.required],
                }
            operation["requestBody"] = {
                "required": any(parameter.required for parameter in body_parameters),
                "content": {"application/json": {"schema": body_schema}},
            }
        document["paths"].setdefault(endpoint.path, {})[endpoint.http_method.lower()] = operation
        generated_methods.setdefault(endpoint.module, []).append(
            {
                "operation_id": operation_id,
                "python_method": python_method,
                "path_parameters": [parameter for parameter in endpoint.parameters if parameter.location == "path"],
                "query_parameters": [parameter for parameter in endpoint.parameters if parameter.location == "query"],
                "body_required": bool(body_parameters and any(parameter.required for parameter in body_parameters)),
                "body_type": body_parameters[0].java_type if len(body_parameters) == 1 else "object",
                "return_type": endpoint.return_type,
                "http_method": endpoint.http_method,
                "path": endpoint.path,
                "description": endpoint.description or f"{endpoint.controller}.{endpoint.java_method}",
            }
        )
    return documents, generated_methods


def _render_module_class(module: str, methods: list[dict[str, Any]]) -> str:
    class_name = "".join(part.capitalize() for part in module.replace("fs-bi-", "").split("-")) + "Api"
    lines = [
        '"""Generated from fs-bi Java HTTP declarations. Do not edit."""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Any",
        "",
        "from framework.api.http_api import HttpApiInvoker",
        "from framework.clients.models import ApiResponse",
        "",
        f"class {class_name}:",
        "    def __init__(self, invoker: HttpApiInvoker) -> None:",
        "        self._invoker = invoker",
    ]
    for method in sorted(methods, key=lambda item: item["python_method"]):
        positional = []
        path_dict = []
        used_parameters = {"self", "body", "params", "headers"}
        for parameter in method["path_parameters"]:
            python_parameter = _python_name(parameter.name)
            while python_parameter in used_parameters:
                python_parameter = f"path_{python_parameter}"
            used_parameters.add(python_parameter)
            positional.append(f"{python_parameter}: Any")
            path_dict.append(f'"{parameter.wire_name}": {python_parameter}')
        if method["body_required"]:
            positional.append("body: Any")
        signature = ", ".join(positional)
        signature = f", {signature}" if signature else ""
        query_arguments = []
        query_assignments = []
        for parameter in method["query_parameters"]:
            python_parameter = _python_name(parameter.name)
            while python_parameter in used_parameters:
                python_parameter = f"query_{python_parameter}"
            used_parameters.add(python_parameter)
            default = "" if parameter.required else " = None"
            query_arguments.append(f"{python_parameter}: Any{default}")
            condition = "" if parameter.required else f"if {python_parameter} is not None:"
            if condition:
                query_assignments.extend(
                    [condition, f'    _params["{parameter.wire_name}"] = {python_parameter}']
                )
            else:
                query_assignments.append(f'_params["{parameter.wire_name}"] = {python_parameter}')
        keyword_arguments = ([] if method["body_required"] else ["body: Any = None"]) + query_arguments + [
            "params: dict[str, Any] | None = None",
            "headers: dict[str, str] | None = None",
        ]
        keyword_signature = ", ".join(keyword_arguments)
        definition = f"    def {method['python_method']}(self{signature}, *, {keyword_signature}) -> ApiResponse:"
        lines.extend(
            [
                "",
                definition,
                '        """',
                f'        Purpose: {method["description"]}',
                f'        Route: {method["http_method"]} {method["path"]}',
                f'        Request body: {method["body_type"]}{" (required)" if method["body_required"] else " (optional)"}',
                f'        Response: {method["return_type"]}',
                f'        Operation ID: {method["operation_id"]}',
                '        """',
                "        _params = dict(params or {})",
                *[f"        {line}" for line in query_assignments],
                "        return self._invoker.call(",
                f'            "{method["operation_id"]}",',
                "            body=body,",
                f"            path_params={{{', '.join(path_dict)}}}," if path_dict else "            path_params=None,",
                "            params=_params or None,",
                "            headers=headers,",
                "        )",
            ]
        )
    return "\n".join(lines) + "\n"


def _render_root(modules: list[str]) -> str:
    imports = []
    assignments = []
    for module in modules:
        file_stem = module.replace("-", "_") + "_api"
        class_name = "".join(part.capitalize() for part in module.replace("fs-bi-", "").split("-")) + "Api"
        attribute = _python_name(module.replace("fs-bi-", "").replace("-", "_"))
        imports.append(f"from .{file_stem} import {class_name}")
        assignments.append(f"        self.{attribute} = {class_name}(invoker)")
    return "\n".join(
        [
            '"""Generated aggregate entry point for fs-bi HTTP APIs."""',
            "",
            "from framework.api.catalog import HttpApiCatalog",
            "from framework.api.http_api import HttpApiInvoker",
            "from framework.clients.http import HttpClient",
            *imports,
            "",
            "class FsBiApi:",
            "    def __init__(self, http_client: HttpClient, catalog: HttpApiCatalog) -> None:",
            "        invoker = HttpApiInvoker(http_client, catalog)",
            *assignments,
            "",
        ]
    )


def sync(repo_root: Path, idl_output: Path, python_output: Path) -> dict[str, int]:
    endpoints = externally_callable_endpoints(scan_repository(repo_root))
    documents, generated_methods = build_documents(endpoints)
    idl_output.mkdir(parents=True, exist_ok=True)
    python_output.mkdir(parents=True, exist_ok=True)
    (python_output / "__init__.py").write_text("from .fs_bi_api import FsBiApi\n\n__all__ = [\"FsBiApi\"]\n", encoding="utf-8")
    for module, document in sorted(documents.items()):
        (idl_output / f"{module}.openapi.json").write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        python_name = module.replace("-", "_") + "_api.py"
        (python_output / python_name).write_text(
            _render_module_class(module, generated_methods[module]), encoding="utf-8"
        )
    modules = sorted(documents)
    (python_output / "fs_bi_api.py").write_text(_render_root(modules), encoding="utf-8")
    expected_idl = {f"{module}.openapi.json" for module in modules}
    for stale in idl_output.glob("fs-bi-*.openapi.json"):
        if stale.name not in expected_idl:
            stale.unlink()
    expected_python = {module.replace("-", "_") + "_api.py" for module in modules}
    expected_python.update({"__init__.py", "fs_bi_api.py"})
    for stale in python_output.glob("fs_bi_*_api.py"):
        if stale.name not in expected_python:
            stale.unlink()
    return {"modules": len(modules), "endpoints": len(endpoints)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Path to the fs-bi repository")
    parser.add_argument("--idl-output", type=Path, default=Path("idl/http/generated/fs-bi"))
    parser.add_argument("--python-output", type=Path, default=Path("src/framework/api/generated/fs_bi"))
    args = parser.parse_args()
    result = sync(args.source.resolve(), args.idl_output, args.python_output)
    print(f"generated modules={result['modules']}, endpoints={result['endpoints']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
