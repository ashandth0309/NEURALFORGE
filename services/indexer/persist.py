
"""Persist a trusted local repository's TypeScript index."""

import argparse
import hashlib
from pathlib import Path

from services.indexer.indexer import (
    MAX_FILE_SIZE,
    index_repository,
)
from services.indexer.symbols_bridge import extract_symbols
from services.indexer.store import (
    IndexedFile,
    IndexedSymbol,
    SQLiteIndexStore,
)


def persist_repository(
    repo_path: Path,
    allowed_root: Path,
    repository_id: str,
    database: Path,
) -> int:
    """Build and transactionally persist a repository snapshot."""

    repo = repo_path.resolve(strict=True)

    # Repository-root authorization is checked by the indexer.
    indexed_files = index_repository(repo, allowed_root)
    snapshot = []

    for indexed in indexed_files:
        source_path = repo / indexed.path

        # Recheck paths after discovery to reduce filesystem
        # race risks. This is not a hardened filesystem sandbox.
        if source_path.is_symlink() or any(
            parent.is_symlink()
            for parent in source_path.parents
            if parent != repo and parent.is_relative_to(repo)
        ):
            raise PermissionError("Unsafe source path")

        resolved = source_path.resolve(strict=True)

        if not resolved.is_relative_to(repo):
            raise PermissionError("Source escaped repository")

        if not resolved.is_file():
            raise ValueError("Source is not a regular file")

        source_bytes = resolved.read_bytes()

        if (
            len(source_bytes) > MAX_FILE_SIZE
            or len(source_bytes) != indexed.size_bytes
            or hashlib.sha256(source_bytes).hexdigest()
            != indexed.sha256
        ):
            raise RuntimeError("Source changed during indexing")

        source_text = source_bytes.decode("utf-8")

        parsed_symbols = extract_symbols(
            indexed.path,
            source_text,
        )

        symbols = tuple(
            IndexedSymbol(
                name=item["name"],
                kind=item["kind"],
                line=item["line"],
            )
            for item in parsed_symbols
        )

        snapshot.append(
            IndexedFile(
                path=indexed.path,
                sha256=indexed.sha256,
                size_bytes=indexed.size_bytes,
                symbols=symbols,
            )
        )

    # Persist only after every source has been processed.
    store = SQLiteIndexStore(database)
    store.replace_snapshot(repository_id, snapshot)

    return len(snapshot)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="NEURALFORGE local SQLite index builder"
    )

    parser.add_argument("repository", type=Path)
    parser.add_argument(
        "--allowed-root",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--repository-id",
        required=True,
    )
    parser.add_argument(
        "--database",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    count = persist_repository(
        repo_path=args.repository,
        allowed_root=args.allowed_root,
        repository_id=args.repository_id,
        database=args.database,
    )

    print(
        f"Indexed {count} TypeScript files "
        f"into repository '{args.repository_id}'"
    )


if __name__ == "__main__":
    main()
