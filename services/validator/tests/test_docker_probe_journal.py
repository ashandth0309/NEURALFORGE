
"""Tests for persistent Docker probe lifecycle records."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.validator.docker_probe_journal import (
    ProbeJournal,
)


class ProbeJournalTests(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

        self.path = (
            Path(self.directory.name) / "probes.sqlite3"
        )

        self.journal = ProbeJournal(self.path)
        self.journal.initialize()

        self.name = "neuralforge-probe-" + "a" * 24
        self.image_id = "sha256:" + "b" * 64
        self.container_id = "c" * 64

    def test_prepare_record(self):
        self.journal.prepare(self.name, self.image_id)

        record = self.journal.get(self.name)

        self.assertEqual(record.phase, "prepared")
        self.assertEqual(record.image_id, self.image_id)
        self.assertIsNone(record.container_id)

    def test_records_survive_reopen(self):
        self.journal.prepare(self.name, self.image_id)

        reopened = ProbeJournal(self.path)
        record = reopened.get(self.name)

        self.assertEqual(record.phase, "prepared")

    def test_record_container_identity(self):
        self.journal.prepare(self.name, self.image_id)
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

        record = self.journal.get(self.name)

        self.assertEqual(
            record.container_id,
            self.container_id,
        )

    def test_rejects_duplicate_probe(self):
        self.journal.prepare(self.name, self.image_id)

        with self.assertRaises(sqlite3.IntegrityError):
            self.journal.prepare(self.name, self.image_id)

    def test_rejects_invalid_transition(self):
        self.journal.prepare(self.name, self.image_id)

        with self.assertRaises(ValueError):
            self.journal.advance(
                self.name,
                "prepared",
                "removed",
            )

    def test_rejects_stale_phase(self):
        self.journal.prepare(self.name, self.image_id)

        with self.assertRaisesRegex(
            ValueError,
            "probe_phase_conflict",
        ):
            self.journal.advance(
                self.name,
                "created",
                "verified",
            )

    def test_rejects_container_id_replacement(self):
        self.journal.prepare(self.name, self.image_id)
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

        with self.assertRaisesRegex(
            ValueError,
            "probe_container_id_conflict",
        ):
            self.journal.advance(
                self.name,
                "created",
                "verified",
                container_id="d" * 64,
            )

    def test_unresolved_records(self):
        self.journal.prepare(self.name, self.image_id)

        records = self.journal.unresolved()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].name, self.name)

    def test_removed_records_not_unresolved(self):
        self.journal.prepare(self.name, self.image_id)
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

        self.assertEqual(self.journal.unresolved(), [])

    def test_missing_record(self):
        self.assertIsNone(self.journal.get(self.name))


if __name__ == "__main__":
    unittest.main()
