
"""Point-in-time freshness checks for indexed source files."""

import hashlib
from pathlib import Path, PurePosixPath

from services.indexer.indexer import MAX_FILE_SIZE
from services.indexer.store import IndexedFile


def check_file_freshness(
    repository_root: Path,
    indexed_file: IndexedFile,
) -> str:
    """Compare an indexed digest with a trusted local source.

    Returns current, stale, missing, or unavailable.

    This is a local-development verifier, not a hardened
    filesystem isolation boundary.
    """

    if not isinstance(indexed_file, IndexedFile):
        raise TypeError("Expected IndexedFile")

    root = Path(repository_root).resolve(strict=True)

    if not root.is_dir():
        raise ValueError("Repository root must be a directory")

    relative = indexed_file.path

    if (
        not isinstance(relative, str)
        or not relative
        or "\\" in relative
        or ":" in relative
        or any(ord(char) < 32 for char in relative)
        or relative.startswith("/")
        or any(
            part in {"", ".", ".."}
            for part in relative.split("/")
        )
        or PurePosixPath(relative).suffix not in {".ts", ".tsx"}
    ):
        return "unavailable"

    candidate = root

    for component in relative.split("/"):
        candidate = candidate / component

        # Never deliberately follow symlinks, including those
        # in intermediate directory components.
        if candidate.is_symlink():
            return "unavailable"

    try:
        resolved = candidate.resolve(strict=False)

        if not resolved.is_relative_to(root):
            return "unavailable"

        if not candidate.exists():
            return "missing"

        if not candidate.is_file():
            return "unavailable"

        if candidate.stat().st_size > MAX_FILE_SIZE:
            return "unavailable"

        content = candidate.read_bytes()

        if len(content) > MAX_FILE_SIZE:
            return "unavailable"

        actual_hash = hashlib.sha256(content).hexdigest()

        if actual_hash == indexed_file.sha256:
            return "current"

        return "stale"

    except (OSError, RuntimeError):
        return "unavailable"
