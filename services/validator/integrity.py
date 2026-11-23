
"""Deterministic, read-only patch content verification."""

import hashlib
from dataclasses import dataclass

from services.indexer.indexer import MAX_FILE_SIZE
from services.validator.policy import ValidationPlan


@dataclass(frozen=True)
class IntegrityResult:
    """Immutable result of validating proposed source bytes."""

    check: str
    passed: bool
    reason: str
    original_sha256: str
    proposed_sha256: str


def verify_patch_integrity(
    plan: ValidationPlan,
    original_content: bytes,
    proposed_content: bytes,
) -> IntegrityResult:
    """Verify source digests without reading or writing files."""

    if not isinstance(plan, ValidationPlan):
        raise TypeError("Expected ValidationPlan")

    if "patch_integrity" not in plan.checks:
        raise ValueError("Patch integrity check not authorized")

    if not isinstance(original_content, bytes):
        raise TypeError("Original content must be bytes")

    if not isinstance(proposed_content, bytes):
        raise TypeError("Proposed content must be bytes")

    original_digest = hashlib.sha256(
        original_content
    ).hexdigest()

    proposed_digest = hashlib.sha256(
        proposed_content
    ).hexdigest()

    def result(passed: bool, reason: str) -> IntegrityResult:
        return IntegrityResult(
            check="patch_integrity",
            passed=passed,
            reason=reason,
            original_sha256=original_digest,
            proposed_sha256=proposed_digest,
        )

    if (
        len(original_content) > MAX_FILE_SIZE
        or len(proposed_content) > MAX_FILE_SIZE
    ):
        return result(False, "size_limit_exceeded")

    if original_digest != plan.original_sha256:
        return result(False, "original_digest_mismatch")

    if proposed_digest != plan.proposed_sha256:
        return result(False, "proposed_digest_mismatch")

    if original_content == proposed_content:
        return result(False, "unchanged_content")

    try:
        original_content.decode("utf-8")
        proposed_content.decode("utf-8")
    except UnicodeDecodeError:
        return result(False, "invalid_utf8")

    return result(True, "verified")
