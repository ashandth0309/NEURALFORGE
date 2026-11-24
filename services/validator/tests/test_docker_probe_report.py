
"""Tests for structured, read-only recovery reports."""

import json
import tempfile
import unittest
from pathlib import Path

from services.validator.docker_probe_journal import (
    ProbeJournal,
)
from services.validator.docker_probe_reconciliation import (
    ProbeDiscovery,
)
from services.validator.docker_probe_recovery import (
    RecoveryAssessment,
)
from services.validator.docker_probe_report import (
    build_recovery_report,
)


class DockerProbeReportTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        path = Path(self.temp.name) / "journal.sqlite3"
        self.journal = ProbeJournal(path)
        self.journal.initialize()

        self.name = "neuralforge-probe-" + "a" * 24
        self.image_id = "sha256:" + "b" * 64

        self.journal.prepare(self.name, self.image_id)
        self.journal.advance(
            self.name,
            "prepared",
            "create_requested",
        )

        self.record = self.journal.get(self.name)

    def test_absence_never_authorizes_retry(self):
        assessment = RecoveryAssessment(
            record=self.record,
            discovery=ProbeDiscovery("absent_at_check"),
        )

        report = build_recovery_report([assessment])

        self.assertTrue(report["recovery_required"])
        self.assertEqual(report["unresolved_count"], 1)
        self.assertFalse(
            report["records"][0]["safe_to_retry"]
        )
        self.assertFalse(
            report["records"][0]["automatic_cleanup_allowed"]
        )
        self.assertEqual(
            self.journal.get(self.name).phase,
            "create_requested",
        )

        # The complete report must be JSON serializable.
        json.dumps(report)

    def test_present_owned_remains_blocked(self):
        container_id = "c" * 64

        assessment = RecoveryAssessment(
            record=self.record,
            discovery=ProbeDiscovery(
                "present_owned",
                container_id,
            ),
        )

        report = build_recovery_report([assessment])

        self.assertEqual(
            report["records"][0]["discovered_container_id"],
            container_id,
        )
        self.assertTrue(
            report["records"][0]["requires_manual_review"]
        )
        self.assertFalse(
            report["records"][0]["safe_to_retry"]
        )

    def test_empty_assessments(self):
        report = build_recovery_report([])

        self.assertEqual(report["unresolved_count"], 0)
        self.assertFalse(report["recovery_required"])
        self.assertEqual(report["records"], [])

    def test_invalid_assessment_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "invalid_recovery_assessment",
        ):
            build_recovery_report(["invalid"])


if __name__ == "__main__":
    unittest.main()
