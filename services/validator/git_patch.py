
"""Validate a canonical patch inside a disposable Git repository."""

import hashlib
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from services.indexer.indexer import MAX_FILE_SIZE
from services.validator.consistency import verify_proposal_consistency
from services.validator.policy import (
    ValidationPlan,
    create_validation_plan,
)


@dataclass(frozen=True)
class GitPatchResult:
    passed: bool
    reason: str
    actual_sha256: str | None


def verify_git_patch(
    plan: ValidationPlan,
    original_content: bytes,
    old_text: str,
    new_text: str,
    proposal: dict,
) -> GitPatchResult:
    """Apply a verified patch to a temporary copy, never the original."""

    def fail(reason: str) -> GitPatchResult:
        return GitPatchResult(False, reason, None)

    if not isinstance(plan, ValidationPlan):
        raise TypeError("Expected ValidationPlan")

    # Revalidate: frozen dataclasses can still be constructed
    # directly without going through the policy factory.
    try:
        create_validation_plan(
            repository_id=plan.repository_id,
            source_path=plan.source_path,
            original_sha256=plan.original_sha256,
            proposed_sha256=plan.proposed_sha256,
            checks=plan.checks,
        )
    except (ValueError, TypeError):
        return fail("invalid_plan")

    if not isinstance(original_content, bytes):
        raise TypeError("Original content must be bytes")

    if len(original_content) > MAX_FILE_SIZE:
        return fail("size_limit_exceeded")

    consistency = verify_proposal_consistency(
        plan=plan,
        original_content=original_content,
        old_text=old_text,
        new_text=new_text,
        proposal=proposal,
    )

    if not consistency.passed:
        return fail(consistency.reason)

    patch_bytes = proposal["unified_diff"].encode("utf-8")

    if len(patch_bytes) > 4 * MAX_FILE_SIZE:
        return fail("patch_size_limit_exceeded")

    try:
        with tempfile.TemporaryDirectory(
            prefix="neuralforge-git-validation-"
        ) as temporary:
            root = Path(temporary)

            target = root.joinpath(
                *plan.source_path.split("/")
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(original_content)

            init_result = subprocess.run(
                ["git", "init", "--quiet"],
                cwd=root,
                capture_output=True,
                timeout=10,
                check=False,
            )

            if init_result.returncode != 0:
                return fail("git_initialization_failed")

            command = [
                "git",
                "-c",
                "core.autocrlf=false",
                "apply",
            ]

            check_result = subprocess.run(
                [*command, "--check", "-"],
                input=patch_bytes,
                cwd=root,
                capture_output=True,
                timeout=10,
                check=False,
            )

            if check_result.returncode != 0:
                return fail("git_patch_check_failed")

            apply_result = subprocess.run(
                [*command, "-"],
                input=patch_bytes,
                cwd=root,
                capture_output=True,
                timeout=10,
                check=False,
            )

            if apply_result.returncode != 0:
                return fail("git_patch_apply_failed")

            actual = target.read_bytes()
            actual_digest = hashlib.sha256(actual).hexdigest()

            if actual_digest != plan.proposed_sha256:
                return GitPatchResult(
                    False,
                    "applied_digest_mismatch",
                    actual_digest,
                )

            return GitPatchResult(
                True,
                "verified",
                actual_digest,
            )

    except FileNotFoundError:
        return fail("git_unavailable")
    except subprocess.TimeoutExpired:
        return fail("git_timeout")
    except (OSError, RuntimeError):
        return fail("validation_unavailable")
