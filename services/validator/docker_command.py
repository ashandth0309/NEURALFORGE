
"""Construct restricted Docker commands without executing them."""

from services.validator.isolation import (
    IsolationPolicy,
    validate_isolation_policy,
)


def build_docker_command(
    policy: IsolationPolicy,
) -> tuple[str, ...]:
    """Build a non-executing, mount-free Docker smoke-test command.

    A caller must not execute this command against untrusted
    images without additional security review.
    """

    validate_isolation_policy(policy)

    return (
        "docker",
        "run",
        "--rm",
        "--pull",
        "never",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges=true",
        "--memory",
        f"{policy.memory_mb}m",
        "--memory-swap",
        f"{policy.memory_mb}m",
        "--cpus",
        str(policy.cpu_count),
        "--pids-limit",
        str(policy.pids_limit),
        "--user",
        policy.user,
        "--init",
        "--entrypoint",
        "/usr/local/bin/node",
        policy.image,
        "--version",
    )
