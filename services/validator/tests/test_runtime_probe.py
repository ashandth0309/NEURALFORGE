
"""Tests for the fail-closed runtime probe parser."""

import copy
import json
import unittest

from services.validator.isolation import IsolationPolicy
from services.validator.runtime_probe import parse_runtime_probe


class RuntimeProbeTests(unittest.TestCase):

    def setUp(self):
        self.policy = IsolationPolicy(
            image="node@sha256:" + "a" * 64
        )

        self.valid = {
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

    def parse(self, data):
        output = json.dumps(data).encode("utf-8")
        return parse_runtime_probe(output, self.policy)

    def test_accepts_valid_observations(self):
        evidence = self.parse(self.valid)

        self.assertTrue(evidence.seccomp_enforced)
        self.assertTrue(evidence.network_disabled)
        self.assertTrue(evidence.read_only_root)
        self.assertTrue(evidence.capabilities_dropped)
        self.assertTrue(evidence.resource_limits_enforced)
        self.assertTrue(evidence.no_new_privileges)

    def test_rejects_wrong_uid(self):
        data = copy.deepcopy(self.valid)
        data["uid"] = 0

        with self.assertRaisesRegex(
            ValueError, "runtime_user_mismatch"
        ):
            self.parse(data)

    def test_rejects_wrong_gid(self):
        data = copy.deepcopy(self.valid)
        data["gid"] = 0

        with self.assertRaisesRegex(
            ValueError, "runtime_user_mismatch"
        ):
            self.parse(data)

    def test_rejects_missing_seccomp(self):
        data = copy.deepcopy(self.valid)
        data["status"]["Seccomp"] = "0"

        with self.assertRaisesRegex(
            ValueError, "runtime_probe_verification_failed"
        ):
            self.parse(data)

    def test_rejects_missing_seccomp_filters(self):
        data = copy.deepcopy(self.valid)
        data["status"]["Seccomp_filters"] = "0"

        with self.assertRaises(ValueError):
            self.parse(data)

    def test_rejects_nonzero_capabilities(self):
        data = copy.deepcopy(self.valid)
        data["status"]["CapEff"] = "0000000000000001"

        with self.assertRaises(ValueError):
            self.parse(data)

    def test_rejects_privilege_escalation(self):
        data = copy.deepcopy(self.valid)
        data["status"]["NoNewPrivs"] = "0"

        with self.assertRaises(ValueError):
            self.parse(data)

    def test_rejects_external_network_interface(self):
        data = copy.deepcopy(self.valid)
        data["interfaces"] = ["lo", "eth0"]

        with self.assertRaises(ValueError):
            self.parse(data)

    def test_rejects_writable_filesystem(self):
        data = copy.deepcopy(self.valid)
        data["filesystem_write_error"] = None

        with self.assertRaises(ValueError):
            self.parse(data)

    def test_rejects_incorrect_memory_limit(self):
        data = copy.deepcopy(self.valid)
        data["memory"] = "1073741824"

        with self.assertRaises(ValueError):
            self.parse(data)

    def test_rejects_incorrect_cpu_quota(self):
        data = copy.deepcopy(self.valid)
        data["cpuQuota"] = "200000"

        with self.assertRaises(ValueError):
            self.parse(data)

    def test_rejects_incorrect_pid_limit(self):
        data = copy.deepcopy(self.valid)
        data["pids"] = "128"

        with self.assertRaises(ValueError):
            self.parse(data)

    def test_rejects_missing_status(self):
        data = copy.deepcopy(self.valid)
        del data["status"]

        with self.assertRaisesRegex(
            ValueError, "runtime_status_missing"
        ):
            self.parse(data)

    def test_rejects_invalid_json(self):
        with self.assertRaisesRegex(
            ValueError, "invalid_runtime_probe_json"
        ):
            parse_runtime_probe(
                b"{not valid json",
                self.policy,
            )

    def test_rejects_excessive_output(self):
        with self.assertRaisesRegex(
            ValueError, "invalid_runtime_probe_output"
        ):
            parse_runtime_probe(
                b"x" * 8193,
                self.policy,
            )

    def test_rejects_nonobject_json(self):
        with self.assertRaisesRegex(
            ValueError, "invalid_runtime_probe_structure"
        ):
            parse_runtime_probe(
                b"[]",
                self.policy,
            )


    def test_rejects_noncanonical_resource_strings(self):
        invalid_values = (
            " 536870912 ",
            "+536870912",
            "0536870912",
            "536870912.0",
            "536870912\n",
            "-536870912",
        )

        for value in invalid_values:
            with self.subTest(value=repr(value)):
                data = copy.deepcopy(self.valid)
                data["memory"] = value

                with self.assertRaisesRegex(
                    ValueError,
                    "runtime_probe_verification_failed",
                ):
                    self.parse(data)

    def test_rejects_nonstring_resource_values(self):
        invalid_values = (
            536870912,
            536870912.0,
            True,
            None,
        )

        for value in invalid_values:
            with self.subTest(value=repr(value)):
                data = copy.deepcopy(self.valid)
                data["memory"] = value

                with self.assertRaisesRegex(
                    ValueError,
                    "runtime_probe_verification_failed",
                ):
                    self.parse(data)

    def test_rejects_malformed_resource_fields(self):
        for field in (
            "memory",
            "cpuQuota",
            "cpuPeriod",
            "pids",
        ):
            with self.subTest(field=field):
                data = copy.deepcopy(self.valid)
                data[field] = "invalid"

                with self.assertRaisesRegex(
                    ValueError,
                    "runtime_probe_verification_failed",
                ):
                    self.parse(data)

if __name__ == "__main__":
    unittest.main()
