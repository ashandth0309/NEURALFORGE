
import unittest

from services.indexer.evidence import (
    answer_symbol_question,
)
from services.indexer.store import (
    IndexedFile,
    IndexedSymbol,
)


class EvidenceQuestionTests(unittest.TestCase):

    def setUp(self):
        self.files = [
            IndexedFile(
                path="src/app/layout.tsx",
                sha256="a" * 64,
                size_bytes=100,
                symbols=(
                    IndexedSymbol(
                        name="RootLayout",
                        kind="function",
                        line=20,
                    ),
                ),
            ),
        ]

    def test_finds_symbol_location(self):
        result = answer_symbol_question(
            self.files,
            "Where is RootLayout defined?",
        )

        self.assertEqual(len(result["evidence"]), 1)

        evidence = result["evidence"][0]

        self.assertEqual(
            evidence["path"],
            "src/app/layout.tsx",
        )
        self.assertEqual(evidence["line"], 20)
        self.assertEqual(
            evidence["sha256"],
            "a" * 64,
        )

    def test_case_insensitive_question(self):
        result = answer_symbol_question(
            self.files,
            "Where is ROOTLAYOUT?",
        )

        self.assertEqual(len(result["evidence"]), 1)

    def test_unknown_symbol_has_no_evidence(self):
        result = answer_symbol_question(
            self.files,
            "Where is UnknownFunction?",
        )

        self.assertEqual(result["evidence"], [])

    def test_rejects_empty_question(self):
        with self.assertRaises(ValueError):
            answer_symbol_question(
                self.files,
                "   ",
            )

    def test_rejects_partial_identifier(self):
        result = answer_symbol_question(
            self.files,
            "Where is RootLayoutExtra?",
        )

        self.assertEqual(result["evidence"], [])

    def test_multiple_locations_are_preserved(self):
        another_file = IndexedFile(
            path="src/other.ts",
            sha256="b" * 64,
            size_bytes=50,
            symbols=(
                IndexedSymbol(
                    name="RootLayout",
                    kind="function",
                    line=5,
                ),
            ),
        )

        result = answer_symbol_question(
            self.files + [another_file],
            "Where is RootLayout?",
        )

        self.assertEqual(len(result["evidence"]), 2)


if __name__ == "__main__":
    unittest.main()
