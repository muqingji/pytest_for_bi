#!/usr/bin/env python3
"""Read fs-bi from a remote mirror and regenerate this repository's BI API artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


REMOTE = "git@git.firstshare.cn:bi/fs-bi.git"


def run(command: list[str], *, cwd: Path, capture: bool = False) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout.strip() if capture else ""


def project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def update_mirror(root: Path, mirror: Path) -> None:
    if mirror.exists():
        if not (mirror / "HEAD").is_file():
            raise RuntimeError(f"Refusing to replace invalid mirror path: {mirror}")
        origin = run(["git", "--git-dir", str(mirror), "remote", "get-url", "origin"], cwd=root, capture=True)
        if origin != REMOTE:
            raise RuntimeError(f"Mirror origin mismatch: expected {REMOTE}, got {origin}")
        run(
            ["git", "--git-dir", str(mirror), "fetch", "--prune", "origin", "+refs/heads/*:refs/heads/*", "+refs/tags/*:refs/tags/*"],
            cwd=root,
        )
        return
    mirror.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "clone", "--mirror", REMOTE, str(mirror)], cwd=root)


def resolve_commit(root: Path, mirror: Path, ref: str) -> str:
    candidates = [f"refs/heads/{ref}", f"refs/tags/{ref}", ref]
    for candidate in candidates:
        try:
            return run(
                ["git", "--git-dir", str(mirror), "rev-parse", "--verify", f"{candidate}^{{commit}}"],
                cwd=root,
                capture=True,
            )
        except subprocess.CalledProcessError:
            continue
    raise RuntimeError(f"Remote revision not found: {ref}")


def extract_snapshot(root: Path, mirror: Path, commit: str, destination: Path) -> None:
    archive = destination.parent / "fs-bi.tar"
    run(["git", "--git-dir", str(mirror), "archive", "--format=tar", "-o", str(archive), commit], cwd=root)
    with tarfile.open(archive) as source:
        source.extractall(destination, filter="data")


def verify_routes(root: Path) -> int:
    idl = root / "idl/http/generated/fs-bi/fs-bi-stat.openapi.json"
    document = json.loads(idl.read_text(encoding="utf-8"))
    paths = document.get("paths", {})
    prefix = "/FHH/EM1HBISTAT/fs-bi-stat"
    invalid = [path for path in paths if not path.startswith(prefix) or ".java" in path]
    if invalid:
        raise RuntimeError(f"Invalid generated external routes: {invalid[:5]}")
    return len(paths)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="master", help="Remote branch, tag, or commit (default: master)")
    parser.add_argument("--mirror", type=Path, help="Override the local bare mirror cache")
    parser.add_argument("--skip-tests", action="store_true", help="Skip pytest; compilation and route checks still run")
    args = parser.parse_args()

    root = project_root()
    mirror = (args.mirror or root / ".cache/fs-bi-api-source.git").resolve()
    update_mirror(root, mirror)
    commit = resolve_commit(root, mirror, args.ref)

    with tempfile.TemporaryDirectory(prefix="fs-bi-api-sync-") as temporary:
        source = Path(temporary) / "fs-bi"
        source.mkdir()
        extract_snapshot(root, mirror, commit, source)
        run([sys.executable, "scripts/sync_fs_bi_http_api.py", "--source", str(source)], cwd=root)

    run([sys.executable, "-m", "compileall", "-q", "src/framework/api/generated/fs_bi", "scripts/sync_fs_bi_http_api.py"], cwd=root)
    endpoint_count = verify_routes(root)
    if not args.skip_tests:
        run([sys.executable, "-m", "pytest", "tests/test_fs_bi_http_generator.py", "-q"], cwd=root)

    changed = run(["git", "status", "--short", "--", "idl/http/generated/fs-bi", "src/framework/api/generated/fs_bi"], cwd=root, capture=True)
    print(f"remote={REMOTE}")
    print(f"commit={commit}")
    print(f"callable_modules=1 callable_endpoints={endpoint_count}")
    print("excluded_modules=fs-bi-devops,fs-bi-metadata,fs-bi-metadata-ant,fs-bi-mq,fs-bi-sqlengine,fs-bi-sqlgenerator,fs-bi-task,fs-bi-transfer")
    print("changed_files:")
    print(changed or "(none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
