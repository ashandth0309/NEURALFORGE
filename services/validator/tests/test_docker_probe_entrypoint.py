
"""Tests for the persistent fixed-diagnostic entry point."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from services.validator.docker_probe_entrypoint import (
    run_persistent_fixed_docker_probe,
)
from services.validator.docker_probe_journal import ProbeJournal
from services.validator.isolation import IsolationPolicy


MODULE = "services.validator.docker_probe_entrypoint"


class PersistentProbeEntrypointTests(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

        self.database = (
            Path(self.directory.name) / "probes.sqlite3"
        )

        self.journal = ProbeJournal(self.database)
        self.journal.initialize()

        self.reference = "node@sha256:" + "a" * 64
        self.image_id = "sha256:" + "b" * 64
        self.policy = IsolationPolicy(image=self.reference)
        self.approved = frozenset({self.reference})

    def test_uses_validated_persistent_journal(self):
        evidence = object()

        with patch(
            MODULE + ".open_persistent_probe_journal",
            return_value=self.journal,
        ) as storage, patch(
            MODULE + ".run_fixed_docker_probe",
            return_value=evidence,
        ) as controller:
            result = run_persistent_fixed_docker_probe(
                self.policy,
                self.approved,
                self.image_id,
            )

        self.assertIs(result, evidence)
        storage.assert_called_once_with()
        controller.assert_called_once_with(
            self.policy,
            self.approved,
            self.image_id,
            journal=self.journal,
        )

    def test_storage_failure_prevents_controller_execution(self):
        with patch(
            MODULE + ".open_persistent_probe_journal",
            side_effect=RuntimeError(
                "probe_storage_missing"
            ),
        ), patch(
            MODULE + ".run_fixed_docker_probe",
        ) as controller:
            with self.assertRaisesRegex(
                RuntimeError,
                "probe_storage_missing",
            ):
                run_persistent_fixed_docker_probe(
                    self.policy,
                    self.approved,
                    self.image_id,
                )

        controller.assert_not_called()

    def test_does_not_suppress_controller_failure(self):
        with patch(
            MODULE + ".open_persistent_probe_journal",
            return_value=self.journal,
        ), patch(
            MODULE + ".run_fixed_docker_probe",
            side_effect=RuntimeError(
                "docker_probe_recovery_required"
            ),
        ) as controller:
            with self.assertRaisesRegex(
                RuntimeError,
                "docker_probe_recovery_required",
            ):
                run_persistent_fixed_docker_probe(
                    self.policy,
                    self.approved,
                    self.image_id,
                )

        controller.assert_called_once()


if __name__ == "__main__":
    unittest.main()
