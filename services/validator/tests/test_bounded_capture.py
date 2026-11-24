
"""Tests for bounded subprocess output capture."""

import os
import sys
import unittest

from services.validator.bounded_capture import (
    BoundedOutputError,
    BoundedProcessTimeout,
    run_bounded,
)


class BoundedCaptureTests(unittest.TestCase):

    def command(self, code):
        return [sys.executable, "-c", code]

    def run_command(self, code, **kwargs):
        return run_bounded(
            self.command(code),
            env=dict(os.environ),
            **kwargs,
        )

    def test_accepts_small_output(self):
        result = self.run_command(
            "print('NEURALFORGE_OK')"
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout.strip(),
            b"NEURALFORGE_OK",
        )

    def test_accepts_output_at_exact_limit(self):
        result = self.run_command(
            "import sys; sys.stdout.write('x'*64)",
            max_output_bytes=64,
        )

        self.assertEqual(len(result.stdout), 64)

    def test_rejects_oversized_output(self):
        with self.assertRaises(BoundedOutputError):
            self.run_command(
                "import sys; sys.stdout.write('x'*100000)",
                max_output_bytes=1024,
            )

    def test_enforces_timeout(self):
        with self.assertRaises(BoundedProcessTimeout):
            self.run_command(
                "import time; time.sleep(5)",
                timeout_seconds=0.2,
            )

    def test_preserves_nonzero_exit_code(self):
        result = self.run_command(
            "import sys; sys.exit(7)"
        )

        self.assertEqual(result.returncode, 7)

    def test_rejects_invalid_output_limit(self):
        with self.assertRaises(ValueError):
            self.run_command(
                "print('hello')",
                max_output_bytes=0,
            )

    def test_rejects_invalid_timeout(self):
        with self.assertRaises(ValueError):
            self.run_command(
                "print('hello')",
                timeout_seconds=0,
            )

    def test_rejects_empty_command(self):
        with self.assertRaises(ValueError):
            run_bounded(
                [],
                env=dict(os.environ),
            )


if __name__ == "__main__":
    unittest.main()
