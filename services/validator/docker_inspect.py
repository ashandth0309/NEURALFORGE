
"""Read-only Docker image inspection with fail-closed validation.

This module invokes only `docker image inspect`.
It does not start containers or execute project code.
"""

import json
import os
import subprocess

from services.validator.bounded_capture import (
    BoundedOutputError,
    BoundedProcessTimeout,
    run_bounded,
)
from services.validator.docker_executable import (
    resolve_docker_executable,
)
from services.validator.image_approval import (
    verify_approved_image,
)
from services.validator.image_identity import (
    DIGEST_PATTERN,
    ImageIdentity,
    verify_image_identity,
)
from services.validator.isolation import IsolationPolicy


INSPECT_TIMEOUT_SECONDS = 10
MAX_INSPECT_OUTPUT_BYTES = 65536


def inspect_approved_image(
    policy: IsolationPolicy,
    approved_images: frozenset[str],
    expected_image_id: str | None = None,
) -> ImageIdentity:
    """Inspect a locally available, approved Docker image."""

    verify_approved_image(
        policy=policy,
        approved_images=approved_images,
    )

    if expected_image_id is not None:
        if (
            not isinstance(expected_image_id, str)
            or DIGEST_PATTERN.fullmatch(expected_image_id) is None
        ):
            raise ValueError("Invalid expected image ID")

    lookup = (
        expected_image_id
        if expected_image_id is not None
        else policy.image
    )

    executable = resolve_docker_executable()

    if executable is None:
        raise RuntimeError("docker_unavailable")

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
        lookup,
    ]

    try:
        result = run_bounded(
            command,
            env=environment,
            timeout_seconds=INSPECT_TIMEOUT_SECONDS,
            max_output_bytes=MAX_INSPECT_OUTPUT_BYTES,
        )

    except BoundedOutputError as exc:
        raise RuntimeError(
            "docker_inspection_output_too_large"
        ) from exc

    except (BoundedProcessTimeout, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(
            "docker_inspection_timeout"
        ) from exc

    except FileNotFoundError as exc:
        raise RuntimeError(
            "docker_unavailable"
        ) from exc

    except OSError as exc:
        raise RuntimeError(
            "docker_inspection_unavailable"
        ) from exc

    if result.returncode != 0:
        raise RuntimeError(
            "docker_inspection_failed"
        )

    # Defensive check for unexpected runner behavior.
    if len(result.stdout) > MAX_INSPECT_OUTPUT_BYTES:
        raise RuntimeError(
            "docker_inspection_output_too_large"
        )

    try:
        metadata = json.loads(result.stdout)
    except (ValueError, UnicodeError) as exc:
        raise RuntimeError(
            "docker_inspection_invalid_json"
        ) from exc

    identity = verify_image_identity(
        policy=policy,
        approved_images=approved_images,
        metadata=metadata,
    )

    if (
        expected_image_id is not None
        and identity.image_id != expected_image_id
    ):
        raise ValueError(
            "Docker image ID mismatch"
        )

    return identity
