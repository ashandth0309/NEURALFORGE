
import hashlib
import tempfile
import unittest
from pathlib import Path

from services.indexer.store import IndexedFile
from services.patcher.source import (
    SourceReadError,
    read_verified_indexed_source,
)


class VerifiedSourceTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

        self.source = self.root / "src" / "example.ts"
        self.source.parent.mkdir(parents=True)

        self.original = b'export const message = "hello";\n'
        self.source.write_bytes(self.original)

        self.digest = hashlib.sha256(
            self.original
        ).hexdigest()

        self.indexed = IndexedFile(
            path="src/example.ts",
            sha256=self.digest,
            size_bytes=len(self.original),
        )

    def tearDown(self):
        self.temp.cleanup()

    def assert_reason(self, reason, **overrides):
        options = {
            "repository_root": self.root,
            "indexed_file": self.indexed,
            "expected_sha256": self.digest,
        }
        options.update(overrides)

        with self.assertRaises(SourceReadError) as caught:
            read_verified_indexed_source(**options)

        self.assertEqual(caught.exception.reason, reason)

    def test_reads_matching_source(self):
        result = read_verified_indexed_source(
            self.root,
            self.indexed,
            self.digest,
        )
        self.assertEqual(
            result,
            self.original.decode("utf-8"),
        )

    def test_rejects_changed_source(self):
        self.source.write_bytes(b"changed")
        self.assert_reason("stale")

    def test_rejects_wrong_request_digest(self):
        self.assert_reason(
            "stale",
            expected_sha256="b" * 64,
        )

    def test_rejects_missing_source(self):
        self.source.unlink()
        self.assert_reason("missing")

    def test_rejects_path_traversal(self):
        invalid = IndexedFile(
            path="../outside.ts",
            sha256=self.digest,
            size_bytes=len(self.original),
        )
        self.assert_reason(
            "invalid_path",
            indexed_file=invalid,
        )

    def test_rejects_oversized_source(self):
        self.source.write_bytes(b"x" * (1024 * 1024 + 1))
        self.assert_reason("unavailable")

    def test_rejects_invalid_utf8(self):
        content = b"\xff\xfe"
        self.source.write_bytes(content)

        invalid = IndexedFile(
            path="src/example.ts",
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
        )

        self.assert_reason(
            "invalid_encoding",
            indexed_file=invalid,
            expected_sha256=invalid.sha256,
        )

    def test_rejects_symlink_source(self):
        link = self.root / "src" / "linked.ts"

        try:
            link.symlink_to(self.source)
        except (OSError, NotImplementedError) as error:
            self.skipTest(str(error))

        invalid = IndexedFile(
            path="src/linked.ts",
            sha256=self.digest,
            size_bytes=len(self.original),
        )

        self.assert_reason(
            "unavailable",
            indexed_file=invalid,
        )


if __name__ == "__main__":
    unittest.main()
