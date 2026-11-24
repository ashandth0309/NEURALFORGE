
"""Integration tests for the validator service dispatcher.

Uses temporary SQLite databases and real OS file locks.
Docker discovery is disabled or mocked.
Does not contact the real Docker daemon or persistent journal.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.validator.docker_probe_journal import (
    ProbeJournal,
)
from services.validator.service_dispatcher import (
    dispatch_service_request,
)


OPERATOR = "services.validator.docker_probe_operator"

VALID_REQUEST = (
    b'{"version":1,"operation":"recovery.inspect"}'
)


class ServiceIntegrationTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.database = (
            Path(self.temp.name) / "recovery.sqlite3"
        )

        self.journal = ProbeJournal(self.database)
        self.journal.initialize()

        self.name = "neuralforge-probe-" + "a" * 24
        self.image_id = "sha256:" + "b" * 64

    def test_empty_journal_returns_safe_read_only_report(self):
        with patch(
            OPERATOR + ".open_persistent_probe_journal",
            return_value=self.journal,
        ), patch(
            OPERATOR + ".resolve_docker_executable"
        ) as docker:
            raw = dispatch_service_request(VALID_REQUEST)

        response = json.loads(raw)

        self.assertTrue(response["success"])
        self.assertTrue(response["report"]["read_only"])
        self.assertEqual(
            response["report"]["unresolved_count"],
            0,
        )
        self.assertFalse(
            response["report"]["recovery_required"]
        )
        self.assertFalse(
            response["report"]["automatic_cleanup_allowed"]
        )

        docker.assert_not_called()
        self.assertEqual(self.journal.unresolved(), [])

    def test_unresolved_journal_remains_unresolved(self):
        self.journal.prepare(
            self.name,
            self.image_id,
        )

        self.journal.advance(
            self.name,
            "prepared",
            "create_requested",
        )

        with patch(
            OPERATOR + ".open_persistent_probe_journal",
            return_value=self.journal,
        ), patch(
            OPERATOR + ".resolve_docker_executable",
            return_value=None,
        ):
            raw = dispatch_service_request(VALID_REQUEST)

        response = json.loads(raw)

        self.assertTrue(response["success"])

        report = response["report"]

        self.assertTrue(report["recovery_required"])
        self.assertEqual(report["unresolved_count"], 1)
        self.assertFalse(report["automatic_cleanup_allowed"])
        self.assertFalse(report["docker_available"])

        record = report["records"][0]

        self.assertEqual(
            record["discovery_status"],
            "uncertain",
        )
        self.assertTrue(
            record["requires_manual_review"]
        )
        self.assertFalse(record["safe_to_retry"])

        # Verify the dispatcher did not change the
        # persisted lifecycle record.
        reopened = ProbeJournal(self.database)
        persisted = reopened.get(self.name)

        self.assertIsNotNone(persisted)
        self.assertEqual(
            persisted.phase,
            "create_requested",
        )
        self.assertIsNone(persisted.container_id)

    def test_missing_journal_fails_closed(self):
        missing = (
            Path(self.temp.name) / "missing.sqlite3"
        )

        missing_journal = ProbeJournal(missing)

        with patch(
            OPERATOR + ".open_persistent_probe_journal",
            return_value=missing_journal,
        ), patch(
            OPERATOR + ".resolve_docker_executable"
        ) as docker:
            raw = dispatch_service_request(VALID_REQUEST)

        response = json.loads(raw)

        self.assertFalse(response["success"])
        self.assertEqual(
            response["recovery_status"],
            "unknown",
        )
        self.assertFalse(response["safe_to_retry"])

        self.assertFalse(missing.exists())
        docker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
