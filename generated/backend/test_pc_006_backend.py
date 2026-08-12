from generated.backend._readiness import require_capability


def test_pc_006_backend_historical_assets_are_registered() -> None:
    require_capability(
        "historical_chart_and_pivot_assets",
        False,
        "no immutable pre-change chart/pivot asset manifest has been discovered in 112",
    )
