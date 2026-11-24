
"""Validate observations from a fixed Docker runtime probe.

This module does not execute Docker, establish provenance,
or authorize execution of untrusted code.
"""

import json
import re

from services.validator.execution_gate import (
    RuntimeSecurityEvidence,
)
from services.validator.isolation import (
    IsolationPolicy,
    validate_isolation_policy,
)


def parse_runtime_probe(
    output: bytes,
    policy: IsolationPolicy,
) -> RuntimeSecurityEvidence:
    """Fail closed unless every required observation matches."""

    validate_isolation_policy(policy)

    if not isinstance(output, bytes) or len(output) > 8192:
        raise ValueError("invalid_runtime_probe_output")

    try:
        data = json.loads(output)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("invalid_runtime_probe_json") from exc

    if not isinstance(data, dict):
        raise ValueError("invalid_runtime_probe_structure")

    expected_user = tuple(
        int(part) for part in policy.user.split(":")
    )

    def exact_int(name, expected):
        value = data.get(name)
        return type(value) is int and value == expected

    status = data.get("status")
    if not isinstance(status, dict):
        raise ValueError("runtime_status_missing")

    if (
        not exact_int("uid", expected_user[0])
        or not exact_int("gid", expected_user[1])
    ):
        raise ValueError("runtime_user_mismatch")

    def exact_status(name, value):
        return status.get(name) == value

    seccomp_ok = (
        exact_status("Seccomp", "2")
        and isinstance(status.get("Seccomp_filters"), str)
        and status["Seccomp_filters"].isdigit()
        and int(status["Seccomp_filters"]) >= 1
    )

    capabilities_ok = (
        exact_status("CapEff", "0000000000000000")
        and exact_status("CapBnd", "0000000000000000")
    )

    privileges_ok = exact_status("NoNewPrivs", "1")

    interfaces = data.get("interfaces")
    network_ok = interfaces == ["lo"]

    filesystem_ok = (
        data.get("filesystem_write_error") == "EROFS"
    )

    
    def strict_positive_integer(name):
        value = data.get(name)

        if (
            type(value) is not str
            or re.fullmatch(r"[1-9][0-9]{0,19}", value)
            is None
        ):
            return None

        return int(value)

    memory = strict_positive_integer("memory")
    quota = strict_positive_integer("cpuQuota")
    period = strict_positive_integer("cpuPeriod")
    pids = strict_positive_integer("pids")

    resources_ok = (
        memory == policy.memory_mb * 1024 * 1024
        and quota is not None
        and period is not None
        and quota == period * policy.cpu_count
        and pids == policy.pids_limit
    )


    evidence = RuntimeSecurityEvidence(
        seccomp_enforced=seccomp_ok,
        network_disabled=network_ok,
        read_only_root=filesystem_ok,
        capabilities_dropped=capabilities_ok,
        resource_limits_enforced=resources_ok,
        no_new_privileges=privileges_ok,
    )

    if not all(vars(evidence).values()):
        raise ValueError("runtime_probe_verification_failed")

    return evidence
