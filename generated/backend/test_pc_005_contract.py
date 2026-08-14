from __future__ import annotations

import pytest

from generated.backend.test_pc_001_contract import run_retained_custom_dimension_case


@pytest.mark.parametrize("locale", ["zh-CN", "en"])
def test_pc_005_custom_dimension_precedes_result_set_filter(
    environment, case_runner, locale
) -> None:
    if environment.name != "112":
        pytest.skip("PC-005 contract automation runs only with --env=112")
    run_retained_custom_dimension_case(
        case_runner, "data_range", locale, combine_result_set_filter=True)
