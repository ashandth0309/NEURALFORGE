
"""Tests for fixed Docker runtime probe commands."""

import unittest

from services.validator.docker_probe_commands import (
    PROBE_SCRIPT,
    build_probe_commands,
)
from services.validator.isolation import IsolationPolicy


class DockerProbeCommandTests(unittest.TestCase):

    def setUp(self):
        self.policy = IsolationPolicy(
            image="node@sha256:" + "a" * 64
        )
        self.image_id = "sha256:" + "b" * 64
        self.name = "neuralforge-probe-" + "c" * 24
        self.executable = r"C:\Docker\docker.exe"

    def build(self, **overrides):
        args = dict(
            policy=self.policy,
            image_id=self.image_id,
            executable=self.executable,
            container_name=self.name,
        )
        args.update(overrides)
        return build_probe_commands(**args)

    def test_produces_four_fixed_commands(self):
        create, inspect, start, cleanup = self.build()

        self.assertEqual(create[3], "create")
        self.assertEqual(inspect[3], "inspect")
        self.assertEqual(start[3], "start")
        self.assertEqual(cleanup[3], "rm")

        self.assertEqual(
            create[-3:],
            (
                self.image_id,
                "-e",
                PROBE_SCRIPT,
            ),
        )

    def test_preserves_security_restrictions(self):
        create, _, _, _ = self.build()

        for option in (
            "--network",
            "--read-only",
            "--cap-drop",
            "--security-opt",
            "--memory",
            "--memory-swap",
            "--cpus",
            "--pids-limit",
            "--user",
            "--init",
        ):
            self.assertIn(option, create)

        self.assertEqual(
            create[create.index("--user") + 1],
            "10001:10001",
        )

        self.assertEqual(
            create[create.index("--network") + 1],
            "none",
        )

        self.assertEqual(
            create[create.index("--cap-drop") + 1],
            "ALL",
        )

        self.assertEqual(
            create[create.index("--memory") + 1],
            "512m",
        )

        self.assertEqual(
            create[create.index("--memory-swap") + 1],
            "512m",
        )

        self.assertEqual(
            create[create.index("--cpus") + 1],
            "1",
        )

        self.assertEqual(
            create[create.index("--pids-limit") + 1],
            "64",
        )

        self.assertIn("seccomp=builtin", create)
        self.assertIn("no-new-privileges=true", create)

    def test_start_and_cleanup_target_same_name(self):
        _, _, start, cleanup = self.build()

        self.assertEqual(start[-1], self.name)
        self.assertEqual(cleanup[-1], self.name)
        self.assertIn("--force", cleanup)

    def test_inspect_targets_same_container(self):
        create, inspect, start, cleanup = self.build()

        self.assertEqual(inspect[3], "inspect")
        self.assertEqual(inspect[-1], self.name)
        self.assertIn("{{json .}}", inspect)

        self.assertEqual(
            create[create.index("--name") + 1],
            self.name,
        )

        self.assertEqual(start[-1], self.name)
        self.assertEqual(cleanup[-1], self.name)

    def test_rejects_invalid_image_id(self):
        with self.assertRaises(ValueError):
            self.build(image_id="node:latest")

    def test_rejects_invalid_container_name(self):
        with self.assertRaises(ValueError):
            self.build(container_name="other-container")

    def test_rejects_relative_executable(self):
        with self.assertRaises(ValueError):
            self.build(executable="docker.exe")

    def test_probe_has_no_repository_mounts(self):
        create, _, _, _ = self.build()

        self.assertNotIn("--volume", create)
        self.assertNotIn("--mount", create)
        self.assertNotIn("-v", create)
        self.assertNotIn("--privileged", create)

    def test_uses_explicit_docker_context(self):
        create, inspect, start, cleanup = self.build()

        for command in (
            create,
            inspect,
            start,
            cleanup,
        ):
            self.assertEqual(
                command[:3],
                (
                    self.executable,
                    "--context",
                    "desktop-linux",
                ),
            )


if __name__ == "__main__":
    unittest.main()
