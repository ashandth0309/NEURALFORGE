
"""Declarative validation plans; no command execution."""

from dataclasses import dataclass
from pathlib import PurePosixPath


ALLOWED_CHECKS = frozenset({
    "patch_integrity",
    "typescript_typecheck",
})

MAX_CHECKS = 2


@dataclass(frozen=True)
class ValidationPlan:
    """Immutable description of requested validation."""

    repository_id: str
    source_path: str
    original_sha256: str
    proposed_sha256: str
    checks: tuple[str, ...]


def create_validation_plan(
    repository_id: str,
    source_path: str,
    original_sha256: str,
    proposed_sha256: str,
    checks: tuple[str, ...],
) -> ValidationPlan:
    """Validate an allowlisted plan without running commands."""

    import re

    if (
        not isinstance(repository_id, str)
        or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",
            repository_id,
        )
    ):
        raise ValueError("Invalid repository ID")

    if not isinstance(source_path, str):
        raise ValueError("Invalid source path")

    parts = source_path.split("/")

    if (
        not source_path
        or source_path.startswith("/")
        or "\\" in source_path
        or ":" in source_path
        or any(
            not part
            or part in {".", ".."}
            or part.startswith(".")
            for part in parts
        )
        or any(
            ord(char) < 32 or ord(char) == 127
            for char in source_path
        )
        or PurePosixPath(source_path).suffix
        not in {".ts", ".tsx"}
        or source_path.endswith(".d.ts")
    ):
        raise ValueError("Unsafe source path")

    for digest in (original_sha256, proposed_sha256):
        if (
            not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            raise ValueError("Invalid SHA-256 digest")

    if original_sha256 == proposed_sha256:
        raise ValueError("Proposal must change source content")

    if (
        not isinstance(checks, tuple)
        or not 1 <= len(checks) <= MAX_CHECKS
        or any(
            not isinstance(check, str)
            for check in checks
        )
    ):
        raise ValueError("Invalid validation checks")

    if len(set(checks)) != len(checks):
        raise ValueError("Duplicate validation checks")

    if not set(checks).issubset(ALLOWED_CHECKS):
        raise ValueError("Unsupported validation check")

    if "patch_integrity" not in checks:
        raise ValueError("Patch integrity check is required")

    return ValidationPlan(
        repository_id=repository_id,
        source_path=source_path,
        original_sha256=original_sha256,
        proposed_sha256=proposed_sha256,
        checks=checks,
    )
