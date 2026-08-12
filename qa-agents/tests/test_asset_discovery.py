from qa_agents.asset_discovery import discover_catalog


def test_recursive_catalog_discovers_nested_assets_and_breaks_cycles():
    pages = {
        "0": {"items": [{"itemID": "folder-1", "itemName": "目录", "isCategory": 1}]},
        "folder-1": {"items": [
            {"itemID": "folder-1", "itemName": "目录", "isCategory": 1},
            {"itemID": "chart-1", "itemName": "统计图", "isCategory": 2},
        ]},
    }
    result = discover_catalog(lambda category, page, size: pages[category], page_size=10)
    assert {item["itemID"] for item in result} == {"folder-1", "chart-1"}
