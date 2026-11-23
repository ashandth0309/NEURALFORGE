
"""Read-only deterministic patch proposal generation."""

import difflib
import hashlib
import re
from pathlib import PurePosixPath


MAX_SOURCE_BYTES = 1024 * 1024


def propose_replacement(
    path: str,
    source: str,
    old_text: str,
    new_text: str,
    expected_sha256: str,
) -> dict:
    """Propose exactly one replacement without writing files."""

    if not isinstance(path, str):
        raise TypeError("Path must be a string")

    parts = path.split("/")

    if (
        not path
        or path.startswith("/")
        or "\\" in path
        or ":" in path
        or any(part in {"", ".", ".."} for part in parts)
        or any(ord(char) < 32 for char in path)
        or PurePosixPath(path).suffix not in {".ts", ".tsx"}
    ):
        raise ValueError("Unsafe source path")

    if not all(
        isinstance(value, str)
        for value in (source, old_text, new_text)
    ):
        raise TypeError("Source and replacement values must be strings")

    if not isinstance(expected_sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}",
        expected_sha256,
    ):
        raise ValueError("Invalid expected SHA-256")

    original_bytes = source.encode("utf-8")
    actual_sha256 = hashlib.sha256(original_bytes).hexdigest()

    if len(original_bytes) > MAX_SOURCE_BYTES:
        raise ValueError("Source exceeds size limit")

    if actual_sha256 != expected_sha256:
        raise ValueError("Source does not match expected snapshot")

    if not old_text:
        raise ValueError("Replacement target cannot be empty")

    if old_text == new_text:
        raise ValueError("Replacement would not change source")

    occurrences = source.count(old_text)

    if occurrences != 1:
        raise ValueError(
            "Replacement target must occur exactly once"
        )

    updated_source = source.replace(old_text, new_text, 1)

    if len(updated_source.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ValueError("Proposed source exceeds size limit")


    diff_lines = difflib.unified_diff(
        source.splitlines(keepends=True),
        updated_source.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="\n",
    )

    formatted_lines = []

    for line in diff_lines:
        if line.endswith("\n"):
            formatted_lines.append(line)
        else:
            formatted_lines.append(
                line
                + "\n"
                + "\\ No newline at end of file\n"
            )

    diff = "".join(formatted_lines)


    return {
        "path": path,
        "original_sha256": actual_sha256,
        "proposed_sha256": hashlib.sha256(
            updated_source.encode("utf-8")
        ).hexdigest(),
        "unified_diff": diff,
        "changed": True,
        "applied": False,
    }
