"""Resolution of the multica CLI executable across runtime environments.

launchd LaunchAgents inherit a minimal PATH (/usr/bin:/bin:/usr/sbin:/sbin)
that does not include /usr/local/bin or /opt/homebrew/bin. Every subprocess
driver that shells out to ``multica`` must resolve the binary explicitly,
otherwise the unattended timer dies on FileNotFoundError at its first call
and the workflow only advances when someone runs the sync manually from a
shell with a fuller PATH.
"""

from __future__ import annotations

import os
import shutil


MULTICA_FALLBACK_PATHS = ("/usr/local/bin/multica", "/opt/homebrew/bin/multica")


def resolve_multica_binary() -> str:
    """Return the multica CLI path, falling back to common install locations."""

    resolved = shutil.which("multica")
    if not resolved:
        for candidate in MULTICA_FALLBACK_PATHS:
            if os.path.exists(candidate):
                resolved = candidate
                break
    if not resolved:
        raise RuntimeError("multica CLI not found on PATH")
    return resolved
