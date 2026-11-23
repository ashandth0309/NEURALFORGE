
"""Fail-closed approval of container image references.

This module does not communicate with Docker, download
images, or execute containers.

Approved references must come from trusted operator
configuration, not untrusted repository input.
"""

from services.validator.isolation import (
    IsolationPolicy,
    validate_isolation_policy,
)


def verify_approved_image(
    policy: IsolationPolicy,
    approved_images: frozenset[str],
) -> IsolationPolicy:
    """Require an exact match with an operator-approved image."""

    validate_isolation_policy(policy)

    if not isinstance(approved_images, frozenset):
        raise TypeError(
            "Approved images must be a frozenset"
        )

    if not approved_images:
        raise ValueError(
            "No container images have been approved"
        )

    if any(
        not isinstance(image, str)
        or not image
        for image in approved_images
    ):
        raise ValueError(
            "Approved image references must be strings"
        )

    if policy.image not in approved_images:
        raise ValueError(
            "Container image is not approved"
        )

    return policy
