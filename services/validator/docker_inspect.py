
"""Read-only Docker image inspection with fail-closed validation.

This module invokes only `docker image inspect`.
It never starts containers or executes project code.
"""

import json
import os
import subprocess

from services.validator.docker_executable import (
    resolve_docker_executable,
)
from services.validator.image_approval import (
    verify_approved_image,
)
from services.validator.image_identity import (
    ImageIdentity,
    verify_image_identity,
)
from services.validator.isolation import IsolationPolicy


INSPECT_TIMEOUT_SECONDS = 10
MAX_INSPECT_OUTPUT_BYTES = 65536


def inspect_approved_image(
    policy: IsolationPolicy,
    approved_images: frozenset[str],
) -> ImageIdentity:
    """Inspect an approved image on the local Docker Desktop engine."""

    # Reject invalid policies and unapproved images first.
    verify_approved_image(policy, approved_images)

    executable = resolve_docker_executable()

    if executable is None:
        raise RuntimeError("docker_unavailable")

    # Do not inherit Docker daemon-selection overrides.
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("DOCKER_")
    }

    command = [
        executable,
        "--context",
        "desktop-linux",
        "image",
        "inspect",
        "--format",
        "{{json .}}",
        policy.image,
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=INSPECT_TIMEOUT_SECONDS,
            check=False,
            env=environment,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("docker_unavailable") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("docker_inspection_timeout") from exc
    except OSError as exc:
        raise RuntimeError("docker_inspection_unavailable") from exc

    if result.returncode != 0:
        raise RuntimeError("docker_inspection_failed")

    # A size check after subprocess.run is not a strict
    # process-output memory bound. That requires a future
    # streaming or pipe-limited execution adapter.
    if len(result.stdout) > MAX_INSPECT_OUTPUT_BYTES:
        raise RuntimeError("docker_inspection_output_too_large")

    try:
        metadata = json.loads(result.stdout)
    except (ValueError, UnicodeError) as exc:
        raise RuntimeError("docker_inspection_invalid_json") from exc

    return verify_image_identity(
        policy=policy,
        approved_images=approved_images,
        metadata=metadata,
    )
