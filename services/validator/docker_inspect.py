
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
    """Inspect an approved image using the local Docker Desktop engine.

    An optional full-length image ID may be used as the lookup
    reference when Docker cannot resolve the repository digest.

    The approved reference and reported image ID are verified
    independently before an ImageIdentity is returned.
    """

    # Validate the isolation policy and operator-approved image
    # before communicating with Docker.
    verify_approved_image(
        policy=policy,
        approved_images=approved_images,
    )

    # Validate any explicitly provided local image ID.
    if expected_image_id is not None:
        if (
            not isinstance(expected_image_id, str)
            or DIGEST_PATTERN.fullmatch(expected_image_id) is None
        ):
            raise ValueError("Invalid expected image ID")

    # Never silently fall back to an unapproved image reference.
    lookup = (
        expected_image_id
        if expected_image_id is not None
        else policy.image
    )

    # Resolve an explicitly selected Docker executable.
    executable = resolve_docker_executable()

    if executable is None:
        raise RuntimeError("docker_unavailable")

    # Remove inherited Docker-specific environment overrides.
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("DOCKER_")
    }

    # Fixed, read-only Docker operation.
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
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=INSPECT_TIMEOUT_SECONDS,
            check=False,
            env=environment,
        )

    except FileNotFoundError as exc:
        raise RuntimeError(
            "docker_unavailable"
        ) from exc

    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "docker_inspection_timeout"
        ) from exc

    except OSError as exc:
        raise RuntimeError(
            "docker_inspection_unavailable"
        ) from exc

    # Docker must complete inspection successfully.
    if result.returncode != 0:
        raise RuntimeError(
            "docker_inspection_failed"
        )

    # This checks captured output size after execution.
    # It is not a strict subprocess memory limit.
    if len(result.stdout) > MAX_INSPECT_OUTPUT_BYTES:
        raise RuntimeError(
            "docker_inspection_output_too_large"
        )

    # Parse Docker's JSON response.
    try:
        metadata = json.loads(result.stdout)

    except (ValueError, UnicodeError) as exc:
        raise RuntimeError(
            "docker_inspection_invalid_json"
        ) from exc

    # IMPORTANT:
    # This block must be OUTSIDE the except clause.
    # Valid JSON must always undergo image identity checks.
    identity = verify_image_identity(
        policy=policy,
        approved_images=approved_images,
        metadata=metadata,
    )

    # Ensure the actual inspected image matches the
    # explicitly requested image ID.
    if (
        expected_image_id is not None
        and identity.image_id != expected_image_id
    ):
        raise ValueError(
            "Docker image ID mismatch"
        )

    return identity
