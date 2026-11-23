
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.indexer.persist import persist_repository
from services.indexer.store import SQLiteIndexStore


class RepositoryPersistenceTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "repository"
        self.repo.mkdir()
        self.database = self.root / "index.sqlite3"

    def tearDown(self):
        self.temp.cleanup()

    def test_persists_real_source_metadata(self):
        (self.repo / "app.ts").write_text(
            "export function hello() { return 1; }",
            encoding="utf-8",
        )

        with patch(
            "services.indexer.persist.extract_symbols",
            return_value=[
                {
                    "name": "hello",
                    "kind": "function",
                    "line": 1,
                }
            ],
        ):
            count = persist_repository(
                self.repo,
                self.root,
                "repo-a",
                self.database,
            )

        self.assertEqual(count, 1)

        files = SQLiteIndexStore(
            self.database
        ).list_files("repo-a")

        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].path, "app.ts")
        self.assertEqual(files[0].symbols[0].name, "hello")
        self.assertEqual(len(files[0].sha256), 64)

    def test_parser_failure_preserves_snapshot(self):
        source = self.repo / "app.ts"
        source.write_text(
            "export function first() {}",
            encoding="utf-8",
        )

        with patch(
            "services.indexer.persist.extract_symbols",
            return_value=[
                {
                    "name": "first",
                    "kind": "function",
                    "line": 1,
                }
            ],
        ):
            persist_repository(
                self.repo,
                self.root,
                "repo-a",
                self.database,
            )

        original = SQLiteIndexStore(
            self.database
        ).list_files("repo-a")

        source.write_text(
            "export function changed() {}",
            encoding="utf-8",
        )

        with patch(
            "services.indexer.persist.extract_symbols",
            side_effect=RuntimeError("Parser failed"),
        ):
            with self.assertRaises(RuntimeError):
                persist_repository(
                    self.repo,
                    self.root,
                    "repo-a",
                    self.database,
                )

        current = SQLiteIndexStore(
            self.database
        ).list_files("repo-a")

        self.assertEqual(current, original)

    def test_rejects_repository_outside_allowed_root(self):
        other_root = self.root / "allowed"
        other_root.mkdir()

        with self.assertRaises(PermissionError):
            persist_repository(
                self.repo,
                other_root,
                "repo-a",
                self.database,
            )


if __name__ == "__main__":
    unittest.main()
