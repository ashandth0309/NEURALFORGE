
"""Read-only consistency checks for NEURALFORGE proposals."""

from dataclasses import dataclass

from services.patcher.proposal import propose_replacement
from services.validator.integrity import verify_patch_integrity
from services.validator.policy import ValidationPlan


@dataclass(frozen=True)
class ConsistencyResult:
    passed: bool
    reason: str


def verify_proposal_consistency(
    plan: ValidationPlan,
    original_content: bytes,
    old_text: str,
    new_text: str,
    proposal: dict,
) -> ConsistencyResult:
    """Regenerate and compare a deterministic patch proposal.

    Does not write files or execute commands.
    Does not independently interpret arbitrary Git patches.
    """

    def fail(reason: str) -> ConsistencyResult:
        return ConsistencyResult(False, reason)

    if not isinstance(plan, ValidationPlan):
        raise TypeError("Expected ValidationPlan")

    if not isinstance(original_content, bytes):
        raise TypeError("Original content must be bytes")

    if not isinstance(proposal, dict):
        return fail("invalid_proposal")

    if not isinstance(old_text, str):
        return fail("invalid_replacement")

    if not isinstance(new_text, str):
        return fail("invalid_replacement")

    try:
        original_source = original_content.decode("utf-8")

        if original_source.count(old_text) != 1:
            return fail("target_not_unique")

        proposed_source = original_source.replace(
            old_text,
            new_text,
            1,
        )

        proposed_content = proposed_source.encode("utf-8")

        integrity = verify_patch_integrity(
            plan,
            original_content,
            proposed_content,
        )

        if not integrity.passed:
            return fail(integrity.reason)

        expected = propose_replacement(
            path=plan.source_path,
            source=original_source,
            old_text=old_text,
            new_text=new_text,
            expected_sha256=plan.original_sha256,
        )

    except UnicodeDecodeError:
        return fail("invalid_utf8")

    except ValueError:
        return fail("invalid_replacement")

    required_fields = (
        "path",
        "original_sha256",
        "proposed_sha256",
        "unified_diff",
        "changed",
        "applied",
    )

    if any(
        field not in proposal
        for field in required_fields
    ):
        return fail("missing_proposal_field")

    for field in required_fields:
        if type(proposal[field]) is not type(expected[field]):
            return fail("proposal_mismatch")

        if proposal[field] != expected[field]:
            return fail("proposal_mismatch")

    return ConsistencyResult(True, "verified")
