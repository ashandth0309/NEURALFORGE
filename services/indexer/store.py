
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3

from services.indexer.indexer import (
    EXCLUDED_DIRS,
    MAX_FILE_SIZE,
    MAX_FILES,
)

KINDS = frozenset({
    "function",
    "class",
    "interface",
    "type",
    "enum",
    "variable",
})


@dataclass(frozen=True)
class IndexedSymbol:
    name: str
    kind: str
    line: int


@dataclass(frozen=True)
class IndexedFile:
    path: str
    sha256: str
    size_bytes: int
    symbols: tuple[IndexedSymbol, ...] = ()


def _check_repository_id(repository_id: str) -> None:
    if not isinstance(repository_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",
        repository_id,
    ):
        raise ValueError("Invalid repository ID")


def _check_file(file: IndexedFile) -> None:
    if not isinstance(file, IndexedFile):
        raise ValueError("Expected IndexedFile")

    path = file.path

    if (
        not isinstance(path, str)
        or not path
        or "\\" in path
        or ":" in path
        or any(
            ord(char) < 32 or ord(char) == 127
            for char in path
        )
    ):
        raise ValueError("Invalid source path")

    parts = path.split("/")

    if any(
        not part
        or part in {".", ".."}
        or part.startswith(".")
        or part in EXCLUDED_DIRS
        for part in parts
    ):
        raise ValueError("Unsafe repository-relative path")

    if (
        not path.endswith((".ts", ".tsx"))
        or path.endswith(".d.ts")
    ):
        raise ValueError("Unsupported source extension")

    if (
        not isinstance(file.sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", file.sha256)
    ):
        raise ValueError("Invalid SHA-256 digest")

    if (
        type(file.size_bytes) is not int
        or not 0 <= file.size_bytes <= MAX_FILE_SIZE
    ):
        raise ValueError("Invalid source size")

    if not isinstance(file.symbols, tuple):
        raise ValueError("Symbols must be a tuple")

    for symbol in file.symbols:
        if not isinstance(symbol, IndexedSymbol):
            raise ValueError("Invalid symbol")

        if (
            not isinstance(symbol.name, str)
            or not symbol.name.strip()
            or any(
                ord(char) < 32 or ord(char) == 127
                for char in symbol.name
            )
        ):
            raise ValueError("Invalid symbol name")

        if (
            not isinstance(symbol.kind, str)
            or symbol.kind not in KINDS
        ):
            raise ValueError("Invalid symbol kind")

        if type(symbol.line) is not int or symbol.line < 1:
            raise ValueError("Invalid symbol line")


class SQLiteIndexStore:
    """Transactional local snapshot store.

    This storage adapter is not an authorization boundary.
    """

    def __init__(self, database: Path):
        self.database = Path(database)

        with closing(self._connect()) as conn:
            with conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS repositories (
                        id TEXT PRIMARY KEY
                    );

                    CREATE TABLE IF NOT EXISTS source_files (
                        repository_id TEXT NOT NULL,
                        path TEXT NOT NULL,
                        sha256 TEXT NOT NULL,
                        size_bytes INTEGER NOT NULL
                            CHECK (size_bytes >= 0),
                        PRIMARY KEY (repository_id, path),
                        FOREIGN KEY (repository_id)
                            REFERENCES repositories(id)
                            ON DELETE CASCADE
                    );

                    CREATE TABLE IF NOT EXISTS symbols (
                        repository_id TEXT NOT NULL,
                        path TEXT NOT NULL,
                        position INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        line INTEGER NOT NULL
                            CHECK (line > 0),
                        PRIMARY KEY (
                            repository_id,
                            path,
                            position
                        ),
                        FOREIGN KEY (repository_id, path)
                            REFERENCES source_files(
                                repository_id, path
                            )
                            ON DELETE CASCADE
                    );
                    """
                )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def replace_snapshot(
        self,
        repository_id: str,
        files: list[IndexedFile],
    ) -> None:
        _check_repository_id(repository_id)

        snapshot = tuple(files)

        if len(snapshot) > MAX_FILES:
            raise ValueError("Too many files")

        paths = set()

        for file in snapshot:
            _check_file(file)

            if file.path in paths:
                raise ValueError("Duplicate source path")

            paths.add(file.path)

        with closing(self._connect()) as conn:
            with conn:
                conn.execute(
                    "INSERT OR IGNORE INTO repositories(id) "
                    "VALUES (?)",
                    (repository_id,),
                )

                conn.execute(
                    "DELETE FROM source_files "
                    "WHERE repository_id = ?",
                    (repository_id,),
                )

                for file in snapshot:
                    conn.execute(
                        "INSERT INTO source_files("
                        "repository_id, path, sha256, size_bytes"
                        ") VALUES (?, ?, ?, ?)",
                        (
                            repository_id,
                            file.path,
                            file.sha256,
                            file.size_bytes,
                        ),
                    )

                    for position, symbol in enumerate(
                        file.symbols
                    ):
                        conn.execute(
                            "INSERT INTO symbols("
                            "repository_id, path, position, "
                            "name, kind, line"
                            ") VALUES (?, ?, ?, ?, ?, ?)",
                            (
                                repository_id,
                                file.path,
                                position,
                                symbol.name,
                                symbol.kind,
                                symbol.line,
                            ),
                        )

    def list_files(
        self,
        repository_id: str,
    ) -> list[IndexedFile]:
        _check_repository_id(repository_id)

        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT path, sha256, size_bytes "
                "FROM source_files "
                "WHERE repository_id = ? "
                "ORDER BY path",
                (repository_id,),
            ).fetchall()

            symbol_rows = conn.execute(
                "SELECT path, name, kind, line "
                "FROM symbols "
                "WHERE repository_id = ? "
                "ORDER BY path, position",
                (repository_id,),
            ).fetchall()

        by_path: dict[str, list[IndexedSymbol]] = {}

        for path, name, kind, line in symbol_rows:
            by_path.setdefault(path, []).append(
                IndexedSymbol(name, kind, line)
            )

        return [
            IndexedFile(
                path,
                sha256,
                size_bytes,
                tuple(by_path.get(path, ())),
            )
            for path, sha256, size_bytes in rows
        ]
