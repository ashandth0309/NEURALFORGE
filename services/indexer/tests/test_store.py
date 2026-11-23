
import tempfile
import unittest
from pathlib import Path

from services.indexer.store import (
    IndexedFile,
    IndexedSymbol,
    SQLiteIndexStore,
)


class SQLiteIndexStoreTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "index.sqlite3"

    def tearDown(self):
        self.temp.cleanup()

    def source(self, path, digest="a" * 64, symbols=()):
        return IndexedFile(
            path=path,
            sha256=digest,
            size_bytes=42,
            symbols=tuple(symbols),
        )

    def test_persists_files_and_symbols_after_reopen(self):
        source = self.source(
            "src/app.ts",
            symbols=(
                IndexedSymbol(
                    name="start",
                    kind="function",
                    line=3,
                ),
            ),
        )

        store = SQLiteIndexStore(self.db)
        store.replace_snapshot("repo-a", [source])

        reopened = SQLiteIndexStore(self.db)

        self.assertEqual(
            reopened.list_files("repo-a"),
            [source],
        )

    def test_replaces_changed_and_deleted_files(self):
        store = SQLiteIndexStore(self.db)

        store.replace_snapshot(
            "repo-a",
            [
                self.source("src/one.ts"),
                self.source("src/two.ts"),
            ],
        )

        changed = self.source(
            "src/one.ts",
            digest="b" * 64,
        )

        store.replace_snapshot("repo-a", [changed])

        self.assertEqual(
            store.list_files("repo-a"),
            [changed],
        )

    def test_isolates_different_repositories(self):
        store = SQLiteIndexStore(self.db)

        first = self.source(
            "src/app.ts",
            digest="a" * 64,
        )
        second = self.source(
            "src/app.ts",
            digest="b" * 64,
        )

        store.replace_snapshot("repo-a", [first])
        store.replace_snapshot("repo-b", [second])

        self.assertEqual(
            store.list_files("repo-a"),
            [first],
        )
        self.assertEqual(
            store.list_files("repo-b"),
            [second],
        )

    def test_invalid_snapshot_preserves_existing_data(self):
        store = SQLiteIndexStore(self.db)

        original = self.source("src/safe.ts")
        store.replace_snapshot("repo-a", [original])

        invalid = self.source("../outside.ts")

        with self.assertRaises(ValueError):
            store.replace_snapshot(
                "repo-a",
                [
                    self.source("src/new.ts"),
                    invalid,
                ],
            )

        self.assertEqual(
            store.list_files("repo-a"),
            [original],
        )

    def test_rejects_invalid_sha256(self):
        store = SQLiteIndexStore(self.db)

        invalid = self.source(
            "src/app.ts",
            digest="not-a-valid-sha256",
        )

        with self.assertRaises(ValueError):
            store.replace_snapshot("repo-a", [invalid])


if __name__ == "__main__":
    unittest.main()
