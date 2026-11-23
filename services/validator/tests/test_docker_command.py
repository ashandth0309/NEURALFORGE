
"""Tests for deterministic Docker command construction."""

import unittest
from dataclasses import replace

from services.validator.docker_command import build_docker_command
from services.validator.isolation import IsolationPolicy


class DockerCommandTests(unittest.TestCase):

    def setUp(self):
        # Test-only digest, not an approved Docker image.
        self.policy = IsolationPolicy(
            image="node@sha256:" + "a" * 64
        )

    def test_generates_deterministic_command(self):
        first = build_docker_command(self.policy)
        second = build_docker_command(self.policy)

        self.assertEqual(first, second)
        self.assertIsInstance(first, tuple)
        self.assertEqual(first[:2], ("docker", "run"))

    def test_disables_network_and_privileges(self):
        command = build_docker_command(self.policy)

        self.assertIn("--network", command)
        self.assertEqual(
            command[command.index("--network") + 1],
            "none",
        )
        self.assertIn("--read-only", command)
        self.assertIn("--cap-drop", command)
        self.assertIn("ALL", command)
        self.assertIn(
            "no-new-privileges=true",
            command,
        )

    def test_enforces_resource_limits(self):
        command = build_docker_command(self.policy)

        for flag, expected in (
            ("--memory", "512m"),
            ("--memory-swap", "512m"),
            ("--cpus", "1"),
            ("--pids-limit", "64"),
        ):
            self.assertEqual(
                command[command.index(flag) + 1],
                expected,
            )

    def test_uses_fixed_entrypoint_and_no_mounts(self):
        command = build_docker_command(self.policy)

        self.assertNotIn("--mount", command)
        self.assertNotIn("--volume", command)
        self.assertNotIn("-v", command)

        self.assertEqual(
            command[command.index("--entrypoint") + 1],
            "/usr/local/bin/node",
        )
        self.assertEqual(command[-1], "--version")
        self.assertEqual(command[-2], self.policy.image)

    def test_disables_automatic_image_pull(self):
        command = build_docker_command(self.policy)

        self.assertEqual(
            command[command.index("--pull") + 1],
            "never",
        )
        self.assertIn("--rm", command)

    def test_rejects_insecure_policy(self):
        insecure = replace(
            self.policy,
            network_disabled=False,
        )

        with self.assertRaises(ValueError):
            build_docker_command(insecure)


if __name__ == "__main__":
    unittest.main()
