
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

        self.assertEqual(result["total_matches"], 1)
        self.assertFalse(result["truncated"])


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


    def test_empty_snapshot_returns_no_evidence(self):
        result = answer_symbol_question(
            [],
            "Where is RootLayout?",
        )

        self.assertEqual(result["evidence"], [])
        self.assertIn(
            "No explicitly named symbol",
            result["answer"],
        )


        self.assertEqual(result["total_matches"], 0)
        self.assertFalse(result["truncated"])



    def test_evidence_is_limited_to_ten_results(self):
        files = [
            IndexedFile(
                path=f"src/module_{number:02d}.ts",
                sha256="a" * 64,
                size_bytes=50,
                symbols=(
                    IndexedSymbol(
                        name="sharedFunction",
                        kind="function",
                        line=1,
                    ),
                ),
            )
            for number in range(15)
        ]

        result = answer_symbol_question(
            files,
            "Where is sharedFunction defined?",
        )

        self.assertEqual(
            len(result["evidence"]),
            10,
        )

        self.assertEqual(result["total_matches"], 15)
        self.assertTrue(result["truncated"])
        self.assertIn("Showing the first 10", result["answer"])


    def test_evidence_order_is_deterministic(self):
        first = IndexedFile(
            path="src/z.ts",
            sha256="a" * 64,
            size_bytes=50,
            symbols=(
                IndexedSymbol(
                    name="sharedFunction",
                    kind="function",
                    line=3,
                ),
            ),
        )

        second = IndexedFile(
            path="src/a.ts",
            sha256="b" * 64,
            size_bytes=50,
            symbols=(
                IndexedSymbol(
                    name="sharedFunction",
                    kind="function",
                    line=5,
                ),
            ),
        )

        result = answer_symbol_question(
            [first, second],
            "Where is sharedFunction?",
        )

        paths = [
            item["path"]
            for item in result["evidence"]
        ]

        self.assertEqual(
            paths,
            ["src/a.ts", "src/z.ts"],
        )


if __name__ == "__main__":
    unittest.main()
