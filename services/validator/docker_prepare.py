
"""Prepare approved Docker commands without executing containers.

This module does not invoke subprocesses or communicate with Docker.
"""

from services.validator.docker_command import (
    build_docker_command,
)
from services.validator.docker_executable import (
    resolve_docker_executable,
)
from services.validator.image_approval import (
    verify_approved_image,
)
from services.validator.isolation import IsolationPolicy


def prepare_docker_command(
    policy: IsolationPolicy,
    approved_images: frozenset[str],
) -> tuple[str, ...]:
    """Construct a command only after all prerequisites pass.

    Approval data must originate from trusted operator configuration.
    """

    # Fail closed if the isolation policy or image is unacceptable.
    verify_approved_image(
        policy=policy,
        approved_images=approved_images,
    )

    # Fail closed if the executable cannot be resolved.
    executable = resolve_docker_executable()

    if executable is None:
        raise RuntimeError(
            "Docker executable is unavailable"
        )

    # Generate the restricted, non-executing command.
    command = build_docker_command(policy)

    # Replace the PATH-dependent executable with the
    # explicitly resolved absolute executable path.
    return (executable, *command[1:])
