from __future__ import annotations

import pytest

from tests.test_112_customer_custom_dimension_lifecycle import (
    run_customer_custom_dimension_case,
)


@pytest.mark.parametrize(
    ("placement", "locale"),
    [
        ("dimension", "zh-CN"),
        ("dimension", "en"),
        ("data_range", "zh-CN"),
        ("data_range", "en"),
        ("drill_field", "zh-CN"),
        ("drill_field", "en"),
    ],
)
def test_pc_001_contract_custom_dimension(
    environment, case_runner, placement, locale
) -> None:
    if environment.name != "112":
        pytest.skip("PC-001 contract automation runs only with --env=112")
    run_customer_custom_dimension_case(case_runner, [(placement, locale)])
