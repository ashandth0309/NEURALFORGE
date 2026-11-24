
"""Tests for bounded subprocess output capture."""

import os
import sys
import unittest
import time

from unittest.mock import MagicMock, patch

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


    def test_discards_large_stderr_without_deadlock(self):
        result = self.run_command(
            "import sys; "
            "sys.stderr.write('e' * 1000000); "
            "sys.stdout.write('OK')",
            timeout_seconds=5,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"OK")
        self.assertEqual(result.stderr, b"")

    def test_timeout_terminates_direct_child(self):
        processes = []

        original_popen = __import__(
            "subprocess"
        ).Popen

        def tracked_popen(*args, **kwargs):
            process = original_popen(*args, **kwargs)
            processes.append(process)
            return process

        with patch(
            "services.validator.bounded_capture."
            "subprocess.Popen",
            side_effect=tracked_popen,
        ):
            with self.assertRaises(
                BoundedProcessTimeout
            ):
                self.run_command(
                    "import time; time.sleep(10)",
                    timeout_seconds=0.2,
                )

        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].poll())

    def test_rejects_oversized_output_and_cleans_up(self):
        processes = []

        original_popen = __import__(
            "subprocess"
        ).Popen

        def tracked_popen(*args, **kwargs):
            process = original_popen(*args, **kwargs)
            processes.append(process)
            return process

        with patch(
            "services.validator.bounded_capture."
            "subprocess.Popen",
            side_effect=tracked_popen,
        ):
            with self.assertRaises(
                BoundedOutputError
            ):
                self.run_command(
                    "import sys,time; "
                    "sys.stdout.write('x'*100000); "
                    "sys.stdout.flush(); "
                    "time.sleep(10)",
                    max_output_bytes=1024,
                    timeout_seconds=5,
                )

        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].poll())

    def test_passes_explicit_environment(self):
        environment = dict(os.environ)
        environment["NEURALFORGE_CAPTURE_TEST"] = (
            "environment_verified"
        )

        result = run_bounded(
            self.command(
                "import os; "
                "print(os.environ.get("
                "'NEURALFORGE_CAPTURE_TEST', 'missing'))"
            ),
            env=environment,
        )

        self.assertEqual(
            result.stdout.strip(),
            b"environment_verified",
        )

    def test_timeout_covers_process_exit_wait(self):
        start = time.monotonic()

        with self.assertRaises(BoundedProcessTimeout):
            self.run_command(
                "import os,sys,time; "
                "sys.stdout.write('READY'); "
                "sys.stdout.flush(); "
                "os.close(sys.stdout.fileno()); "
                "time.sleep(5)",
                timeout_seconds=0.4,
            )

        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 1.5)


    def test_process_wait_uses_remaining_deadline(self):
        process = MagicMock()

        # Simulate stdout reaching EOF immediately.
        process.stdout.read1.return_value = b""
        process.wait.return_value = 0
        process.poll.return_value = 0

        with patch(
            "services.validator.bounded_capture."
            "subprocess.Popen",
            return_value=process,
        ):
            result = run_bounded(
                ["trusted-test-command"],
                env={},
                timeout_seconds=0.4,
                max_output_bytes=1024,
            )

        self.assertEqual(result.returncode, 0)
        process.wait.assert_called()

        # The process-exit wait must not receive more
        # time than the original overall deadline.
        first_wait = process.wait.call_args_list[0]
        wait_timeout = first_wait.kwargs["timeout"]

        self.assertLessEqual(wait_timeout, 0.4 + 1e-9)
        self.assertGreaterEqual(wait_timeout, 0)


if __name__ == "__main__":
    unittest.main()
