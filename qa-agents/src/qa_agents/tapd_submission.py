"""TAPD story branching and approved automation-repository submission."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import subprocess
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any
from collections.abc import Mapping

from .contracts import content_hash
from .errors import ContractError, InputError, SecurityPolicyError


@dataclass(frozen=True)
class GitResult:
    returncode: int
    stdout: str
    stderr: str


def extract_tapd_story_id(story_reference: str) -> str:
    """Extract the short visible TAPD story ID from a link or pasted card."""

    text = story_reference.strip()
    if not text:
        raise InputError("TAPD story reference is empty")

    explicit = re.search(r"(?:story[_ -]?id|需求\s*ID)\s*[:：]\s*(\d{4,})", text, re.IGNORECASE)
    if explicit:
        return explicit.group(1)
    explicit = re.search(r"\bID\s*[:：]\s*(\d{4,})", text, re.IGNORECASE)
    if explicit:
        return explicit.group(1)

    query = re.search(r"[?&](?:story[_ -]?id)=(\d{4,})", text, re.IGNORECASE)
    if query:
        return query.group(1)

    detail = re.search(r"/story/detail/(\d{10,})", text)
    workspace = re.search(r"/(\d{6,})/story/detail/", text)
    if detail and workspace:
        encoded_id = detail.group(1)
        workspace_id = workspace.group(1)
        prefix = f"112{workspace_id[1:]}00"
        if encoded_id.startswith(prefix) and len(encoded_id) > len(prefix):
            return encoded_id[len(prefix):]
        raise InputError(
            "Cannot derive the visible TAPD story ID from this URL; paste the card text containing 'ID: xxx'"
        )
    raise InputError("TAPD story ID is missing")


def tapd_branch_name(story_id: str) -> str:
    return f"qa/tapd-story-{story_id}"


def _git(repository: Path, *arguments: str) -> GitResult:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        shell=False,
        check=False,
    )
    return GitResult(completed.returncode, completed.stdout, completed.stderr)


def _git_ok(repository: Path, *arguments: str) -> str:
    result = _git(repository, *arguments)
    if result.returncode != 0:
        raise SecurityPolicyError(
            f"git {' '.join(arguments)} failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def _load_config(path: Path) -> dict[str, Any]:
    import json

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InputError(f"Repository config is missing: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"Repository config is invalid: {path}") from error
    if not isinstance(value, dict) or value.get("schema_version") != "test-repository-config/1.0":
        raise ContractError("Repository config must use test-repository-config/1.0")
    for field in ("repository_id", "repository_path", "base_ref", "access_class"):
        if not str(value.get(field, "")).strip():
            raise ContractError(f"Repository config is missing {field}")
    if value.get("access_class") != "approved_test_repository":
        raise SecurityPolicyError("Test candidates require access_class=approved_test_repository")
    return value


def _landing_files(landing_path: Path) -> list[dict[str, Any]]:
    import json

    try:
        artifact = json.loads(landing_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"Landing Artifact is invalid: {landing_path}") from error
    if (
        not isinstance(artifact, dict)
        or artifact.get("producer", {}).get("component_id") != "N29"
        or artifact.get("payload", {}).get("schema_version") != "n29-candidate-landing/1.0"
        or artifact.get("status") != "completed"
    ):
        raise ContractError("Submission requires a completed N29 landing Artifact")
    files = artifact["payload"].get("landed_files", [])
    if not isinstance(files, list) or not files:
        raise ContractError("Landing Artifact has no landed files")
    for item in files:
        if not isinstance(item, dict) or not item.get("path") or not item.get("content_hash"):
            raise ContractError("Landing file binding is incomplete")
    return files


def _write_landing_file(root: Path, item: Mapping[str, Any]) -> None:
    relative = PurePosixPath(str(item["path"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise SecurityPolicyError(f"Landing path escapes repository: {item['path']}")
    target = root.joinpath(*relative.parts)
    source = Path(str(item["absolute_path"]))
    if not source.is_file():
        raise InputError(f"Landed candidate is unavailable: {source}")
    content = source.read_text(encoding="utf-8")
    if content_hash(content) != item["content_hash"]:
        raise ContractError(f"Landing content drifted before submission: {item['path']}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    if content_hash(target.read_text(encoding="utf-8")) != item["content_hash"]:
        raise ContractError(f"Submitted content changed while writing: {item['path']}")


def submit_test_candidates(
    story_reference: str,
    landing_path: Path,
    repository_config_path: Path,
    output_path: Path,
    *,
    committer_name: str = "QA Agent",
    committer_email: str = "qa-agent@example.invalid",
) -> dict[str, Any]:
    """Create or reuse one branch per TAPD story and commit hash-bound candidates."""

    story_id = extract_tapd_story_id(story_reference)
    branch = tapd_branch_name(story_id)
    config = _load_config(repository_config_path)
    repository = Path(str(config["repository_path"])).expanduser().resolve()
    if not (repository / ".git").exists():
        raise InputError(f"Configured repository is not a Git worktree: {repository}")
    base_ref = str(config["base_ref"])
    files = _landing_files(landing_path)

    if _git(repository, "status", "--porcelain").stdout.strip():
        raise SecurityPolicyError("Refusing to submit from a dirty Git worktree")
    _git_ok(repository, "rev-parse", "--verify", base_ref)
    branch_exists = _git(repository, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}").returncode == 0
    if not branch_exists:
        _git_ok(repository, "branch", branch, base_ref)
    start_point = branch
    worktree = repository / ".qa-worktrees" / f"tapd-story-{story_id}"
    worktree.parent.mkdir(parents=True, exist_ok=True)
    if worktree.exists():
        raise SecurityPolicyError(f"Submission worktree already exists: {worktree}")
    _git_ok(repository, "worktree", "add", str(worktree), start_point)
    try:
        current = _git_ok(worktree, "branch", "--show-current")
        if current != branch:
            raise ContractError(f"Submission worktree is not on {branch}")
        for item in files:
            _write_landing_file(worktree, item)
        relative_paths = [str(item["path"]) for item in files]
        status = _git(worktree, "status", "--porcelain", "--", *relative_paths).stdout.strip()
        commit_hash = None
        if status:
            _git_ok(worktree, "add", "--", *relative_paths)
            _git_ok(
                worktree,
                "-c", f"user.name={committer_name}",
                "-c", f"user.email={committer_email}",
                "commit",
                "-m", f"test: add QA candidates for TAPD story {story_id}",
            )
            commit_hash = _git_ok(worktree, "rev-parse", "HEAD")
        else:
            commit_hash = _git_ok(worktree, "rev-parse", "HEAD")

        pushed = False
        remote = str(config.get("remote", "")).strip()
        if bool(config.get("push")):
            if not remote:
                raise ContractError("Repository config sets push=true but has no remote")
            _git_ok(worktree, "push", remote, branch)
            pushed = True

        payload: dict[str, Any] = {
            "schema_version": "tapd-test-submission/1.0",
            "tapd_story_id": story_id,
            "branch": branch,
            "repository_id": str(config["repository_id"]),
            "base_ref": base_ref,
            "branch_existed": branch_exists,
            "commit_hash": commit_hash,
            "pushed": pushed,
            "push_mode": "explicit_config" if pushed else "local_only",
            "submitted_files": [
                {"path": str(item["path"]), "content_hash": str(item["content_hash"])}
                for item in files
            ],
            "submission_hash": content_hash(files),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "storage_repository_disposition": {
                "current": str(config.get("purpose", "current_shared_repository")),
                "dedicated_results_repository_required": bool(
                    config.get("dedicated_results_repository_todo", True)
                ),
                "todo": "Replace repository_path with a dedicated test-results repository when provisioned.",
            },
        }
        import json

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return payload
    finally:
        if worktree.exists():
            _git(worktree, "reset", "--hard", "HEAD")
        _git_ok(repository, "worktree", "remove", "--force", str(worktree))
        worktree.parent.rmdir()
