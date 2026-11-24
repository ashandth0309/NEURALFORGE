
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

    def test_journal_survives_abrupt_process_exit(self):
        """A killed worker must leave its durable intent visible."""
        import subprocess
        import sys

        script = """
import os
import sys

from services.validator.docker_probe_journal import ProbeJournal

journal = ProbeJournal(sys.argv[1])
name = sys.argv[2]
image_id = sys.argv[3]

journal.prepare(name, image_id)
journal.advance(
    name,
    "prepared",
    "create_requested",
)

os._exit(23)
"""

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                script,
                str(self.journal.path),
                self.name,
                self.image_id,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )

        # Exit code 23 confirms the child reached
        # the deliberate abrupt-termination point.
        self.assertEqual(
            result.returncode,
            23,
            msg=result.stderr,
        )

        # Reopen SQLite in the surviving process.
        reopened = ProbeJournal(self.journal.path)
        record = reopened.get(self.name)

        self.assertIsNotNone(record)
        self.assertEqual(
            record.phase,
            "create_requested",
        )
        self.assertIsNone(record.container_id)

        self.assertEqual(
            len(reopened.unresolved()),
            1,
        )

    def test_late_container_appearance_remains_blocked(self):
        """An earlier absence must not authorize another probe."""
        from unittest.mock import patch

        from services.validator.docker_probe_controller import (
            run_fixed_docker_probe,
        )
        from services.validator.isolation import IsolationPolicy

        self.journal.prepare(self.name, self.image_id)
        self.journal.advance(
            self.name,
            "prepared",
            "create_requested",
        )

        discover = Mock(
            side_effect=[
                ProbeDiscovery("absent_at_check"),
                ProbeDiscovery("present_owned", self.container_id),
            ]
        )

        policy = IsolationPolicy(
            image="node@sha256:" + "a" * 64
        )
        approved = frozenset({policy.image})

        statuses = []

        for _ in range(2):
            assessments = assess_unresolved_probes(
                self.journal,
                self.executable,
                discover=discover,
            )

            self.assertEqual(len(assessments), 1)
            statuses.append(assessments[0].discovery.status)

            with patch(
                "services.validator.docker_probe_controller."
                "inspect_approved_image"
            ) as inspect_image, patch(
                "services.validator.docker_probe_controller."
                "run_bounded"
            ) as docker:
                with self.assertRaisesRegex(
                    RuntimeError,
                    "docker_probe_recovery_required",
                ):
                    run_fixed_docker_probe(
                        policy,
                        approved,
                        self.image_id,
                        journal=self.journal,
                    )

                inspect_image.assert_not_called()
                docker.assert_not_called()

        self.assertEqual(
            statuses,
            ["absent_at_check", "present_owned"],
        )
        self.assertEqual(discover.call_count, 2)

        record = self.journal.get(self.name)
        self.assertEqual(record.phase, "create_requested")
        self.assertIsNone(record.container_id)
        self.assertEqual(len(self.journal.unresolved()), 1)



if __name__ == "__main__":
    unittest.main()
