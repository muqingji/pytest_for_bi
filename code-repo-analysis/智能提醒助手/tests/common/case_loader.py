"""测试数据加载：一个业务主体对应一个 JSON 用例文件。

主体：一个接口或一组接口请求的组合场景。
用例：主体下真正执行的一条数据，包含预期请求体与预期返回内容。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from tests.common.settings import CASES_DIR


class CaseSchemaError(ValueError):
    """用例文件结构不合法时抛出，在收集阶段直接失败，避免静默跳过。"""


@dataclass(frozen=True)
class Endpoint:
    method: str
    path: str


@dataclass(frozen=True)
class SubjectData:
    subject: str
    description: str
    endpoint: Endpoint
    defaults: dict[str, Any]
    cases: list[dict[str, Any]]

    @property
    def case_ids(self) -> list[str]:
        return [str(case["id"]) for case in self.cases]


def _require(mapping: dict[str, Any], keys: set[str], where: str) -> None:
    missing = sorted(key for key in keys if key not in mapping)
    if missing:
        raise CaseSchemaError(f"{where} 缺少必填字段：{', '.join(missing)}")


def load_subject(subject: str) -> SubjectData:
    path = CASES_DIR / f"{subject}.json"
    if not path.is_file():
        raise CaseSchemaError(f"找不到主体用例文件：{path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    _require(raw, {"subject", "endpoint", "cases"}, f"{path.name}")
    if raw["subject"] != subject:
        raise CaseSchemaError(f"{path.name} 的 subject 字段为 {raw['subject']!r}，与文件名不一致")

    endpoint_raw = raw["endpoint"]
    _require(endpoint_raw, {"method", "path"}, f"{path.name}.endpoint")

    cases = raw["cases"]
    if not isinstance(cases, list) or not cases:
        raise CaseSchemaError(f"{path.name} 的 cases 必须是非空数组")

    seen: set[str] = set()
    for index, case in enumerate(cases):
        where = f"{path.name}.cases[{index}]"
        _require(case, {"id", "name", "request", "expected"}, where)
        if case["id"] in seen:
            raise CaseSchemaError(f"{where} 用例 id 重复：{case['id']}")
        seen.add(case["id"])
        _require(case["request"], {"body"}, f"{where}.request")
        _require(case["expected"], {"status_code", "body"}, f"{where}.expected")
        mode = case.get("match", "subset")
        if mode not in {"subset", "exact"}:
            raise CaseSchemaError(f"{where}.match 只支持 subset 或 exact，当前为 {mode!r}")

    return SubjectData(
        subject=subject,
        description=raw.get("description", ""),
        endpoint=Endpoint(method=endpoint_raw["method"], path=endpoint_raw["path"]),
        defaults=raw.get("defaults", {}),
        cases=cases,
    )
