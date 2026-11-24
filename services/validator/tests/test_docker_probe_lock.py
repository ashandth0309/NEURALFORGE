
"""Tests for cross-process Docker probe locking."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from services.validator.docker_probe_lock import (
    exclusive_probe_lock,
)


class ProbeLockTests(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

        self.database = (
            Path(self.directory.name) / "probes.sqlite3"
        )

    def try_child_lock(self):
        script = """
import sys

from services.validator.docker_probe_lock import (
    exclusive_probe_lock,
)

try:
    with exclusive_probe_lock(sys.argv[1]):
        print("ACQUIRED")
except RuntimeError as exc:
    if str(exc) == "docker_probe_lock_unavailable":
        print("BLOCKED")
    else:
        raise
"""

        return subprocess.run(
            [
                sys.executable,
                "-c",
                script,
                str(self.database),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        ).stdout.strip()

    def test_lock_can_be_acquired(self):
        with exclusive_probe_lock(self.database):
            self.assertTrue(
                Path(str(self.database) + ".lock").exists()
            )

    def test_second_process_cannot_acquire_held_lock(self):
        with exclusive_probe_lock(self.database):
            self.assertEqual(
                self.try_child_lock(),
                "BLOCKED",
            )

    def test_lock_is_released_after_context_exit(self):
        with exclusive_probe_lock(self.database):
            pass

        self.assertEqual(
            self.try_child_lock(),
            "ACQUIRED",
        )

    def test_lock_is_released_after_exception(self):
        with self.assertRaisesRegex(
            ValueError,
            "simulated_failure",
        ):
            with exclusive_probe_lock(self.database):
                raise ValueError("simulated_failure")

        self.assertEqual(
            self.try_child_lock(),
            "ACQUIRED",
        )


if __name__ == "__main__":
    unittest.main()
