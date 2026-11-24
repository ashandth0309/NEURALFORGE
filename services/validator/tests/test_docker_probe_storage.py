
"""Tests for persistent Docker probe journal configuration."""

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.validator.docker_probe_journal import ProbeJournal
from services.validator.docker_probe_storage import (
    open_persistent_probe_journal,
)


class ProbeStorageTests(unittest.TestCase):

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)

        self.root = Path(self.temporary.name)
        self.directory = self.root / "NEURALFORGE" / "validator"
        self.directory.mkdir(parents=True)

        self.database = (
            self.directory / "probe_lifecycle.sqlite3"
        )

        self.environment = patch.dict(
            os.environ,
            {"LOCALAPPDATA": str(self.root)},
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def initialize_database(self):
        journal = ProbeJournal(self.database)
        journal.initialize()
        return journal

    def test_opens_existing_journal(self):
        self.initialize_database()

        journal = open_persistent_probe_journal()

        self.assertEqual(journal.path, self.database)
        self.assertEqual(journal.unresolved(), [])

    def test_missing_database_is_rejected(self):
        with self.assertRaisesRegex(
            RuntimeError,
            "probe_storage_missing",
        ):
            open_persistent_probe_journal()

        self.assertFalse(self.database.exists())

    def test_invalid_database_is_rejected(self):
        self.database.write_bytes(
            b"This is not a SQLite database"
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "probe_storage_database_invalid",
        ):
            open_persistent_probe_journal()

    def test_existing_unresolved_record_survives_reopen(self):
        original = self.initialize_database()

        name = "neuralforge-probe-" + "a" * 24
        image_id = "sha256:" + "b" * 64

        original.prepare(name, image_id)

        reopened = open_persistent_probe_journal()
        records = reopened.unresolved()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].name, name)
        self.assertEqual(records[0].phase, "prepared")

    def test_missing_localappdata_is_rejected(self):
        self.initialize_database()

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                RuntimeError,
                "probe_storage_location_missing",
            ):
                open_persistent_probe_journal()


if __name__ == "__main__":
    unittest.main()
