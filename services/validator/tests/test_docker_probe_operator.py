
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

class DockerProbeOperatorIntegrationTests(unittest.TestCase):
    """Real SQLite and locking, with simulated Docker discovery."""

    def setUp(self):
        import tempfile
        from pathlib import Path

        from services.validator.docker_probe_journal import (
            ProbeJournal,
        )

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        database = Path(self.temp.name) / "recovery.sqlite3"
        self.journal = ProbeJournal(database)
        self.journal.initialize()

        self.name = "neuralforge-probe-" + "a" * 24
        self.image_id = "sha256:" + "b" * 64
        self.container_id = "c" * 64

        self.journal.prepare(self.name, self.image_id)
        self.journal.advance(
            self.name,
            "prepared",
            "create_requested",
        )

        # Use the actual journal and actual OS file lock.
        self.storage = patch(
            MODULE + ".open_persistent_probe_journal",
            return_value=self.journal,
        )
        self.storage.start()
        self.addCleanup(self.storage.stop)

    def assert_journal_unchanged(self):
        from services.validator.docker_probe_journal import (
            ProbeJournal,
        )

        reopened = ProbeJournal(self.journal.path)
        record = reopened.get(self.name)

        self.assertIsNotNone(record)
        self.assertEqual(record.phase, "create_requested")
        self.assertIsNone(record.container_id)
        self.assertEqual(len(reopened.unresolved()), 1)

    def test_unavailable_docker_reports_uncertain_record(self):
        with patch(
            MODULE + ".resolve_docker_executable",
            return_value=None,
        ):
            report = inspect_persistent_recovery()

        self.assertFalse(report["docker_available"])
        self.assertTrue(report["recovery_required"])
        self.assertEqual(report["unresolved_count"], 1)

        entry = report["records"][0]

        self.assertEqual(
            entry["discovery_status"],
            "uncertain",
        )
        self.assertFalse(entry["safe_to_retry"])
        self.assertFalse(entry["automatic_cleanup_allowed"])

        self.assert_journal_unchanged()

    def test_owned_container_is_reported_without_mutation(self):
        from services.validator.docker_probe_recovery import (
            assess_unresolved_probes,
        )

        discovery = Mock(
            return_value=ProbeDiscovery(
                "present_owned",
                self.container_id,
            )
        )

        def assess(journal, executable):
            return assess_unresolved_probes(
                journal,
                executable,
                discover=discovery,
            )

        with patch(
            MODULE + ".resolve_docker_executable",
            return_value="C:/Docker/docker.exe",
        ), patch(
            MODULE + ".assess_unresolved_probes",
            side_effect=assess,
        ):
            report = inspect_persistent_recovery()

        entry = report["records"][0]

        self.assertEqual(
            entry["discovery_status"],
            "present_owned",
        )
        self.assertEqual(
            entry["discovered_container_id"],
            self.container_id,
        )
        self.assertFalse(entry["safe_to_retry"])
        self.assert_journal_unchanged()

    def test_identity_mismatch_remains_blocked(self):
        from services.validator.docker_probe_recovery import (
            assess_unresolved_probes,
        )

        def assess(journal, executable):
            return assess_unresolved_probes(
                journal,
                executable,
                discover=Mock(
                    return_value=ProbeDiscovery(
                        "mismatch",
                        "d" * 64,
                    )
                ),
            )

        with patch(
            MODULE + ".resolve_docker_executable",
            return_value="C:/Docker/docker.exe",
        ), patch(
            MODULE + ".assess_unresolved_probes",
            side_effect=assess,
        ):
            report = inspect_persistent_recovery()

        entry = report["records"][0]

        self.assertEqual(
            entry["discovery_status"],
            "mismatch",
        )
        self.assertTrue(entry["requires_manual_review"])
        self.assertFalse(entry["safe_to_retry"])
        self.assert_journal_unchanged()

    def test_held_lock_prevents_inspection(self):
        from services.validator.docker_probe_lock import (
            exclusive_probe_lock,
        )

        with patch(
            MODULE + ".resolve_docker_executable",
        ) as docker:
            with exclusive_probe_lock(self.journal.path):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "docker_probe_lock_unavailable",
                ):
                    inspect_persistent_recovery()

        docker.assert_not_called()
        self.assert_journal_unchanged()


if __name__ == "__main__":
    unittest.main()
