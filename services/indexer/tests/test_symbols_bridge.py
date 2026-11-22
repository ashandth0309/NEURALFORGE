
import unittest

from services.indexer.symbols_bridge import extract_symbols


class SymbolsBridgeTests(unittest.TestCase):

    def test_extracts_function(self):
        symbols = extract_symbols(
            "example.ts",
            "export function greet() { return 'hello'; }"
        )
        self.assertEqual(symbols[0]["name"], "greet")
        self.assertEqual(symbols[0]["kind"], "function")
        self.assertEqual(symbols[0]["line"], 1)

    def test_extracts_interface(self):
        symbols = extract_symbols(
            "user.ts",
            "export interface User { id: string }"
        )
        self.assertEqual(symbols[0]["name"], "User")
        self.assertEqual(symbols[0]["kind"], "interface")

    def test_rejects_invalid_extension(self):
        with self.assertRaises((ValueError, RuntimeError)):
            extract_symbols("invalid.py", "print('hello')")

    def test_rejects_oversized_source(self):
        with self.assertRaises(ValueError):
            extract_symbols(
                "large.ts",
                "x" * (1024 * 1024 + 1)
            )


if __name__ == "__main__":
    unittest.main()
