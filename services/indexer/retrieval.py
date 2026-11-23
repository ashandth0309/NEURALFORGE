
"""Deterministic symbol retrieval for NEURALFORGE."""

import argparse
import json
from pathlib import Path, PurePosixPath


ALLOWED_SYMBOL_KINDS = {
    "function",
    "class",
    "interface",
    "type",
    "enum",
    "variable",
}

ALLOWED_EXTENSIONS = {".ts", ".tsx"}

MAX_INDEX_FILES = 1000
MAX_SYMBOLS_PER_FILE = 10000
MAX_PATH_LENGTH = 4096
MAX_SYMBOL_NAME_LENGTH = 256
MAX_QUERY_LENGTH = 100
MAX_RESULTS = 100


def validate_index(indexed_files: list) -> None:
    """Validate the index structure before searching."""

    if not isinstance(indexed_files, list):
        raise TypeError("Index must be a list")

    if len(indexed_files) > MAX_INDEX_FILES:
        raise ValueError("Index exceeds file limit")

    for source_file in indexed_files:
        if not isinstance(source_file, dict):
            raise ValueError("Invalid source file entry")

        path = source_file.get("path")
        symbols = source_file.get("symbols", [])

        # Validate repository-relative TypeScript paths.
        if (
            not isinstance(path, str)
            or not path
            or len(path) > MAX_PATH_LENGTH
            or "\\" in path
            or ":" in path
            or any(ord(char) < 32 for char in path)
            or path.startswith("/")
            or any(
                part in {"", ".", ".."}
                for part in path.split("/")
            )
            or PurePosixPath(path).suffix not in ALLOWED_EXTENSIONS
        ):
            raise ValueError("Invalid source path")

        # Validate the symbols collection.
        if not isinstance(symbols, list):
            raise ValueError("Invalid symbols collection")

        if len(symbols) > MAX_SYMBOLS_PER_FILE:
            raise ValueError("Too many symbols")

        for symbol in symbols:
            if not isinstance(symbol, dict):
                raise ValueError("Invalid symbol")

            name = symbol.get("name")
            kind = symbol.get("kind")
            line = symbol.get("line")

            # Validate symbol name.
            if (
                not isinstance(name, str)
                or not name
                or len(name) > MAX_SYMBOL_NAME_LENGTH
            ):
                raise ValueError("Invalid symbol name")

            # Validate declaration type.
            if kind not in ALLOWED_SYMBOL_KINDS:
                raise ValueError("Invalid symbol kind")

            # Validate one-based source line.
            if type(line) is not int or line < 1:
                raise ValueError("Invalid symbol line")


def search_symbols(
    indexed_files: list[dict],
    query: str,
    limit: int = 20,
) -> list[dict]:
    """Search indexed declarations with deterministic ranking."""

    # Validate search query.
    if not isinstance(query, str):
        raise TypeError("Query must be a string")

    query = query.strip()

    if not query or len(query) > MAX_QUERY_LENGTH:
        raise ValueError(
            "Query must contain 1-100 characters"
        )

    # Validate result limit.
    if type(limit) is not int or not 1 <= limit <= MAX_RESULTS:
        raise ValueError(
            "Limit must be between 1 and 100"
        )

    # Validate the complete index.
    validate_index(indexed_files)

    matches = []
    normalized = query.casefold()

    for source_file in indexed_files:
        path = source_file["path"]
        symbols = source_file.get("symbols", [])

        for symbol in symbols:
            name = symbol["name"]
            candidate = name.casefold()

            # Ranking strategy:
            # Exact match: 100
            # Prefix match: 80
            # Substring match: 60

            if candidate == normalized:
                score = 100

            elif candidate.startswith(normalized):
                score = 80

            elif normalized in candidate:
                score = 60

            else:
                continue

            matches.append({
                "path": path,
                "name": name,
                "kind": symbol["kind"],
                "line": symbol["line"],
                "score": score,
            })

    # Deterministic ordering.
    matches.sort(
        key=lambda item: (
            -item["score"],
            item["name"].casefold(),
            item["path"],
            item["line"],
        )
    )

    return matches[:limit]


def main() -> None:
    """Run symbol retrieval from the command line."""

    parser = argparse.ArgumentParser(
        description="NEURALFORGE Symbol Retrieval Engine"
    )

    parser.add_argument(
        "--index",
        type=Path,
        required=True,
        help="Path to the generated JSON index",
    )

    parser.add_argument(
        "--query",
        required=True,
        help="Symbol name to search",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of results (1-100)",
    )

    args = parser.parse_args()

    # Load previously generated repository index.
    with args.index.open(
        "r",
        encoding="utf-8"
    ) as file:
        indexed_files = json.load(file)

    # Search indexed symbols.
    results = search_symbols(
        indexed_files,
        args.query,
        args.limit,
    )

    # Print structured JSON response.
    print(
        json.dumps(
            {
                "query": args.query,
                "count": len(results),
                "results": results,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
