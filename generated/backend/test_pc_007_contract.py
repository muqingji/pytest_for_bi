from generated.backend._readiness import require_capability


def test_pc_007_chart_and_pivot_entry_consistency_is_ready() -> None:
    require_capability(
        "chart_and_pivot_entry_consistency",
        False,
        "the two historical entry fixtures required by PC-007 are not registered",
    )
