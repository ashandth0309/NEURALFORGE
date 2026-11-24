
"""Tests for fail-closed execution eligibility."""

import unittest
from dataclasses import replace

from services.validator.execution_gate import (
    RuntimeSecurityEvidence,
    validate_execution_eligibility,
)
from services.validator.image_identity import ImageIdentity
from services.validator.isolation import IsolationPolicy


class ExecutionGateTests(unittest.TestCase):

    def setUp(self):
        self.reference = "node@sha256:" + "a" * 64
        self.policy = IsolationPolicy(image=self.reference)
        self.approved = frozenset({self.reference})

        self.identity = ImageIdentity(
            reference=self.reference,
            image_id="sha256:" + "b" * 64,
            os="linux",
            architecture="amd64",
        )

    def check(self, runtime=None, identity=None):
        validate_execution_eligibility(
            policy=self.policy,
            approved_images=self.approved,
            image_identity=(
                self.identity if identity is None else identity
            ),
            runtime=(
                RuntimeSecurityEvidence()
                if runtime is None else runtime
            ),
        )

    def test_defaults_fail_closed(self):
        with self.assertRaisesRegex(
            ValueError, "runtime_control_unverified"
        ):
            self.check()

    def test_rejects_missing_seccomp(self):
        evidence = RuntimeSecurityEvidence(
            network_disabled=True,
            read_only_root=True,
            capabilities_dropped=True,
            resource_limits_enforced=True,
            no_new_privileges=True,
        )

        with self.assertRaisesRegex(
            ValueError,
            "runtime_control_unverified:seccomp_enforced",
        ):
            self.check(runtime=evidence)

    def test_rejects_wrong_image_reference(self):
        wrong = replace(
            self.identity,
            reference="node@sha256:" + "c" * 64,
        )

        with self.assertRaisesRegex(
            ValueError, "image_identity_mismatch"
        ):
            self.check(identity=wrong)

    def test_rejects_wrong_architecture(self):
        wrong = replace(
            self.identity,
            architecture="arm64",
        )

        with self.assertRaisesRegex(
            ValueError, "unsupported_image_architecture"
        ):
            self.check(identity=wrong)

    def test_rejects_missing_runtime_evidence(self):
        with self.assertRaisesRegex(
            ValueError, "runtime_evidence_missing"
        ):
            self.check(runtime="unverified")


    def test_accepts_complete_declared_evidence(self):
        evidence = RuntimeSecurityEvidence(
            seccomp_enforced=True,
            network_disabled=True,
            read_only_root=True,
            capabilities_dropped=True,
            resource_limits_enforced=True,
            no_new_privileges=True,
        )

        self.assertIsNone(self.check(runtime=evidence))

    def test_rejects_each_missing_runtime_control(self):
        controls = (
            "seccomp_enforced",
            "network_disabled",
            "read_only_root",
            "capabilities_dropped",
            "resource_limits_enforced",
            "no_new_privileges",
        )

        complete = RuntimeSecurityEvidence(
            **{control: True for control in controls}
        )

        for control in controls:
            with self.subTest(control=control):
                incomplete = replace(
                    complete,
                    **{control: False},
                )

                with self.assertRaisesRegex(
                    ValueError,
                    f"runtime_control_unverified:{control}",
                ):
                    self.check(runtime=incomplete)



if __name__ == "__main__":
    unittest.main()
