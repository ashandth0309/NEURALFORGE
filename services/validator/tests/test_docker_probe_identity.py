
"""Tests for Docker probe container identity verification."""

import copy
import unittest

from services.validator.docker_probe_commands import PROBE_SCRIPT
from services.validator.docker_probe_identity import (
    verify_probe_container,
)
from services.validator.isolation import IsolationPolicy


class DockerProbeIdentityTests(unittest.TestCase):

    def setUp(self):
        self.policy = IsolationPolicy(
            image="node@sha256:" + "a" * 64
        )
        self.image_id = "sha256:" + "b" * 64
        self.container_id = "c" * 64
        self.name = "neuralforge-probe-" + "d" * 24

        self.metadata = {
            "Id": self.container_id,
            "Image": self.image_id,
            "Name": "/" + self.name,
            "State": {
                "Status": "created",
                "Running": False,
            },
            "Config": {
                "User": "10001:10001",
                "Entrypoint": ["/usr/local/bin/node"],
                "Cmd": ["-e", PROBE_SCRIPT],
            },
            "HostConfig": {
                "NetworkMode": "none",
                "ReadonlyRootfs": True,
                "Privileged": False,
                "Memory": 536870912,
                "MemorySwap": 536870912,
                "NanoCpus": 1000000000,
                "PidsLimit": 64,
                "CgroupnsMode": "private",
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

    def verify(self, metadata):
        return verify_probe_container(
            metadata,
            policy=self.policy,
            expected_image_id=self.image_id,
            expected_name=self.name,
            expected_container_id=self.container_id,
        )

    def test_accepts_expected_configuration(self):
        self.assertEqual(
            self.verify(self.metadata),
            self.container_id,
        )

    def test_rejects_wrong_container_id(self):
        data = copy.deepcopy(self.metadata)
        data["Id"] = "e" * 64

        with self.assertRaisesRegex(
            ValueError, "container_id_mismatch"
        ):
            self.verify(data)

    def test_rejects_wrong_image(self):
        data = copy.deepcopy(self.metadata)
        data["Image"] = "sha256:" + "f" * 64

        with self.assertRaisesRegex(
            ValueError, "container_image_mismatch"
        ):
            self.verify(data)

    def test_rejects_running_container(self):
        data = copy.deepcopy(self.metadata)
        data["State"]["Status"] = "running"
        data["State"]["Running"] = True

        with self.assertRaisesRegex(
            ValueError, "container_not_stopped"
        ):
            self.verify(data)

    def test_rejects_wrong_user(self):
        data = copy.deepcopy(self.metadata)
        data["Config"]["User"] = "0:0"

        with self.assertRaisesRegex(
            ValueError, "container_user_mismatch"
        ):
            self.verify(data)

    def test_rejects_privileged_container(self):
        data = copy.deepcopy(self.metadata)
        data["HostConfig"]["Privileged"] = True

        with self.assertRaisesRegex(
            ValueError, "container_configuration_mismatch"
        ):
            self.verify(data)

    def test_rejects_network_access(self):
        data = copy.deepcopy(self.metadata)
        data["HostConfig"]["NetworkMode"] = "bridge"

        with self.assertRaisesRegex(
            ValueError, "container_configuration_mismatch"
        ):
            self.verify(data)

    def test_rejects_missing_seccomp(self):
        data = copy.deepcopy(self.metadata)
        data["HostConfig"]["SecurityOpt"] = [
            "no-new-privileges=true"
        ]

        with self.assertRaisesRegex(
            ValueError, "container_security_options_mismatch"
        ):
            self.verify(data)

    def test_rejects_host_mount(self):
        data = copy.deepcopy(self.metadata)
        data["Mounts"] = [
            {"Source": "/host", "Destination": "/data"}
        ]

        with self.assertRaisesRegex(
            ValueError, "unexpected_container_mounts"
        ):
            self.verify(data)

    def test_rejects_wrong_resource_limit(self):
        data = copy.deepcopy(self.metadata)
        data["HostConfig"]["Memory"] = 1073741824

        with self.assertRaisesRegex(
            ValueError, "container_configuration_mismatch"
        ):
            self.verify(data)

    def test_rejects_changed_diagnostic(self):
        data = copy.deepcopy(self.metadata)
        data["Config"]["Cmd"] = ["-e", "console.log('changed')"]

        with self.assertRaisesRegex(
            ValueError, "container_command_mismatch"
        ):
            self.verify(data)

    def test_rejects_host_cgroup_namespace(self):
        data = copy.deepcopy(self.metadata)
        data["HostConfig"]["CgroupnsMode"] = "host"

        with self.assertRaisesRegex(
            ValueError,
            "container_configuration_mismatch:CgroupnsMode",
        ):
            self.verify(data)



if __name__ == "__main__":
    unittest.main()
