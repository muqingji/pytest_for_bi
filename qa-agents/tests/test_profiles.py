import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_implemented_profiles_have_unique_ids_and_no_write_access() -> None:
    profiles = []
    for path in sorted((ROOT / "profiles").glob("*.json")):
        with path.open(encoding="utf-8") as file:
            profiles.append(json.load(file))

    assert {profile["agent_id"] for profile in profiles} == {
        "A01",
        "A02",
        "A03",
        "A04",
        "A05",
        "A06",
        "A07",
        "A08",
        "A09",
        "A11",
        "A12",
        "A13",
        "A14",
        "A15",
        "A16",
        "A17-PERF",
        "A17-SEC",
        "A17-A11Y",
        "A17-COMPAT",
        "A17-RES",
        "A17-DATA",
        "A18-FE",
        "A18-BE",
        "A18-CT",
        "A18-E2E",
        "A18-PERF",
        "A18-SEC",
        "A18-A11Y",
        "A18-COMPAT",
        "A18-RES",
        "A18-DATA",
    }
    assert len({profile["name"] for profile in profiles}) == len(profiles)
    assert all(profile["repository_access"]["write"] == [] for profile in profiles)
    assert all(profile["output_contract"] for profile in profiles)


def test_a09_explicitly_denies_evaluation_oracle() -> None:
    with (ROOT / "profiles" / "a09-oracle-coverage-reviewer.json").open(
        encoding="utf-8"
    ) as file:
        profile = json.load(file)
    assert profile["forbidden_inputs"] == ["evaluation_oracle_registry"]
