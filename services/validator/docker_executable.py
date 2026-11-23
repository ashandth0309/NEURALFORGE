
"""Resolve the Docker CLI without searching PATH.

Resolution is not verification of executable authenticity.
No Docker commands are executed by this module.
"""

import os
import sys
from pathlib import Path


def resolve_docker_executable() -> str | None:
    """Return an existing absolute Docker CLI path or None."""

    configured = os.environ.get(
        "NEURALFORGE_DOCKER_EXECUTABLE"
    )

    if configured is not None:
        if not configured.strip():
            return None
        candidate = Path(configured)
    elif sys.platform == "win32":
        candidate = Path(
            r"C:\Program Files\Docker\Docker"
            r"\resources\bin\docker.exe"
        )
    else:
        candidate = Path("/usr/bin/docker")

    if not candidate.is_absolute():
        return None

    try:
        resolved = candidate.resolve(strict=True)
        if not resolved.is_file():
            return None
        return str(resolved)
    except (OSError, RuntimeError, ValueError):
        return None
