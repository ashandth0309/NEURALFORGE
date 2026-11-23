
"""Tests for read-only Docker image inspection."""

import json
import subprocess
import unittest
from dataclasses import replace
from unittest.mock import patch

from services.validator.docker_inspect import (
    inspect_approved_image,
)
from services.validator.isolation import IsolationPolicy


class DockerInspectTests(unittest.TestCase):

    def setUp(self):
        self.reference = "node@sha256:" + "a" * 64
        self.policy = IsolationPolicy(image=self.reference)
        self.approved = frozenset({self.reference})

        self.metadata = {
            "Id": "sha256:" + "b" * 64,
            "RepoDigests": [self.reference],
            "Os": "linux",
            "Architecture": "amd64",
        }

    def successful_result(self):
        return subprocess.CompletedProcess(
            args=["docker"],
            returncode=0,
            stdout=json.dumps(self.metadata).encode("utf-8"),
            stderr=b"",
        )

    def test_inspects_approved_image(self):
        with patch(
            "services.validator.docker_inspect."
            "resolve_docker_executable",
            return_value=r"C:\Docker\docker.exe",
        ):
            with patch(
                "services.validator.docker_inspect.subprocess.run",
                return_value=self.successful_result(),
            ) as mocked:
                identity = inspect_approved_image(
                    self.policy,
                    self.approved,
                )

        self.assertEqual(identity.reference, self.reference)
        self.assertEqual(identity.os, "linux")
        self.assertEqual(identity.architecture, "amd64")

        args = mocked.call_args.args[0]
        self.assertEqual(args[0], r"C:\Docker\docker.exe")
        self.assertEqual(args[1:3], [
            "--context", "desktop-linux"
        ])
        self.assertEqual(args[3:5], ["image", "inspect"])
        self.assertEqual(args[-1], self.reference)
        self.assertFalse(mocked.call_args.kwargs["check"])

    def test_rejects_unapproved_image_before_docker(self):
        with patch(
            "services.validator.docker_inspect.subprocess.run"
        ) as mocked:
            with self.assertRaises(ValueError):
                inspect_approved_image(
                    self.policy,
                    frozenset(),
                )

        mocked.assert_not_called()

    def test_rejects_insecure_policy(self):
        unsafe = replace(self.policy, privileged=True)

        with self.assertRaises(ValueError):
            inspect_approved_image(unsafe, self.approved)

    def test_rejects_unavailable_executable(self):
        with patch(
            "services.validator.docker_inspect."
            "resolve_docker_executable",
            return_value=None,
        ):
            with self.assertRaisesRegex(
                RuntimeError, "docker_unavailable"
            ):
                inspect_approved_image(
                    self.policy,
                    self.approved,
                )

    def test_rejects_failed_inspection(self):
        failure = subprocess.CompletedProcess(
            args=["docker"],
            returncode=1,
            stdout=b"",
            stderr=b"image not found",
        )

        with patch(
            "services.validator.docker_inspect."
            "resolve_docker_executable",
            return_value="docker-test.exe",
        ):
            with patch(
                "services.validator.docker_inspect.subprocess.run",
                return_value=failure,
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "docker_inspection_failed"
                ):
                    inspect_approved_image(
                        self.policy,
                        self.approved,
                    )

    def test_rejects_malformed_json(self):
        malformed = subprocess.CompletedProcess(
            args=["docker"],
            returncode=0,
            stdout=b"not-json",
            stderr=b"",
        )

        with patch(
            "services.validator.docker_inspect."
            "resolve_docker_executable",
            return_value="docker-test.exe",
        ):
            with patch(
                "services.validator.docker_inspect.subprocess.run",
                return_value=malformed,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "docker_inspection_invalid_json",
                ):
                    inspect_approved_image(
                        self.policy,
                        self.approved,
                    )


if __name__ == "__main__":
    unittest.main()
