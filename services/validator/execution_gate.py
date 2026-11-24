
"""Fail-closed execution eligibility gate.

This module performs no subprocess or Docker operations.
It evaluates verification evidence only.

An eligible result is not authorization to execute
untrusted code until runtime isolation is implemented
and independently verified.
"""

from dataclasses import dataclass

from services.validator.image_identity import ImageIdentity
from services.validator.isolation import (
    IsolationPolicy,
    validate_isolation_policy,
)
from services.validator.image_approval import (
    verify_approved_image,
)


@dataclass(frozen=True)
class RuntimeSecurityEvidence:
    """Results supplied by a future trusted runtime verifier."""

    seccomp_enforced: bool = False
    network_disabled: bool = False
    read_only_root: bool = False
    capabilities_dropped: bool = False
    resource_limits_enforced: bool = False
    no_new_privileges: bool = False


def validate_execution_eligibility(
    policy: IsolationPolicy,
    approved_images: frozenset[str],
    image_identity: ImageIdentity,
    runtime: RuntimeSecurityEvidence,
) -> None:
    """Reject incomplete or inconsistent verification evidence.

    This is a data-consistency gate, not an attestation
    mechanism or permission to launch containers.
    """

    validate_isolation_policy(policy)
    verify_approved_image(policy, approved_images)

    if not isinstance(image_identity, ImageIdentity):
        raise ValueError("image_identity_missing")

    if image_identity.reference != policy.image:
        raise ValueError("image_identity_mismatch")

    if image_identity.os != "linux":
        raise ValueError("unsupported_image_os")

    if image_identity.architecture != "amd64":
        raise ValueError("unsupported_image_architecture")

    if not isinstance(runtime, RuntimeSecurityEvidence):
        raise ValueError("runtime_evidence_missing")

    required_controls = (
        "seccomp_enforced",
        "network_disabled",
        "read_only_root",
        "capabilities_dropped",
        "resource_limits_enforced",
        "no_new_privileges",
    )

    for control in required_controls:
        if getattr(runtime, control) is not True:
            raise ValueError(
                f"runtime_control_unverified:{control}"
            )
