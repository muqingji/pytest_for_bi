from generated.backend._readiness import require_capability


def test_pc_006_contract_historical_matrix_is_ready() -> None:
    require_capability(
        "historical_contract_matrix",
        False,
        "historical chart/pivot IDs and frozen configuration hashes are not registered",
    )
