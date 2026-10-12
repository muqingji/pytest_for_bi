#!/usr/bin/env python3
"""Parser checks for duplicate traceIds split by a trailing route."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_call_log import parse_call_log


SAMPLE = """
实时查询：FSW-664159.1047-01M36MYX64CWZ33VQ03BHQF14K

| 描述 | TraceId |
| --- | --- |
| 实时查询 | `FSW-664159.1047-01M36MYX64CWZ33VQ03BHQF14K` |
| 返回图名。前端拿到 `chartType` 后渲染`stat/chartConfig/query` | `FSW-fktest7572.1001-01M3M81KAA1PZ0YASE8SYY95XQ` |
| 返回筛选范围 `stat/filters/getFiltersResult` | `FSW-fktest7572.1001-01M3M81KAA1PZ0YASE8SYY95XQ` |
| 查聚合结果。 `fs-bi-stat/stat/data/query` | `FSW-fktest7572.1001-01M3M81KAA1PZ0YASE8SYY95XQ` |
| 获取页面水印`WatermarkApi/getWatermark` | `FSW-fktest7572.1001-01M3M81KK4VBA8GA3X0YY3FJ80` |
| 文件夹列表`getCategoryAndRpt` | `FSW-fktest7572.1001-01M3M81CB41A438TKSTEHZMNV3` |
| 完整路径`FHH/EM1HBISTAT/fs-bi-stat/stat/data/query` | `FSW-fktest7572.1001-01M3M81CB41A438TKSTEHZMNV3` |
| 编辑审批流，获取审批流详情 | `FSW-fktest7572.1001-01M4HXEQXBSGBA9CABQ392ZC6C` |
| 审批定义详情`FHH/EM1HAPPROVAL/Definition/Detail` | `FSW-fktest7572.1001-01M4HXEQXBSGBA9CABQ392ZC6C` |
"""


def main() -> int:
    tasks = parse_call_log(SAMPLE)
    by_route = {task["route"]: task for task in tasks}
    realtime = [task for task in tasks if task["trace_id"].endswith("01M36MYX64CWZ33VQ03BHQF14K")]
    assert realtime and realtime[0]["description"] == "实时查询"
    assert [task["trace_id"] for task in tasks].count("FSW-664159.1047-01M36MYX64CWZ33VQ03BHQF14K") == 1
    shared = [task for task in tasks if task["trace_id"].endswith("01M3M81KAA1PZ0YASE8SYY95XQ")]
    assert [task["route"] for task in shared] == [
        "stat/chartConfig/query",
        "stat/filters/getFiltersResult",
        "fs-bi-stat/stat/data/query",
    ]
    assert "chartType" not in by_route["stat/chartConfig/query"]["route"]
    assert by_route["WatermarkApi/getWatermark"]["description"] == "获取页面水印"
    assert by_route["getCategoryAndRpt"]["description"] == "文件夹列表"
    full = by_route["FHH/EM1HBISTAT/fs-bi-stat/stat/data/query"]
    assert full["service_code"] == "BISTAT"
    assert full["route_key"] == "EM1HBISTAT/fs-bi-stat/stat/data/query"
    slugs = [task["slug"] for task in shared]
    assert len(slugs) == len(set(slugs))
    dirs = [task["output_dir"] for task in tasks]
    assert len(dirs) == len(set(dirs))
    assert all(task["output_dir"].startswith("统计图/") for task in tasks if "审批" not in str(task["description"]) and "APPROVAL" not in str(task.get("route") or "").upper())
    approval = [task for task in tasks if "01M4HXEQXBSGBA9CABQ392ZC6C" in task["trace_id"]]
    assert approval
    assert all(task["category"] == "审批流" for task in approval)
    assert all(task["output_dir"].startswith("审批流/") for task in approval)
    print("ok", len(tasks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
