
"""Declarative policy for a future isolated validation worker.

This module does not create or execute containers.
"""

import re
from dataclasses import dataclass


IMAGE_PATTERN = re.compile(
    r"[a-zA-Z0-9][a-zA-Z0-9._/:@-]*"
    r"@sha256:[0-9a-f]{64}"
)


@dataclass(frozen=True)
class IsolationPolicy:
    image: str
    network_disabled: bool = True
    read_only_root: bool = True
    privileged: bool = False
    user: str = "10001:10001"
    memory_mb: int = 512
    cpu_count: int = 1
    pids_limit: int = 64
    timeout_seconds: int = 30
    drop_all_capabilities: bool = True
    no_new_privileges: bool = True
    writable_host_mounts: bool = False


def validate_isolation_policy(
    policy: IsolationPolicy,
) -> IsolationPolicy:
    """Reject policies that violate minimum isolation requirements."""

    if not isinstance(policy, IsolationPolicy):
        raise TypeError("Expected IsolationPolicy")

    if (
        not isinstance(policy.image, str)
        or IMAGE_PATTERN.fullmatch(policy.image) is None
    ):
        raise ValueError("Container image must be digest-pinned")

    if policy.network_disabled is not True:
        raise ValueError("Network access must be disabled")

    if policy.read_only_root is not True:
        raise ValueError("Root filesystem must be read-only")

    if policy.privileged is not False:
        raise ValueError("Privileged execution is forbidden")

    if policy.user != "10001:10001":
        raise ValueError("Unexpected container user")

    if (
        type(policy.memory_mb) is not int
        or not 128 <= policy.memory_mb <= 512
    ):
        raise ValueError("Invalid memory limit")

    if (
        type(policy.cpu_count) is not int
        or policy.cpu_count != 1
    ):
        raise ValueError("Invalid CPU limit")

    if (
        type(policy.pids_limit) is not int
        or not 1 <= policy.pids_limit <= 64
    ):
        raise ValueError("Invalid process limit")

    if (
        type(policy.timeout_seconds) is not int
        or not 1 <= policy.timeout_seconds <= 30
    ):
        raise ValueError("Invalid execution timeout")

    if policy.drop_all_capabilities is not True:
        raise ValueError("Capabilities must be dropped")

    if policy.no_new_privileges is not True:
        raise ValueError("Privilege escalation must be disabled")

    if policy.writable_host_mounts is not False:
        raise ValueError("Writable host mounts are forbidden")

    return policy
