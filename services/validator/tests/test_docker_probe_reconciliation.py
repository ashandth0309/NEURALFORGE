
"""Tests for read-only Docker probe reconciliation."""

import json
import subprocess
import unittest
from unittest.mock import Mock

from services.validator.docker_probe_reconciliation import (
    reconcile_probe_presence,
)


class ProbeReconciliationTests(unittest.TestCase):

    def setUp(self):
        self.name = "neuralforge-probe-" + "a" * 24
        self.container_id = "b" * 64
        self.image_id = "sha256:" + "c" * 64

        self.metadata = {
            "Id": self.container_id,
            "Name": "/" + self.name,
            "Image": self.image_id,
            "Config": {
                "Labels": {
                    "com.neuralforge.probe.name": self.name,
                },
            },
        }

    @staticmethod
    def result(output=b"", code=0):
        return subprocess.CompletedProcess(
            args=[],
            returncode=code,
            stdout=output,
            stderr=b"",
        )

    def inspect_result(self, metadata=None):
        return self.result(
            json.dumps(
                self.metadata
                if metadata is None
                else metadata
            ).encode()
        )

    def list_result(self):
        return self.result(
            (self.container_id + "\n").encode()
        )

    def discover(self, responses, **kwargs):
        runner = Mock(side_effect=responses)

        outcome = reconcile_probe_presence(
            executable=r"C:\Docker\docker.exe",
            container_name=self.name,
            expected_image_id=self.image_id,
            runner=runner,
            **kwargs,
        )

        # This module must issue read-only commands only.
        for call in runner.call_args_list:
            command = call.args[0]
            self.assertNotIn("rm", command)
            self.assertNotIn("start", command)
            self.assertNotIn("stop", command)
            self.assertNotIn("create", command)
            self.assertNotIn("run", command)

        return outcome, runner

    def test_owned_container(self):
        result, runner = self.discover([
            self.inspect_result(),
            self.list_result(),
        ])

        self.assertEqual(result.status, "present_owned")
        self.assertEqual(result.container_id, self.container_id)
        self.assertEqual(runner.call_count, 2)

    def test_absent_at_check(self):
        result, _ = self.discover([
            self.result(code=1),
            self.result(),
        ])

        self.assertEqual(result.status, "absent_at_check")

    def test_inspection_failure_with_listed_container(self):
        result, _ = self.discover([
            self.result(code=1),
            self.list_result(),
        ])

        self.assertEqual(result.status, "uncertain")

    def test_wrong_ownership_label(self):
        metadata = json.loads(json.dumps(self.metadata))
        metadata["Config"]["Labels"] = {
            "com.neuralforge.probe.name": "unrelated",
        }

        result, _ = self.discover([
            self.inspect_result(metadata),
            self.list_result(),
        ])

        self.assertEqual(result.status, "mismatch")

    def test_wrong_image(self):
        metadata = dict(self.metadata)
        metadata["Image"] = "sha256:" + "d" * 64

        result, _ = self.discover([
            self.inspect_result(metadata),
            self.list_result(),
        ])

        self.assertEqual(result.status, "mismatch")

    def test_wrong_expected_id(self):
        result, _ = self.discover(
            [
                self.inspect_result(),
                self.list_result(),
            ],
            expected_container_id="d" * 64,
        )

        self.assertEqual(result.status, "mismatch")

    def test_contradictory_docker_results(self):
        result, _ = self.discover([
            self.inspect_result(),
            self.result(),
        ])

        self.assertEqual(result.status, "uncertain")

    def test_docker_cli_error(self):
        result, _ = self.discover([
            OSError("Docker unavailable"),
        ])

        self.assertEqual(result.status, "uncertain")

    def test_invalid_metadata(self):
        result, _ = self.discover([
            self.result(b"not-json"),
            self.list_result(),
        ])

        self.assertEqual(result.status, "uncertain")

    def test_rejects_invalid_probe_name(self):
        with self.assertRaises(ValueError):
            reconcile_probe_presence(
                executable=r"C:\Docker\docker.exe",
                container_name="unrelated-container",
                expected_image_id=self.image_id,
                runner=Mock(),
            )


if __name__ == "__main__":
    unittest.main()
