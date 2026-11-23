
"""Tests for fail-closed Docker command preparation."""

import unittest
from dataclasses import replace
from unittest.mock import patch

from services.validator.docker_prepare import (
    prepare_docker_command,
)
from services.validator.isolation import IsolationPolicy


class DockerPrepareTests(unittest.TestCase):

    def setUp(self):
        self.image = "node@sha256:" + "a" * 64

        self.policy = IsolationPolicy(
            image=self.image
        )

        self.approved = frozenset({self.image})

        self.executable = (
            r"C:\Program Files\Docker\Docker"
            r"\resources\bin\docker.exe"
        )

    def test_prepares_approved_command(self):
        with patch(
            "services.validator.docker_prepare."
            "resolve_docker_executable",
            return_value=self.executable,
        ):
            command = prepare_docker_command(
                self.policy,
                self.approved,
            )

        self.assertEqual(
            command[0],
            self.executable,
        )
        self.assertEqual(command[1], "run")
        self.assertIn(self.image, command)

    def test_preserves_isolation_flags(self):
        with patch(
            "services.validator.docker_prepare."
            "resolve_docker_executable",
            return_value=self.executable,
        ):
            command = prepare_docker_command(
                self.policy,
                self.approved,
            )

        self.assertIn("--read-only", command)
        self.assertIn("--network", command)
        self.assertIn("none", command)
        self.assertIn("--cap-drop", command)
        self.assertIn("ALL", command)
        self.assertIn("seccomp=builtin", command)
        self.assertIn(
            "no-new-privileges=true",
            command,
        )

    def test_rejects_unapproved_image(self):
        with patch(
            "services.validator.docker_prepare."
            "resolve_docker_executable"
        ) as resolver:
            with self.assertRaises(ValueError):
                prepare_docker_command(
                    self.policy,
                    frozenset(),
                )

        resolver.assert_not_called()

    def test_rejects_insecure_policy(self):
        insecure = replace(
            self.policy,
            privileged=True,
        )

        with patch(
            "services.validator.docker_prepare."
            "resolve_docker_executable"
        ) as resolver:
            with self.assertRaises(ValueError):
                prepare_docker_command(
                    insecure,
                    self.approved,
                )

        resolver.assert_not_called()

    def test_rejects_missing_executable(self):
        with patch(
            "services.validator.docker_prepare."
            "resolve_docker_executable",
            return_value=None,
        ):
            with self.assertRaises(RuntimeError):
                prepare_docker_command(
                    self.policy,
                    self.approved,
                )

    def test_never_invokes_subprocess(self):
        with patch(
            "subprocess.run"
        ) as mocked:
            with patch(
                "services.validator.docker_prepare."
                "resolve_docker_executable",
                return_value=self.executable,
            ):
                prepare_docker_command(
                    self.policy,
                    self.approved,
                )

        mocked.assert_not_called()


if __name__ == "__main__":
    unittest.main()
