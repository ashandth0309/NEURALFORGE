
import unittest

from services.indexer.retrieval import search_symbols


class RetrievalTests(unittest.TestCase):

    def setUp(self):
        self.index = [
            {
                "path": "src/app/layout.tsx",
                "symbols": [
                    {
                        "name": "RootLayout",
                        "kind": "function",
                        "line": 20,
                    },
                    {
                        "name": "metadata",
                        "kind": "variable",
                        "line": 15,
                    },
                ],
            },
            {
                "path": "src/app/page.tsx",
                "symbols": [
                    {
                        "name": "Home",
                        "kind": "function",
                        "line": 3,
                    },
                    {
                        "name": "HomePage",
                        "kind": "function",
                        "line": 10,
                    },
                ],
            },
        ]

    def test_exact_match(self):
        results = search_symbols(self.index, "RootLayout")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["line"], 20)
        self.assertEqual(results[0]["score"], 100)

    def test_case_insensitive_search(self):
        results = search_symbols(self.index, "rootlayout")
        self.assertEqual(results[0]["name"], "RootLayout")

    def test_exact_before_prefix(self):
        results = search_symbols(self.index, "Home")
        self.assertEqual(
            [item["name"] for item in results],
            ["Home", "HomePage"],
        )

    def test_substring_match(self):
        results = search_symbols(self.index, "Layout")
        self.assertEqual(results[0]["name"], "RootLayout")
        self.assertEqual(results[0]["score"], 60)

    def test_no_matches(self):
        self.assertEqual(
            search_symbols(self.index, "Nonexistent"),
            [],
        )

    def test_rejects_empty_query(self):
        with self.assertRaises(ValueError):
            search_symbols(self.index, "   ")

    def test_rejects_invalid_limit(self):
        with self.assertRaises(ValueError):
            search_symbols(self.index, "Home", 0)

    def test_respects_limit(self):
        results = search_symbols(self.index, "Home", 1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Home")


    def test_rejects_non_string_query(self):
        with self.assertRaises(TypeError):
            search_symbols(self.index, 123)

    def test_rejects_overlong_query(self):
        with self.assertRaises(ValueError):
            search_symbols(self.index, "x" * 101)

    def test_rejects_boolean_limit(self):
        with self.assertRaises(ValueError):
            search_symbols(self.index, "Home", True)


    def test_rejects_invalid_source_path(self):
        bad_index = [{
            "path": "../secret.ts",
            "symbols": []
        }]

        with self.assertRaises(ValueError):
            search_symbols(bad_index, "secret")

    def test_rejects_invalid_symbol_line(self):
        bad_index = [{
            "path": "src/example.ts",
            "symbols": [{
                "name": "example",
                "kind": "function",
                "line": -1
            }]
        }]

        with self.assertRaises(ValueError):
            search_symbols(bad_index, "example")

    def test_rejects_invalid_symbol_kind(self):
        bad_index = [{
            "path": "src/example.ts",
            "symbols": [{
                "name": "example",
                "kind": "unknown",
                "line": 1
            }]
        }]

        with self.assertRaises(ValueError):
            search_symbols(bad_index, "example")


    def test_rejects_windows_absolute_path(self):
        bad_index = [{
            "path": "C:/private/secret.ts",
            "symbols": []
        }]

        with self.assertRaises(ValueError):
            search_symbols(bad_index, "secret")

    def test_rejects_control_character_in_path(self):
        bad_index = [{
            "path": "src/\nsecret.ts",
            "symbols": []
        }]

        with self.assertRaises(ValueError):
            search_symbols(bad_index, "secret")




if __name__ == "__main__":
    unittest.main()
