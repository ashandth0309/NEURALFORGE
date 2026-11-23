
"""Validate a canonical patch inside a disposable Git repository."""

import hashlib
import os

import sys

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


def _git_environment() -> dict[str, str]:
    """Remove inherited Git-specific environment overrides.

    Disable system and global Git configuration and prevent
    Git from prompting for interactive credentials.

    This is defense in depth, not operating-system isolation.
    """

    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }

    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )

    return environment


@dataclass(frozen=True)
class GitPatchResult:
    """Immutable result of independent Git patch verification."""

    passed: bool
    reason: str
    actual_sha256: str | None


def _resolve_git_executable() -> str | None:
    """Resolve a configured, absolute Git executable path.

    Never search PATH to locate a Git executable.
    This checks location, not binary authenticity.
    """

    configured = os.environ.get(
        "NEURALFORGE_GIT_EXECUTABLE"
    )

    if configured is not None:
        if not configured.strip():
            return None

        candidate = Path(configured)
    elif sys.platform == "win32":
        candidate = Path(
            r"C:\Program Files\Git\cmd\git.exe"
        )
    else:
        candidate = Path("/usr/bin/git")

    if not candidate.is_absolute():
        return None

    try:
        if not candidate.is_file():
            return None

        resolved = candidate.resolve(strict=True)

        if not resolved.is_file():
            return None

        return str(resolved)

    except (OSError, RuntimeError, ValueError):
        return None



def verify_git_patch(
    plan: ValidationPlan,
    original_content: bytes,
    old_text: str,
    new_text: str,
    proposal: dict,
) -> GitPatchResult:
    """Verify and apply a canonical patch to a disposable copy.

    The original project repository is never used as the Git
    working directory or as the patch destination.

    Intended for trusted local validation only.
    """

    def fail(reason: str) -> GitPatchResult:
        return GitPatchResult(
            passed=False,
            reason=reason,
            actual_sha256=None,
        )

    if not isinstance(plan, ValidationPlan):
        raise TypeError("Expected ValidationPlan")

    # Frozen dataclasses can be constructed directly.
    # Revalidate the plan through the policy factory.
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

    # Verify proposal consistency before invoking Git.
    consistency = verify_proposal_consistency(
        plan=plan,
        original_content=original_content,
        old_text=old_text,
        new_text=new_text,
        proposal=proposal,
    )

    if not consistency.passed:
        return fail(consistency.reason)

    # Git receives only a canonical proposal verified above.
    patch_bytes = proposal["unified_diff"].encode("utf-8")

    if len(patch_bytes) > 4 * MAX_FILE_SIZE:
        return fail("patch_size_limit_exceeded")

    # Remove inherited Git configuration overrides.

    git_executable = _resolve_git_executable()

    if git_executable is None:
        return fail("git_unavailable")

    git_environment = _git_environment()


    try:
        with tempfile.TemporaryDirectory(
            prefix="neuralforge-git-validation-"
        ) as temporary:
            root = Path(temporary)

            # The source path has already passed validation.
            # Reconstruct it only inside the temporary directory.
            target = root.joinpath(
                *plan.source_path.split("/")
            )

            target.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            target.write_bytes(original_content)

            # Initialize a disposable Git repository.
            init_result = subprocess.run(
                [git_executable, "init", "--quiet"],
                cwd=root,
                env=git_environment,
                capture_output=True,
                timeout=10,
                check=False,
            )

            if init_result.returncode != 0:
                return fail("git_initialization_failed")

            # Disable automatic line-ending conversion.
            command = [
                git_executable,
                "-c",
                "core.autocrlf=false",
                "apply",
            ]

            # First confirm that Git accepts the patch.
            check_result = subprocess.run(
                [*command, "--check", "-"],
                input=patch_bytes,
                cwd=root,
                env=git_environment,
                capture_output=True,
                timeout=10,
                check=False,
            )

            if check_result.returncode != 0:
                return fail("git_patch_check_failed")

            # Apply only to the disposable copy.
            apply_result = subprocess.run(
                [*command, "-"],
                input=patch_bytes,
                cwd=root,
                env=git_environment,
                capture_output=True,
                timeout=10,
                check=False,
            )

            if apply_result.returncode != 0:
                return fail("git_patch_apply_failed")

            # Independently hash the resulting file bytes.
            actual = target.read_bytes()

            actual_digest = hashlib.sha256(
                actual
            ).hexdigest()

            if actual_digest != plan.proposed_sha256:
                return GitPatchResult(
                    passed=False,
                    reason="applied_digest_mismatch",
                    actual_sha256=actual_digest,
                )

            return GitPatchResult(
                passed=True,
                reason="verified",
                actual_sha256=actual_digest,
            )

    except FileNotFoundError:
        return fail("git_unavailable")

    except subprocess.TimeoutExpired:
        return fail("git_timeout")

    except (OSError, RuntimeError):
        return fail("validation_unavailable")
