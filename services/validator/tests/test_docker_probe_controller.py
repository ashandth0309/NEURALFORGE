
"""Mocked tests for the fixed Docker probe controller."""

import copy
import json
import subprocess
import unittest
from unittest.mock import patch

from services.validator.docker_probe_commands import PROBE_SCRIPT
from services.validator.docker_probe_controller import (
    run_fixed_docker_probe,
)
from services.validator.image_identity import ImageIdentity
from services.validator.isolation import IsolationPolicy


class DockerProbeControllerTests(unittest.TestCase):

    def setUp(self):
        self.reference = "node@sha256:" + "a" * 64
        self.image_id = "sha256:" + "b" * 64
        self.container_id = "c" * 64
        self.name = "neuralforge-probe-" + "d" * 24

        self.policy = IsolationPolicy(image=self.reference)
        self.approved = frozenset({self.reference})

        self.identity = ImageIdentity(
            reference=self.reference,
            image_id=self.image_id,
            os="linux",
            architecture="amd64",
        )

        self.metadata = {
            "Id": self.container_id,
            "Image": self.image_id,
            "Name": "/" + self.name,
            "State": {
                "Status": "created",
                "Running": False,
            },
            "Config": {
                "Labels": {
                    "com.neuralforge.probe.name": self.name,
                },
                "User": "10001:10001",
                "Entrypoint": ["/usr/local/bin/node"],
                "Cmd": ["-e", PROBE_SCRIPT],
            },
            "HostConfig": {
                "NetworkMode": "none",
                "CgroupnsMode": "private",
                "ReadonlyRootfs": True,
                "Privileged": False,
                "Memory": 536870912,
                "MemorySwap": 536870912,
                "NanoCpus": 1000000000,
                "PidsLimit": 64,
                "Init": True,
                "CapDrop": ["ALL"],
                "SecurityOpt": [
                    "no-new-privileges=true",
                    "seccomp=builtin",
                ],
                "Binds": None,
                "Mounts": [],
                "Devices": [],
            },
            "Mounts": [],
        }

        self.observations = {
            "uid": 10001,
            "gid": 10001,
            "status": {
                "Seccomp": "2",
                "Seccomp_filters": "2",
                "CapEff": "0000000000000000",
                "CapBnd": "0000000000000000",
                "NoNewPrivs": "1",
            },
            "interfaces": ["lo"],
            "filesystem_write_error": "EROFS",
            "memory": "536870912",
            "cpuQuota": "100000",
            "cpuPeriod": "100000",
            "pids": "64",
        }

    @staticmethod
    def result(output=b"", returncode=0):
        return subprocess.CompletedProcess(
            args=[],
            returncode=returncode,
            stdout=output,
            stderr=b"",
        )

    def responses(self):
        finished = copy.deepcopy(self.metadata)
        finished["State"] = {
            "Status": "exited",
            "Running": False,
            "ExitCode": 0,
        }

        return [
            self.result(self.container_id.encode() + b"\n"),
            self.result(json.dumps(self.metadata).encode()),
            self.result(json.dumps(self.observations).encode()),
            self.result(json.dumps(finished).encode()),
            self.result(),
            self.result(),
        ]


    def invoke_probe(self, responses):
        self.cli_calls = []

        with patch(
            "services.validator.docker_probe_controller."
            "inspect_approved_image",
            return_value=self.identity,
        ), patch(
            "services.validator.docker_probe_controller."
            "resolve_docker_executable",
            return_value=r"C:\Docker\docker.exe",
        ), patch(
            "services.validator.docker_probe_controller."
            "secrets.token_hex",
            return_value="d" * 24,
        ), patch(
            "services.validator.docker_probe_controller."
            "run_bounded",
            side_effect=responses,
        ) as invoke:
            try:
                evidence = run_fixed_docker_probe(
                    self.policy,
                    self.approved,
                    self.image_id,
                )
                return evidence, invoke.call_args_list
            finally:
                self.cli_calls = list(invoke.call_args_list)

    def test_successful_probe(self):
        evidence, calls = self.invoke_probe(self.responses())

        self.assertTrue(evidence.seccomp_enforced)
        self.assertTrue(evidence.resource_limits_enforced)
        self.assertEqual(len(calls), 6)

        self.assertEqual(
            calls[2].args[0][-1],
            self.container_id,
        )

        self.assertEqual(
            calls[4].args[0][-1],
            self.container_id,
        )

    def test_rejects_invalid_created_container_id(self):
        responses = [
            self.result(b"invalid-id\n"),
            self.result(),
            self.result(),
        ]

        with self.assertRaisesRegex(
            RuntimeError,
            "docker_probe_cleanup_unconfirmed",
        ):
            self.invoke_probe(responses)

    def test_rejects_wrong_inspected_image(self):
        wrong = copy.deepcopy(self.metadata)
        wrong["Image"] = "sha256:" + "e" * 64

        responses = [
            self.result(self.container_id.encode()),
            self.result(json.dumps(wrong).encode()),
            self.result(),
            self.result(),
        ]

        with self.assertRaisesRegex(
            ValueError,
            "container_image_mismatch",
        ):
            self.invoke_probe(responses)

    def test_rejects_nonzero_container_exit(self):
        responses = self.responses()
        finished = copy.deepcopy(self.metadata)
        finished["State"] = {
            "Status": "exited",
            "Running": False,
            "ExitCode": 1,
        }
        responses[3] = self.result(
            json.dumps(finished).encode()
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "docker_probe_exit_failed",
        ):
            self.invoke_probe(responses)

    def test_rejects_failed_cleanup(self):
        responses = self.responses()
        responses[4] = self.result(
            returncode=1
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "docker_probe_cleanup_unconfirmed",
        ):
            self.invoke_probe(responses)

    def test_rejects_container_still_listed(self):
        responses = self.responses()
        responses[5] = self.result(
            self.container_id.encode()
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "docker_probe_cleanup_unconfirmed",
        ):
            self.invoke_probe(responses)

    def test_rejects_failed_container_start(self):
        responses = self.responses()
        responses[2] = self.result(returncode=1)

        # After start failure, the controller must
        # still attempt removal and absence checking.
        responses = [
            responses[0],
            responses[1],
            responses[2],
            self.result(),
            self.result(),
        ]

        with self.assertRaisesRegex(
            RuntimeError,
            "docker_probe_start_failed",
        ):
            self.invoke_probe(responses)

    def test_rejects_invalid_probe_output(self):
        responses = self.responses()
        responses[2] = self.result(
            b'{"invalid":"observations"}'
        )

        with self.assertRaisesRegex(
            ValueError,
            "runtime_status_missing",
        ):
            self.invoke_probe(responses)


    def test_reports_uncertain_cleanup_after_create_timeout(self):
        from services.validator.bounded_capture import (
            BoundedProcessTimeout,
        )

        responses = [
            BoundedProcessTimeout("subprocess_timeout"),
            self.result(),
            self.result(),
        ]

        with self.assertRaisesRegex(
            RuntimeError,
            "docker_probe_cleanup_unconfirmed",
        ):
            self.invoke_probe(responses)



    def test_rejects_failed_container_creation(self):
        responses = [
            self.result(returncode=1),
        ]

        with self.assertRaisesRegex(
            RuntimeError,
            "docker_probe_cleanup_unconfirmed",
        ):
            self.invoke_probe(responses)


    def test_attempts_cleanup_after_start_timeout(self):
        from services.validator.bounded_capture import (
            BoundedProcessTimeout,
        )

        responses = [
            self.result(self.container_id.encode()),
            self.result(json.dumps(self.metadata).encode()),
            BoundedProcessTimeout("subprocess_timeout"),
            self.result(),
            self.result(),
        ]

        with self.assertRaises(BoundedProcessTimeout):
            self.invoke_probe(responses)

    def test_rejects_container_still_running(self):
        responses = self.responses()

        running = copy.deepcopy(self.metadata)
        running["State"] = {
            "Status": "running",
            "Running": True,
            "ExitCode": 0,
        }

        responses[3] = self.result(
            json.dumps(running).encode()
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "docker_probe_exit_failed",
        ):
            self.invoke_probe(responses)

    def test_rejects_cleanup_cli_exception(self):
        responses = self.responses()
        responses[4] = OSError("Docker CLI unavailable")

        with self.assertRaisesRegex(
            RuntimeError,
            "docker_probe_cleanup_unconfirmed",
        ):
            self.invoke_probe(responses)

    def test_reports_uncertain_cleanup_after_create_error(self):
        responses = [
            OSError("Docker connection interrupted"),
            self.result(),
            self.result(),
        ]

        with self.assertRaisesRegex(
            RuntimeError,
            "docker_probe_cleanup_unconfirmed",
        ):
            self.invoke_probe(responses)


    def test_rejects_unverified_container_ownership(self):
        wrong = copy.deepcopy(self.metadata)
        wrong["Name"] = "/unrelated-container"

        responses = [
            self.result(self.container_id.encode()),
            self.result(json.dumps(wrong).encode()),
        ]

        with self.assertRaisesRegex(
            RuntimeError,
            "docker_probe_cleanup_unconfirmed",
        ):
            self.invoke_probe(responses)

    def test_never_removes_unverified_container(self):
        wrong = copy.deepcopy(self.metadata)
        wrong["Name"] = "/unrelated-container"

        responses = [
            self.result(self.container_id.encode()),
            self.result(json.dumps(wrong).encode()),
        ]

        with self.assertRaisesRegex(
            RuntimeError,
            "docker_probe_cleanup_unconfirmed",
        ):
            self.invoke_probe(responses)

        commands = [
            call.args[0]
            for call in self.cli_calls
        ]

        self.assertEqual(len(commands), 2)

        self.assertTrue(
            any("create" in command for command in commands)
        )

        self.assertTrue(
            any("inspect" in command for command in commands)
        )

        self.assertFalse(
            any("rm" in command for command in commands)
        )

        self.assertFalse(
            any("start" in command for command in commands)
        )

    def test_never_starts_or_removes_wrong_label(self):
        wrong = copy.deepcopy(self.metadata)

        wrong["Config"]["Labels"] = {
            "com.neuralforge.probe.name":
                "neuralforge-probe-" + "e" * 24,
        }

        responses = [
            self.result(self.container_id.encode()),
            self.result(json.dumps(wrong).encode()),
        ]

        with self.assertRaisesRegex(
            RuntimeError,
            "docker_probe_cleanup_unconfirmed",
        ):
            self.invoke_probe(responses)

        commands = [
            call.args[0]
            for call in self.cli_calls
        ]

        self.assertEqual(len(commands), 2)

        self.assertFalse(
            any("start" in command for command in commands)
        )

        self.assertFalse(
            any("rm" in command for command in commands)
        )

    def test_journal_failure_prevents_docker_creation(self):
        from unittest.mock import Mock

        journal = Mock()
        journal.prepare.side_effect = OSError(
            "SQLite write failed"
        )

        with patch(
            "services.validator.docker_probe_controller."
            "inspect_approved_image",
            return_value=self.identity,
        ), patch(
            "services.validator.docker_probe_controller."
            "resolve_docker_executable",
            return_value=r"C:\Docker\docker.exe",
        ), patch(
            "services.validator.docker_probe_controller."
            "secrets.token_hex",
            return_value="d" * 24,
        ), patch(
            "services.validator.docker_probe_controller."
            "run_bounded",
        ) as docker:
            with self.assertRaises(OSError):
                run_fixed_docker_probe(
                    self.policy,
                    self.approved,
                    self.image_id,
                    journal=journal,
                )

        docker.assert_not_called()


    def test_journal_transition_failure_prevents_creation(self):
        from unittest.mock import Mock

        journal = Mock()
        journal.advance.side_effect = OSError(
            "SQLite transaction failed"
        )

        with patch(
            "services.validator.docker_probe_controller."
            "inspect_approved_image",
            return_value=self.identity,
        ), patch(
            "services.validator.docker_probe_controller."
            "resolve_docker_executable",
            return_value=r"C:\Docker\docker.exe",
        ), patch(
            "services.validator.docker_probe_controller."
            "secrets.token_hex",
            return_value="d" * 24,
        ), patch(
            "services.validator.docker_probe_controller."
            "run_bounded",
        ) as docker:
            with self.assertRaisesRegex(
                OSError,
                "SQLite transaction failed",
            ):
                run_fixed_docker_probe(
                    self.policy,
                    self.approved,
                    self.image_id,
                    journal=journal,
                )

        journal.prepare.assert_called_once_with(
            self.name,
            self.image_id,
        )

        journal.advance.assert_called_once_with(
            self.name,
            "prepared",
            "create_requested",
        )

        docker.assert_not_called()

    def test_successful_probe_persists_removed_state(self):
        import tempfile
        from pathlib import Path

        from services.validator.docker_probe_journal import (
            ProbeJournal,
        )

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "probes.sqlite3"
            journal = ProbeJournal(database)
            journal.initialize()

            with patch(
                "services.validator.docker_probe_controller."
                "inspect_approved_image",
                return_value=self.identity,
            ), patch(
                "services.validator.docker_probe_controller."
                "resolve_docker_executable",
                return_value=r"C:\Docker\docker.exe",
            ), patch(
                "services.validator.docker_probe_controller."
                "secrets.token_hex",
                return_value="d" * 24,
            ), patch(
                "services.validator.docker_probe_controller."
                "run_bounded",
                side_effect=self.responses(),
            ) as docker:
                evidence = run_fixed_docker_probe(
                    self.policy,
                    self.approved,
                    self.image_id,
                    journal=journal,
                )

            self.assertTrue(evidence.seccomp_enforced)
            self.assertTrue(evidence.resource_limits_enforced)
            self.assertEqual(docker.call_count, 6)

            # Reopen the database to verify persistence.
            reopened = ProbeJournal(database)
            record = reopened.get(self.name)

            self.assertIsNotNone(record)
            self.assertEqual(record.phase, "removed")
            self.assertEqual(
                record.container_id,
                self.container_id,
            )
            self.assertEqual(reopened.unresolved(), [])

    def test_ownership_failure_persists_unresolved_state(self):
        import tempfile
        from pathlib import Path

        from services.validator.docker_probe_journal import (
            ProbeJournal,
        )

        wrong = copy.deepcopy(self.metadata)

        wrong["Config"]["Labels"] = {
            "com.neuralforge.probe.name": "unrelated",
        }

        responses = [
            self.result(self.container_id.encode()),
            self.result(json.dumps(wrong).encode()),
        ]

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "probes.sqlite3"
            journal = ProbeJournal(database)
            journal.initialize()

            with patch(
                "services.validator.docker_probe_controller."
                "inspect_approved_image",
                return_value=self.identity,
            ), patch(
                "services.validator.docker_probe_controller."
                "resolve_docker_executable",
                return_value=r"C:\Docker\docker.exe",
            ), patch(
                "services.validator.docker_probe_controller."
                "secrets.token_hex",
                return_value="d" * 24,
            ), patch(
                "services.validator.docker_probe_controller."
                "run_bounded",
                side_effect=responses,
            ) as docker:
                with self.assertRaisesRegex(
                    RuntimeError,
                    "docker_probe_cleanup_unconfirmed",
                ):
                    run_fixed_docker_probe(
                        self.policy,
                        self.approved,
                        self.image_id,
                        journal=journal,
                    )

            # Unverified containers must never be
            # started or force-removed.
            commands = [
                call.args[0]
                for call in docker.call_args_list
            ]

            self.assertEqual(len(commands), 2)

            self.assertFalse(
                any("start" in command for command in commands)
            )

            self.assertFalse(
                any("rm" in command for command in commands)
            )

            # The unresolved record must survive reopening.
            reopened = ProbeJournal(database)
            record = reopened.get(self.name)

            self.assertIsNotNone(record)
            self.assertEqual(
                record.phase,
                "cleanup_unconfirmed",
            )
            self.assertEqual(
                record.container_id,
                self.container_id,
            )

            self.assertEqual(
                len(reopened.unresolved()),
                1,
            )

if __name__ == "__main__":
    unittest.main()
