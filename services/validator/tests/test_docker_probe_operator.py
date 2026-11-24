
"""Tests for the read-only recovery operator command."""

import unittest
from io import StringIO
from unittest.mock import Mock, patch

from services.validator.docker_probe_operator import (
    inspect_persistent_recovery,
    main,
)
from services.validator.docker_probe_reconciliation import (
    ProbeDiscovery,
)


MODULE = "services.validator.docker_probe_operator"


class DummyLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DockerProbeOperatorTests(unittest.TestCase):

    def setUp(self):
        self.journal = Mock()
        self.journal.path = "test.sqlite3"

        self.lock_patch = patch(
            MODULE + ".exclusive_probe_lock",
            return_value=DummyLock(),
        )
        self.storage_patch = patch(
            MODULE + ".open_persistent_probe_journal",
            return_value=self.journal,
        )

        self.lock_patch.start()
        self.storage_patch.start()

        self.addCleanup(self.lock_patch.stop)
        self.addCleanup(self.storage_patch.stop)

    def test_empty_journal_never_contacts_docker(self):
        self.journal.unresolved.return_value = []

        with patch(
            MODULE + ".resolve_docker_executable"
        ) as resolve, patch(
            MODULE + ".assess_unresolved_probes"
        ) as assess:
            report = inspect_persistent_recovery()

        self.assertEqual(report["unresolved_count"], 0)
        self.assertFalse(report["recovery_required"])
        self.assertIsNone(report["docker_available"])

        resolve.assert_not_called()
        assess.assert_not_called()

    def test_missing_docker_preserves_uncertainty(self):
        self.journal.unresolved.return_value = [Mock()]

        with patch(
            MODULE + ".resolve_docker_executable",
            return_value=None,
        ), patch(
            MODULE + ".assess_unresolved_probes",
            return_value=[],
        ) as assess:
            report = inspect_persistent_recovery()

        self.assertFalse(report["docker_available"])
        assess.assert_called_once()

        # Validate that the injected discovery callback
        # refuses to interpret unavailable Docker as absence.
        callback = assess.call_args.kwargs["discover"]
        self.assertEqual(
            callback().status,
            "uncertain",
        )

    def test_docker_available_uses_recovery_assessment(self):
        self.journal.unresolved.return_value = [Mock()]

        with patch(
            MODULE + ".resolve_docker_executable",
            return_value="C:/Docker/docker.exe",
        ), patch(
            MODULE + ".assess_unresolved_probes",
            return_value=[],
        ) as assess:
            report = inspect_persistent_recovery()

        self.assertTrue(report["docker_available"])
        assess.assert_called_once_with(
            self.journal,
            "C:/Docker/docker.exe",
        )

    def test_main_reports_inspection_failure(self):
        with patch(
            MODULE + ".inspect_persistent_recovery",
            side_effect=RuntimeError(
                "probe_storage_missing"
            ),
        ), patch(
            "sys.stderr",
            new_callable=StringIO,
        ) as stderr:
            code = main()

        self.assertEqual(code, 1)
        self.assertIn(
            "recovery_inspection_failed",
            stderr.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
