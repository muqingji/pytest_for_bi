from __future__ import annotations

import pytest


def test_data_driven_interface_case(api_case: dict, case_runner) -> None:
    if not api_case.get("enabled", True):
        pytest.skip("Case is disabled in its environment data file")
    case_runner.run(api_case)

