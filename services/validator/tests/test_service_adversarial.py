"""Adversarial service integration using temporary SQLite and mocked Docker.

No actual Docker daemon is contacted. Real journal, real OS lock.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.validator.docker_probe_journal import ProbeJournal
from services.validator.docker_probe_lock import exclusive_probe_lock
from services.validator.service_dispatcher import dispatch_service_request

OPERATOR = "services.validator.docker_probe_operator"
REQUEST = b'{"version":1,"operation":"recovery.inspect"}'


class ServiceAdversarialTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "recovery.sqlite3"
        self.journal = ProbeJournal(self.path)
        self.journal.initialize()
        self.storage_patch = patch(
            OPERATOR + ".open_persistent_probe_journal", return_value=self.journal,
        )
        self.storage_patch.start()
        self.addCleanup(self.storage_patch.stop)

    def dispatch(self):
        return json.loads(dispatch_service_request(REQUEST))

    def test_held_lock_reports_unknown_and_does_not_contact_docker(self):
        with patch(OPERATOR + ".resolve_docker_executable") as resolve:
            with exclusive_probe_lock(self.path):
                response = self.dispatch()
        self.assertFalse(response["success"])
        self.assertEqual(response["recovery_status"], "unknown")
        self.assertFalse(response["safe_to_retry"])
        resolve.assert_not_called()

    def test_missing_database_does_not_recreate_or_contact_docker(self):
        self.path.unlink()
        with patch(OPERATOR + ".resolve_docker_executable") as resolve:
            response = self.dispatch()
        self.assertFalse(response["success"])
        self.assertFalse(self.path.exists())
        resolve.assert_not_called()

    def test_corrupt_database_does_not_report_recovery_safe(self):
        self.path.write_bytes(b"not-a-sqlite-database")
        with patch(OPERATOR + ".resolve_docker_executable") as resolve:
            response = self.dispatch()
        self.assertFalse(response["success"])
        self.assertFalse(response["safe_to_retry"])
        resolve.assert_not_called()

    def test_bad_request_does_not_open_storage(self):
        with patch(OPERATOR + ".open_persistent_probe_journal") as storage:
            with self.assertRaises(ValueError):
                dispatch_service_request(
                    b'{"version":1,"operation":"docker.run"}'
                )
        storage.assert_not_called()

    def test_empty_journal_does_not_discover_docker(self):
        with patch(OPERATOR + ".resolve_docker_executable") as resolve:
            response = self.dispatch()
        self.assertTrue(response["success"])
        self.assertEqual(response["report"]["unresolved_count"], 0)
        resolve.assert_not_called()

    def test_discovery_exception_reports_unknown_without_clearing_record(self):
        name = "neuralforge-probe-" + "a" * 24
        self.journal.prepare(name, "sha256:" + "b" * 64)
        self.journal.advance(name, "prepared", "create_requested")
        with patch(OPERATOR + ".resolve_docker_executable", return_value="C:/fake/docker.exe"), patch(
            OPERATOR + ".assess_unresolved_probes", side_effect=RuntimeError("private path")
        ):
            response = self.dispatch()
        self.assertFalse(response["success"])
        self.assertNotIn("private path", json.dumps(response))
        self.assertEqual(len(self.journal.unresolved()), 1)


if __name__ == "__main__":
    unittest.main()
