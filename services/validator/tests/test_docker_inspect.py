
"""Tests for read-only Docker image inspection."""

import json
import subprocess
import unittest


import os

from services.validator.docker_inspect import (
    MAX_INSPECT_OUTPUT_BYTES,
)

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


    def test_reports_docker_inspection_timeout(self):
        with patch(
            "services.validator.docker_inspect."
            "resolve_docker_executable",
            return_value=r"C:\Docker\docker.exe",
        ):
            with patch(
                "services.validator.docker_inspect.subprocess.run",
                side_effect=subprocess.TimeoutExpired(
                    cmd=["docker", "image", "inspect"],
                    timeout=10,
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "docker_inspection_timeout",
                ):
                    inspect_approved_image(
                        self.policy,
                        self.approved,
                    )

    def test_rejects_oversized_inspection_output(self):
        oversized = subprocess.CompletedProcess(
            args=["docker"],
            returncode=0,
            stdout=b"x" * (MAX_INSPECT_OUTPUT_BYTES + 1),
            stderr=b"",
        )

        with patch(
            "services.validator.docker_inspect."
            "resolve_docker_executable",
            return_value=r"C:\Docker\docker.exe",
        ):
            with patch(
                "services.validator.docker_inspect.subprocess.run",
                return_value=oversized,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "docker_inspection_output_too_large",
                ):
                    inspect_approved_image(
                        self.policy,
                        self.approved,
                    )

    def test_removes_inherited_docker_overrides(self):
        inherited = {
            "DOCKER_HOST": "tcp://localhost:2375",
            "DOCKER_CONTEXT": "untrusted-context",
            "DOCKER_CONFIG": r"C:\untrusted-docker-config",
        }

        with patch.dict(os.environ, inherited):
            with patch(
                "services.validator.docker_inspect."
                "resolve_docker_executable",
                return_value=r"C:\Docker\docker.exe",
            ):
                with patch(
                    "services.validator.docker_inspect.subprocess.run",
                    return_value=self.successful_result(),
                ) as mocked:
                    inspect_approved_image(
                        self.policy,
                        self.approved,
                    )

        environment = mocked.call_args.kwargs["env"]

        self.assertNotIn("DOCKER_HOST", environment)
        self.assertNotIn("DOCKER_CONTEXT", environment)
        self.assertNotIn("DOCKER_CONFIG", environment)

        command = mocked.call_args.args[0]
        self.assertEqual(
            command[1:3],
            ["--context", "desktop-linux"],
        )

    def test_rejects_wrong_image_architecture(self):
        wrong_metadata = dict(self.metadata)
        wrong_metadata["Architecture"] = "arm64"

        result = subprocess.CompletedProcess(
            args=["docker"],
            returncode=0,
            stdout=json.dumps(wrong_metadata).encode("utf-8"),
            stderr=b"",
        )

        with patch(
            "services.validator.docker_inspect."
            "resolve_docker_executable",
            return_value=r"C:\Docker\docker.exe",
        ):
            with patch(
                "services.validator.docker_inspect.subprocess.run",
                return_value=result,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "Docker image must target amd64",
                ):
                    inspect_approved_image(
                        self.policy,
                        self.approved,
                    )

    def test_accepts_matching_expected_image_id(self):
        expected_id = self.metadata["Id"]

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
                    expected_image_id=expected_id,
                )

        self.assertEqual(identity.image_id, expected_id)

        command = mocked.call_args.args[0]
        self.assertEqual(command[-1], expected_id)
        self.assertEqual(command[3:5], ["image", "inspect"])

    def test_rejects_invalid_expected_image_id(self):
        invalid_ids = [
            "invalid",
            "sha256:1234",
            "b" * 64,
            "sha256:" + "G" * 64,
            "",
        ]

        with patch(
            "services.validator.docker_inspect.subprocess.run"
        ) as mocked:
            for invalid_id in invalid_ids:
                with self.subTest(image_id=invalid_id):
                    with self.assertRaisesRegex(
                        ValueError,
                        "Invalid expected image ID",
                    ):
                        inspect_approved_image(
                            self.policy,
                            self.approved,
                            expected_image_id=invalid_id,
                        )

        mocked.assert_not_called()

    def test_rejects_mismatched_expected_image_id(self):
        expected_id = "sha256:" + "c" * 64

        with patch(
            "services.validator.docker_inspect."
            "resolve_docker_executable",
            return_value=r"C:\Docker\docker.exe",
        ):
            with patch(
                "services.validator.docker_inspect.subprocess.run",
                return_value=self.successful_result(),
            ) as mocked:
                with self.assertRaisesRegex(
                    ValueError,
                    "Docker image ID mismatch",
                ):
                    inspect_approved_image(
                        self.policy,
                        self.approved,
                        expected_image_id=expected_id,
                    )

        command = mocked.call_args.args[0]
        self.assertEqual(command[-1], expected_id)



if __name__ == "__main__":
    unittest.main()
