
"""Execute trusted patch checks and report their outcomes."""

from time import perf_counter_ns

from services.validator.git_patch import verify_git_patch
from services.validator.policy import (
    ValidationPlan,
    create_validation_plan,
)
from services.validator.report import (
    MAX_DURATION_MS,
    CheckReport,
    ValidationReport,
    create_validation_report,
)


def run_patch_validation(
    plan: ValidationPlan,
    original_content: bytes,
    old_text: str,
    new_text: str,
    proposal: dict,
) -> ValidationReport:
    """Run patch integrity validation and return a measured report.

    Trusted local inputs only. Does not execute project code.
    """

    if not isinstance(plan, ValidationPlan):
        raise TypeError("Expected ValidationPlan")

    # Validate even manually constructed plans.
    create_validation_plan(
        repository_id=plan.repository_id,
        source_path=plan.source_path,
        original_sha256=plan.original_sha256,
        proposed_sha256=plan.proposed_sha256,
        checks=plan.checks,
    )

    # TypeScript execution has not been implemented.
    if plan.checks != ("patch_integrity",):
        raise ValueError(
            "Only patch_integrity validation is implemented"
        )

    started = perf_counter_ns()

    result = verify_git_patch(
        plan=plan,
        original_content=original_content,
        old_text=old_text,
        new_text=new_text,
        proposal=proposal,
    )

    elapsed_ms = max(
        0,
        (perf_counter_ns() - started) // 1_000_000,
    )

    duration_ms = min(
        elapsed_ms,
        MAX_DURATION_MS,
    )

    check_result = CheckReport(
        check="patch_integrity",
        passed=result.passed,
        reason=result.reason,
        duration_ms=duration_ms,
    )

    return create_validation_report(
        plan,
        (check_result,),
    )
