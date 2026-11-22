
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import json

ALLOWED_EXTENSIONS = {".ts", ".tsx"}
EXCLUDED_DIRS = {
    ".git", "node_modules", ".next",
    "dist", "build", "coverage"
}
MAX_FILE_SIZE = 1024 * 1024  # 1 MiB
MAX_FILES = 1000


@dataclass(frozen=True)
class SourceFile:
    path: str
    sha256: str
    size_bytes: int


def index_repository(
    repo_path: Path,
    allowed_root: Path
) -> list[SourceFile]:
    """Index permitted TypeScript files without executing them."""

    root = allowed_root.resolve(strict=True)
    repo = repo_path.resolve(strict=True)

    if not repo.is_relative_to(root):
        raise PermissionError("Repository outside allowed root")

    if not repo.is_dir():
        raise ValueError("Repository path must be a directory")

    results = []

    for path in sorted(repo.rglob("*")):
        relative = path.relative_to(repo)

        if any(
            part in EXCLUDED_DIRS or part.startswith(".")
            for part in relative.parts[:-1]
        ):
            continue

        if path.name.startswith("."):
            continue

        if path.suffix not in ALLOWED_EXTENSIONS:
            continue

        if path.name.endswith(".d.ts"):
            continue

        # Do not follow symlinks, including directory symlinks.
        if path.is_symlink() or any(
            parent.is_symlink()
            for parent in path.parents
            if parent != repo and parent.is_relative_to(repo)
        ):
            continue

        resolved = path.resolve(strict=True)

        if not resolved.is_relative_to(repo):
            raise PermissionError("File outside repository")

        if not resolved.is_file():
            continue

        if resolved.stat().st_size > MAX_FILE_SIZE:
            continue

        data = resolved.read_bytes()

        if len(data) > MAX_FILE_SIZE:
            continue

        results.append(
            SourceFile(
                path=relative.as_posix(),
                sha256=hashlib.sha256(data).hexdigest(),
                size_bytes=len(data),
            )
        )

        if len(results) > MAX_FILES:
            raise ValueError("Repository file limit exceeded")

    return results



if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("repository", type=Path)
    parser.add_argument(
        "--allowed-root",
        type=Path,
        required=True
    )
    parser.add_argument(
        "--symbols",
        action="store_true",
        help="Extract TypeScript AST declarations"
    )

    args = parser.parse_args()

    indexed = index_repository(
        args.repository,
        args.allowed_root
    )

    output = [asdict(item) for item in indexed]

    if args.symbols:
        from services.indexer.symbols_bridge import extract_symbols

        repo = args.repository.resolve(strict=True)

        for item in output:
            source_path = repo / item["path"]

            if (
                source_path.is_symlink()
                or not source_path.resolve(strict=True).is_relative_to(repo)
            ):
                raise PermissionError("Unsafe source path")

            source_bytes = source_path.read_bytes()

            if len(source_bytes) > MAX_FILE_SIZE:
                raise ValueError("Source exceeds size limit")

            if hashlib.sha256(source_bytes).hexdigest() != item["sha256"]:
                raise RuntimeError("Source changed during indexing")

            item["symbols"] = extract_symbols(
                item["path"],
                source_bytes.decode("utf-8")
            )

    print(json.dumps(output, indent=2))
