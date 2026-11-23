
"""Validate Docker image inspection metadata without executing Docker.

Metadata must ultimately be obtained from a trusted Docker daemon.
This module does not establish image provenance or authenticity.
"""

import re
from dataclasses import dataclass

from services.validator.image_approval import verify_approved_image
from services.validator.isolation import IsolationPolicy


DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


@dataclass(frozen=True)
class ImageIdentity:
    reference: str
    image_id: str
    os: str
    architecture: str


def verify_image_identity(
    policy: IsolationPolicy,
    approved_images: frozenset[str],
    metadata: dict,
) -> ImageIdentity:
    """Require reported metadata to match an approved image."""

    verify_approved_image(policy, approved_images)

    if not isinstance(metadata, dict):
        raise TypeError("Image metadata must be a dictionary")

    image_id = metadata.get("Id")
    repo_digests = metadata.get("RepoDigests")
    os_name = metadata.get("Os")
    architecture = metadata.get("Architecture")

    if (
        not isinstance(image_id, str)
        or DIGEST_PATTERN.fullmatch(image_id) is None
    ):
        raise ValueError("Invalid Docker image identifier")

    if (
        not isinstance(repo_digests, list)
        or any(not isinstance(x, str) for x in repo_digests)
        or policy.image not in repo_digests
    ):
        raise ValueError("Approved image digest not reported")

    if os_name != "linux":
        raise ValueError("Docker image must target Linux")

    if architecture != "amd64":
        raise ValueError("Docker image must target amd64")

    return ImageIdentity(
        reference=policy.image,
        image_id=image_id,
        os=os_name,
        architecture=architecture,
    )
