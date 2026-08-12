from __future__ import annotations

import pytest

from tests.test_112_customer_custom_dimension_lifecycle import (
    run_customer_custom_dimension_case,
)


@pytest.mark.parametrize("locale", ["zh-CN", "en"])
def test_pc_005_custom_dimension_precedes_result_set_filter(
    environment, case_runner, locale
) -> None:
    if environment.name != "112":
        pytest.skip("PC-005 contract automation runs only with --env=112")
    run_customer_custom_dimension_case(
        case_runner,
        [("data_range", locale)],
        combine_result_set_filter=True,
    )
