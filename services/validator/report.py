
"""Structured, immutable validation reports."""

import re
from dataclasses import asdict, dataclass

from services.validator.policy import (
    ALLOWED_CHECKS,
    ValidationPlan,
    create_validation_plan,
)

MAX_DURATION_MS = 3_600_000
REASON_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}")


@dataclass(frozen=True)
class CheckReport:
    check: str
    passed: bool
    reason: str
    duration_ms: int


@dataclass(frozen=True)
class ValidationReport:
    repository_id: str
    source_path: str
    original_sha256: str
    proposed_sha256: str
    passed: bool
    checks: tuple[CheckReport, ...]
    total_duration_ms: int

    def to_dict(self) -> dict:
        """Return a JSON-compatible representation."""
        return asdict(self)


def create_validation_report(
    plan: ValidationPlan,
    results: tuple[CheckReport, ...],
) -> ValidationReport:
    """Build a complete report from an approved validation plan."""

    if not isinstance(plan, ValidationPlan):
        raise TypeError("Expected ValidationPlan")

    create_validation_plan(
        repository_id=plan.repository_id,
        source_path=plan.source_path,
        original_sha256=plan.original_sha256,
        proposed_sha256=plan.proposed_sha256,
        checks=plan.checks,
    )

    if not isinstance(results, tuple):
        raise TypeError("Results must be a tuple")

    if len(results) != len(plan.checks):
        raise ValueError("Validation result count mismatch")

    reported_checks = tuple(
        result.check
        for result in results
        if isinstance(result, CheckReport)
    )

    if reported_checks != plan.checks:
        raise ValueError("Validation check order mismatch")

    for result in results:
        if result.check not in ALLOWED_CHECKS:
            raise ValueError("Unsupported check")

        if type(result.passed) is not bool:
            raise ValueError("Invalid check status")

        if (
            not isinstance(result.reason, str)
            or REASON_PATTERN.fullmatch(result.reason) is None
        ):
            raise ValueError("Invalid result reason")

        if (
            type(result.duration_ms) is not int
            or not 0 <= result.duration_ms <= MAX_DURATION_MS
        ):
            raise ValueError("Invalid duration")

        if result.passed and result.reason != "verified":
            raise ValueError("Passed checks must be verified")

        if not result.passed and result.reason == "verified":
            raise ValueError("Failed checks need a failure reason")

    total_duration = sum(
        result.duration_ms
        for result in results
    )

    return ValidationReport(
        repository_id=plan.repository_id,
        source_path=plan.source_path,
        original_sha256=plan.original_sha256,
        proposed_sha256=plan.proposed_sha256,
        passed=all(result.passed for result in results),
        checks=results,
        total_duration_ms=total_duration,
    )
