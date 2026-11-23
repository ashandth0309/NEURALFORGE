
"""Read indexed source files for read-only patch proposals."""

import hashlib
import re
from pathlib import Path

from services.indexer.indexer import MAX_FILE_SIZE
from services.indexer.store import IndexedFile


class SourceReadError(ValueError):
    """A source file cannot be used for a patch proposal."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def read_verified_indexed_source(
    repository_root: Path,
    indexed_file: IndexedFile,
    expected_sha256: str,
) -> str:
    """Return UTF-8 source only when both hashes match.

    Intended for trusted local repositories. This is
    read-only, but it is not race-free filesystem isolation.
    """

    if not isinstance(indexed_file, IndexedFile):
        raise TypeError("Expected IndexedFile")

    if (
        not isinstance(expected_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
    ):
        raise SourceReadError("invalid_digest")

    relative = indexed_file.path

    if (
        not isinstance(relative, str)
        or not relative
        or relative.startswith("/")
        or "\\" in relative
        or ":" in relative
        or any(
            ord(char) < 32 or ord(char) == 127
            for char in relative
        )
        or any(
            part in {"", ".", ".."} or part.startswith(".")
            for part in relative.split("/")
        )
        or not relative.endswith((".ts", ".tsx"))
        or relative.endswith(".d.ts")
    ):
        raise SourceReadError("invalid_path")

    try:
        root = Path(repository_root).resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError):
        raise SourceReadError("unavailable") from None

    if not root.is_dir():
        raise SourceReadError("unavailable")

    candidate = root

    for component in relative.split("/"):
        candidate = candidate / component

        if candidate.is_symlink():
            raise SourceReadError("unavailable")

    try:
        if not candidate.resolve(strict=False).is_relative_to(root):
            raise SourceReadError("invalid_path")

        if not candidate.exists():
            raise SourceReadError("missing")

        if not candidate.is_file():
            raise SourceReadError("unavailable")

        if candidate.stat().st_size > MAX_FILE_SIZE:
            raise SourceReadError("unavailable")

        with candidate.open("rb") as stream:
            content = stream.read(MAX_FILE_SIZE + 1)

    except (OSError, RuntimeError):
        raise SourceReadError("unavailable") from None

    if len(content) > MAX_FILE_SIZE:
        raise SourceReadError("unavailable")

    actual_sha256 = hashlib.sha256(content).hexdigest()

    if (
        actual_sha256 != indexed_file.sha256
        or actual_sha256 != expected_sha256
    ):
        raise SourceReadError("stale")

    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        raise SourceReadError("invalid_encoding") from None
