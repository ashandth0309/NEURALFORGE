
import unittest
from dataclasses import FrozenInstanceError, replace

from services.validator.isolation import (
    IsolationPolicy,
    validate_isolation_policy,
)


class IsolationPolicyTests(unittest.TestCase):

    def setUp(self):
        # Test-only digest; not an actual approved image.
        self.policy = IsolationPolicy(
            image="node@sha256:" + "a" * 64
        )

    def check_rejected(self, **changes):
        altered = replace(self.policy, **changes)

        with self.assertRaises(ValueError):
            validate_isolation_policy(altered)

    def test_accepts_restricted_policy(self):
        result = validate_isolation_policy(self.policy)
        self.assertEqual(result, self.policy)

    def test_rejects_unpinned_image(self):
        self.check_rejected(image="node:22")

    def test_rejects_network_access(self):
        self.check_rejected(network_disabled=False)

    def test_rejects_writable_root(self):
        self.check_rejected(read_only_root=False)

    def test_rejects_privileged_execution(self):
        self.check_rejected(privileged=True)

    def test_rejects_root_user(self):
        self.check_rejected(user="0:0")

    def test_rejects_excessive_memory(self):
        self.check_rejected(memory_mb=2048)

    def test_rejects_excessive_cpu(self):
        self.check_rejected(cpu_count=4)

    def test_rejects_excessive_process_limit(self):
        self.check_rejected(pids_limit=1024)

    def test_rejects_excessive_timeout(self):
        self.check_rejected(timeout_seconds=300)

    def test_rejects_retained_capabilities(self):
        self.check_rejected(drop_all_capabilities=False)

    def test_rejects_privilege_escalation(self):
        self.check_rejected(no_new_privileges=False)

    def test_rejects_writable_host_mounts(self):
        self.check_rejected(writable_host_mounts=True)

    def test_policy_is_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            self.policy.privileged = True


if __name__ == "__main__":
    unittest.main()
