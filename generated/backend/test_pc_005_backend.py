from __future__ import annotations

import pytest

from generated.backend._readiness import require_capability
from tests.test_112_customer_custom_dimension_lifecycle import (
    run_customer_custom_dimension_case,
)


def test_pc_005_backend_supported_priority(environment, case_runner) -> None:
    if environment.name != "112":
        pytest.skip("PC-005 backend automation runs only with --env=112")
    run_customer_custom_dimension_case(
        case_runner, [("data_range", "zh-CN")], combine_result_set_filter=True
    )


@pytest.mark.parametrize(
    ("capability", "reason"),
    [
        ("all_four_without_permission", "112 has no configured limited/no-permission identity"),
        ("candidate_plus_parameter_error", "no allowlisted fault-injection hook is configured"),
        ("candidate_plus_timeout", "no allowlisted timeout-injection hook is configured"),
        ("candidate_plus_metadata_error", "no allowlisted metadata-fault hook is configured"),
    ],
)
def test_pc_005_backend_required_controlled_capability(capability, reason) -> None:
    require_capability(capability, False, reason)
