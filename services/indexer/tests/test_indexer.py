

import tempfile
import unittest
from pathlib import Path

from services.indexer.indexer import index_repository


class RepositoryIndexerTests(unittest.TestCase):


    def test_allows_exactly_max_files(self):
        for i in range(1000):
            (self.repo / f"file_{i:04}.ts").write_text(
                f"export const value{i} = {i};",
                encoding="utf-8"
            )

        result = index_repository(self.repo, self.root)

        self.assertEqual(len(result), 1000)

    def test_rejects_more_than_max_files(self):
        for i in range(1001):
            (self.repo / f"file_{i:04}.ts").write_text(
                f"export const value{i} = {i};",
                encoding="utf-8"
            )

        with self.assertRaises(ValueError):
            index_repository(self.repo, self.root)


    def test_does_not_index_symlink_outside_repository(self):
        with tempfile.TemporaryDirectory() as external_dir:
            external = Path(external_dir) / "secret.ts"
            external.write_text(
                "export const secret = 123;",
                encoding="utf-8"
            )

            link = self.repo / "linked.ts"

            try:
                link.symlink_to(external)
            except (OSError, NotImplementedError):
                self.skipTest(
                    "Symlink creation unavailable on this Windows setup"
                )

            result = index_repository(self.repo, self.root)

            self.assertEqual(result, [])



    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)
        self.repo = self.root / "project"
        self.repo.mkdir()

    def test_indexes_typescript_file(self):
        (self.repo / "hello.ts").write_text(
            "export const greeting = 'hello';",
            encoding="utf-8"
        )

        result = index_repository(self.repo, self.root)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].path, "hello.ts")
        self.assertEqual(len(result[0].sha256), 64)

    def test_ignores_non_typescript_files(self):
        (self.repo / "notes.txt").write_text("hello")

        result = index_repository(self.repo, self.root)

        self.assertEqual(result, [])

    def test_excludes_node_modules(self):
        modules = self.repo / "node_modules"
        modules.mkdir()
        (modules / "library.ts").write_text("const x = 1")

        result = index_repository(self.repo, self.root)

        self.assertEqual(result, [])

    def test_rejects_repository_outside_root(self):
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside)

            with self.assertRaises(PermissionError):
                index_repository(external, self.root)

    def test_hash_changes_when_content_changes(self):
        source = self.repo / "app.ts"

        source.write_text("const x = 1")
        first = index_repository(self.repo, self.root)

        source.write_text("const x = 2")
        second = index_repository(self.repo, self.root)

        self.assertNotEqual(
            first[0].sha256,
            second[0].sha256
        )


if __name__ == "__main__":
    unittest.main()
