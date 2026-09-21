"""测试数据绑定回查脚本自检。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


CHECKER = (
    Path(__file__).resolve().parents[2]
    / "dev-tools"
    / "skills"
    / "test-data-construction"
    / "scripts"
    / "check_test_data_binding.py"
)


def _write_project(root: Path, *, request_user: str = "case-eval-001") -> None:
    cases_dir = root / "tests" / "cases"
    fixtures_dir = root / "testenv" / "fixtures"
    cases_dir.mkdir(parents=True)
    fixtures_dir.mkdir(parents=True)
    (cases_dir / "evaluate.json").write_text(
        json.dumps(
            {
                "subject": "evaluate",
                "endpoint": {"method": "POST", "path": "/evaluate"},
                "cases": [
                    {
                        "id": "EVAL-001",
                        "name": "绑定数据",
                        "scenario": {"fixture": "case-eval-001"},
                        "test_data": {
                            "fixture": "case-eval-001",
                            "request": {"user_id": request_user, "task_date": "2026-09-20"},
                        },
                        "request": {"body": "{data.request}"},
                        "expected": {"status_code": 200, "body": {}},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (fixtures_dir / "users.json").write_text(
        json.dumps(
            {
                "users": [
                    {
                        "user_id": "case-eval-001",
                        "task_template": "PENDING",
                        "covers": ["EVAL-001"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _run_checker(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--project-root", str(root), "--case-id", "EVAL-001"],
        check=False,
        capture_output=True,
        text=True,
    )


def test_binding_checker_accepts_case_owned_fixture_and_runtime_request(tmp_path: Path) -> None:
    _write_project(tmp_path)

    result = _run_checker(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "阻塞项：0" in result.stdout


def test_binding_checker_rejects_request_user_different_from_fixture(tmp_path: Path) -> None:
    _write_project(tmp_path, request_user="another-user")

    result = _run_checker(tmp_path)

    assert result.returncode == 1
    assert "与绑定 Fixture 'case-eval-001' 不一致" in result.stdout
