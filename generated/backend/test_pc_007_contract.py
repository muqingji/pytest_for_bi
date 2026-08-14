from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_pc_007_web_h5_chart_detail_uses_same_backend_contract():
    evidence = json.loads(
        (ROOT / "generated/pc007-web-h5-detail-equivalence.json").read_text()
    )
    chart = evidence["chart"]
    assert evidence["requirement_scope"] == "backend_only"
    assert evidence["decision"] == "mobile_ui_validation_not_required"
    assert chart["same_endpoint"] is True
    assert chart["web_endpoint"] == chart["h5_endpoint"]
    assert chart["shared_business_service"] == "StatDetailQueryService.queryStatDetail"


def test_pc_007_joined_table_sync_async_paths_share_business_service():
    evidence = json.loads(
        (ROOT / "generated/pc007-web-h5-detail-equivalence.json").read_text()
    )
    joined = evidence["joined_table"]
    assert joined["same_transport_endpoint"] is False
    assert joined["same_business_dto"] == "QueryStatDetailInfoArg"
    assert joined["mapper"] == "AsyncQueryDetailInfoArgMapper.toQueryStatDetailInfoArg"
    assert joined["shared_business_service"] == "StatDetailQueryService.queryStatDetail"


def test_pc_007_frozen_source_anchors_remain_available():
    evidence = json.loads(
        (ROOT / "generated/pc007-web-h5-detail-equivalence.json").read_text()
    )
    for source in evidence["source_anchors"]:
        path = Path(source) if source.startswith("/") else ROOT / source
        assert path.is_file(), source
