
import hashlib
import tempfile
import unittest
from pathlib import Path

from services.indexer.freshness import check_file_freshness
from services.indexer.store import IndexedFile


class FreshnessTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "app.ts"
        self.original = b"export function hello() {}"

        self.source.write_bytes(self.original)

        self.indexed = IndexedFile(
            path="app.ts",
            sha256=hashlib.sha256(self.original).hexdigest(),
            size_bytes=len(self.original),
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_unchanged_file_is_current(self):
        self.assertEqual(
            check_file_freshness(self.root, self.indexed),
            "current",
        )

    def test_changed_file_is_stale(self):
        self.source.write_text(
            "export function changed() {}",
            encoding="utf-8",
        )

        self.assertEqual(
            check_file_freshness(self.root, self.indexed),
            "stale",
        )

    def test_deleted_file_is_missing(self):
        self.source.unlink()

        self.assertEqual(
            check_file_freshness(self.root, self.indexed),
            "missing",
        )

    def test_path_traversal_is_unavailable(self):
        invalid = IndexedFile(
            path="../outside.ts",
            sha256=self.indexed.sha256,
            size_bytes=self.indexed.size_bytes,
        )

        self.assertEqual(
            check_file_freshness(self.root, invalid),
            "unavailable",
        )

    def test_oversized_file_is_unavailable(self):
        self.source.write_bytes(b"x" * (1024 * 1024 + 1))

        self.assertEqual(
            check_file_freshness(self.root, self.indexed),
            "unavailable",
        )

    def test_non_file_path_is_unavailable(self):
        (self.root / "folder.ts").mkdir()

        invalid = IndexedFile(
            path="folder.ts",
            sha256=self.indexed.sha256,
            size_bytes=0,
        )

        self.assertEqual(
            check_file_freshness(self.root, invalid),
            "unavailable",
        )


    def test_symlink_source_is_unavailable(self):
        link = self.root / "linked.ts"

        try:
            link.symlink_to(self.source)
        except (OSError, NotImplementedError) as error:
            self.skipTest(
                f"Symlinks unavailable in this environment: {error}"
            )

        linked = IndexedFile(
            path="linked.ts",
            sha256=self.indexed.sha256,
            size_bytes=self.indexed.size_bytes,
        )

        self.assertEqual(
            check_file_freshness(self.root, linked),
            "unavailable",
        )



if __name__ == "__main__":
    unittest.main()
