"""Compile joined-table save DTOs only from live discovery evidence."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping

_HASH = re.compile(r"sha256:[0-9a-f]{64}")


def canonical_hash(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def compile_joined_table_save_args(intent: Mapping, discovery: Mapping) -> dict:
    """Return a create-only LargeWideTableSaveArgs after provenance validation."""
    required = ("requirement_name", "view_name", "join_type", "join_reason")
    for key in required:
        if not str(intent.get(key, "")).strip():
            raise ValueError(f"JoinedTableIntent.{key} is required")
    if intent["join_type"] not in {"left", "inner", "outer", "vertical"}:
        raise ValueError("unsupported joined-table join_type")
    for key in ("folder", "topology", "identity"):
        item = discovery.get(key)
        if not isinstance(item, Mapping) or not _HASH.fullmatch(str(item.get("response_hash", ""))):
            raise ValueError(f"live {key} discovery evidence is required")
    folder = discovery["folder"]
    if folder.get("name") != intent["requirement_name"] or not folder.get("id"):
        raise ValueError("joined table folder must exactly match requirement name")
    topology = discovery["topology"]
    sources = copy.deepcopy(topology.get("data_sources", []))
    relations = copy.deepcopy(topology.get("relations", []))
    fields = copy.deepcopy(topology.get("display_fields", []))
    if len(sources) < 2 or not relations or not fields:
        raise ValueError("joined table requires two sources, a live relation and output fields")
    source_ids = {str(x.get("id")) for x in sources if x.get("id")}
    if len(source_ids) != len(sources):
        raise ValueError("joined-table source IDs must be live and unique")
    for field in fields:
        if str(field.get("dataSourceId")) not in source_ids:
            raise ValueError("output field does not belong to a selected data source")
    for relation in relations:
        if {str(relation.get("leftDataSourceId")), str(relation.get("rightDataSourceId"))} - source_ids:
            raise ValueError("relation endpoint is outside selected data sources")
        if not relation.get("leftFieldId") or not relation.get("rightFieldId"):
            raise ValueError("relation keys must come from live topology")
    identity = discovery["identity"]
    owner = {"id": str(identity.get("user_id")), "type": "p"}
    lwt = copy.deepcopy(topology.get("base_lwt_args", {}))
    lwt.update({"lwtId": "", "dataSources": sources, "relations": relations,
                "displayFields": fields, "joinType": intent["join_type"],
                "timeZone": str(identity.get("time_zone", "Asia/Shanghai"))})
    query = {"id": "", "lwtArgs": None}
    return {"categoryID": str(folder["id"]), "description": str(intent.get("description", "")),
            "lwtArgs": lwt, "opPermission": "1|1|1|1|1|1", "permType": 1,
            "queryLwtArg": query, "saveType": 0, "userOwnerList": [owner],
            "editableList": [owner], "deletableList": [owner], "exportableList": [owner],
            "subscribeableList": [owner], "shareableList": [owner], "forwardableList": [owner],
            "viewName": str(intent["view_name"]), "creator": str(identity.get("user_id"))}
