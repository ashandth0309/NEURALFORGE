
"""Validate Docker probe container inspection metadata.

This module does not execute Docker or containers.
Inspection data must come from a trusted Docker daemon.
"""

import re

from services.validator.docker_probe_commands import (
    NAME_PATTERN,
    PROBE_SCRIPT,
)
from services.validator.image_identity import DIGEST_PATTERN
from services.validator.isolation import (
    IsolationPolicy,
    validate_isolation_policy,
)


CONTAINER_ID_PATTERN = re.compile(r"[0-9a-f]{64}")


def verify_probe_container(
    metadata: dict,
    *,
    policy: IsolationPolicy,
    expected_image_id: str,
    expected_name: str,
    expected_container_id: str,
) -> str:
    """Validate a stopped probe's identity and Docker configuration."""

    validate_isolation_policy(policy)

    if (
        not isinstance(expected_image_id, str)
        or DIGEST_PATTERN.fullmatch(expected_image_id) is None
    ):
        raise ValueError("invalid_expected_image_id")

    if (
        not isinstance(expected_name, str)
        or NAME_PATTERN.fullmatch(expected_name) is None
    ):
        raise ValueError("invalid_expected_container_name")

    if (
        not isinstance(expected_container_id, str)
        or CONTAINER_ID_PATTERN.fullmatch(expected_container_id) is None
    ):
        raise ValueError("invalid_expected_container_id")

    if not isinstance(metadata, dict):
        raise ValueError("invalid_container_metadata")

    if metadata.get("Id") != expected_container_id:
        raise ValueError("container_id_mismatch")

    if metadata.get("Image") != expected_image_id:
        raise ValueError("container_image_mismatch")

    if metadata.get("Name") != "/" + expected_name:
        raise ValueError("container_name_mismatch")

    config = metadata.get("Config")
    host = metadata.get("HostConfig")
    state = metadata.get("State")

    if not all(
        isinstance(item, dict)
        for item in (config, host, state)
    ):
        raise ValueError("incomplete_container_metadata")

    if (
        state.get("Status") != "created"
        or state.get("Running") is not False
    ):
        raise ValueError("container_not_stopped")

    if config.get("User") != policy.user:
        raise ValueError("container_user_mismatch")

    if config.get("Entrypoint") != [
        "/usr/local/bin/node"
    ]:
        raise ValueError("container_entrypoint_mismatch")

    if config.get("Cmd") != ["-e", PROBE_SCRIPT]:
        raise ValueError("container_command_mismatch")

    required_host_settings = {
        "CgroupnsMode": "private",
        "NetworkMode": "none",
        "ReadonlyRootfs": True,
        "Privileged": False,
        "Memory": policy.memory_mb * 1024 * 1024,
        "MemorySwap": policy.memory_mb * 1024 * 1024,
        "NanoCpus": policy.cpu_count * 1_000_000_000,
        "PidsLimit": policy.pids_limit,
        "Init": True,
    }

    for key, expected in required_host_settings.items():
        actual = host.get(key)

        if type(actual) is not type(expected) or actual != expected:
            raise ValueError(
                f"container_configuration_mismatch:{key}"
            )

    if host.get("CapDrop") != ["ALL"]:
        raise ValueError("container_capabilities_mismatch")

    security_options = host.get("SecurityOpt")

    if (
        not isinstance(security_options, list)
        or len(security_options) != 2
        or set(security_options) != {
            "no-new-privileges=true",
            "seccomp=builtin",
        }
    ):
        raise ValueError("container_security_options_mismatch")

    if metadata.get("Mounts") != []:
        raise ValueError("unexpected_container_mounts")

    for field in ("Binds", "Mounts", "Devices"):
        if host.get(field) not in (None, []):
            raise ValueError(
                f"unexpected_container_host_setting:{field}"
            )

    return expected_container_id
