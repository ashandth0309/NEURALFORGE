
"""Tests for read-only lifecycle recovery assessments."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from services.validator.docker_probe_journal import (
    ProbeJournal,
)
from services.validator.docker_probe_reconciliation import (
    ProbeDiscovery,
)
from services.validator.docker_probe_recovery import (
    assess_unresolved_probes,
)


class ProbeRecoveryTests(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

        database = (
            Path(self.directory.name) / "recovery.sqlite3"
        )

        self.journal = ProbeJournal(database)
        self.journal.initialize()

        self.name = "neuralforge-probe-" + "a" * 24
        self.image_id = "sha256:" + "b" * 64
        self.container_id = "c" * 64
        self.executable = r"C:\Docker\docker.exe"

    def prepare_created_record(self):
        self.journal.prepare(
            self.name,
            self.image_id,
        )
        self.journal.advance(
            self.name,
            "prepared",
            "create_requested",
        )
        self.journal.advance(
            self.name,
            "create_requested",
            "created",
            container_id=self.container_id,
        )

    def test_recovers_created_container_identity(self):
        self.prepare_created_record()

        discover = Mock(
            return_value=ProbeDiscovery(
                "present_owned",
                self.container_id,
            )
        )

        assessments = assess_unresolved_probes(
            self.journal,
            self.executable,
            discover=discover,
        )

        self.assertEqual(len(assessments), 1)
        self.assertEqual(
            assessments[0].discovery.status,
            "present_owned",
        )

        discover.assert_called_once_with(
            executable=self.executable,
            container_name=self.name,
            expected_image_id=self.image_id,
            expected_container_id=self.container_id,
        )

        # Recovery assessment must not mutate the journal.
        self.assertEqual(
            self.journal.get(self.name).phase,
            "created",
        )

    def test_absence_does_not_mark_record_removed(self):
        self.prepare_created_record()

        assessments = assess_unresolved_probes(
            self.journal,
            self.executable,
            discover=Mock(
                return_value=ProbeDiscovery(
                    "absent_at_check"
                )
            ),
        )

        self.assertEqual(
            assessments[0].discovery.status,
            "absent_at_check",
        )

        self.assertEqual(
            self.journal.get(self.name).phase,
            "created",
        )
        self.assertEqual(
            len(self.journal.unresolved()),
            1,
        )

    def test_docker_error_becomes_uncertain(self):
        self.prepare_created_record()

        assessments = assess_unresolved_probes(
            self.journal,
            self.executable,
            discover=Mock(
                side_effect=OSError(
                    "Docker daemon unavailable"
                )
            ),
        )

        self.assertEqual(
            assessments[0].discovery.status,
            "uncertain",
        )

        self.assertEqual(
            self.journal.get(self.name).phase,
            "created",
        )

    def test_rejects_conflicting_discovered_id(self):
        self.prepare_created_record()

        assessments = assess_unresolved_probes(
            self.journal,
            self.executable,
            discover=Mock(
                return_value=ProbeDiscovery(
                    "present_owned",
                    "d" * 64,
                )
            ),
        )

        self.assertEqual(
            assessments[0].discovery.status,
            "uncertain",
        )

    def test_removed_records_are_not_assessed(self):
        self.prepare_created_record()

        self.journal.advance(
            self.name,
            "created",
            "verified",
        )
        self.journal.advance(
            self.name,
            "verified",
            "removed",
        )

        discover = Mock()

        assessments = assess_unresolved_probes(
            self.journal,
            self.executable,
            discover=discover,
        )

        self.assertEqual(assessments, [])
        discover.assert_not_called()

    
    def test_rejects_excessive_recovery_records(self):
        self.journal.prepare(
            self.name,
            self.image_id,
        )
        self.journal.prepare(
            "neuralforge-probe-" + "e" * 24,
            self.image_id,
        )

        discover = Mock()

        with self.assertRaisesRegex(
            RuntimeError,
            "recovery_record_limit_exceeded",
        ):
            assess_unresolved_probes(
                self.journal,
                self.executable,
                discover=discover,
                max_records=1,
            )

        discover.assert_not_called()


    def _check_limit(self, discover):
        self.journal.prepare(
            "neuralforge-probe-" + "e" * 24,
            self.image_id,
        )
        return assess_unresolved_probes(
            self.journal,
            self.executable,
            discover=discover,
            max_records=1,
        )


if __name__ == "__main__":
    unittest.main()
