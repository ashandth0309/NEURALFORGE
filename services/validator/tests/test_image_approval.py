
"""Tests for fail-closed container image approval."""

import unittest
from dataclasses import replace

from services.validator.image_approval import (
    verify_approved_image,
)
from services.validator.isolation import IsolationPolicy


class ImageApprovalTests(unittest.TestCase):

    def setUp(self):
        # Test-only reference, not a trusted real image.
        self.approved_reference = (
            "node@sha256:" + "a" * 64
        )

        self.policy = IsolationPolicy(
            image=self.approved_reference
        )

        self.approved = frozenset(
            {self.approved_reference}
        )

    def test_accepts_exact_approved_reference(self):
        result = verify_approved_image(
            self.policy,
            self.approved,
        )

        self.assertEqual(result, self.policy)

    def test_rejects_unapproved_digest(self):
        altered = replace(
            self.policy,
            image="node@sha256:" + "b" * 64,
        )

        with self.assertRaises(ValueError):
            verify_approved_image(
                altered,
                self.approved,
            )

    def test_rejects_empty_approval_list(self):
        with self.assertRaises(ValueError):
            verify_approved_image(
                self.policy,
                frozenset(),
            )

    def test_rejects_unpinned_image(self):
        altered = replace(
            self.policy,
            image="node:alpine",
        )

        with self.assertRaises(ValueError):
            verify_approved_image(
                altered,
                self.approved,
            )

    def test_rejects_insecure_policy(self):
        altered = replace(
            self.policy,
            privileged=True,
        )

        with self.assertRaises(ValueError):
            verify_approved_image(
                altered,
                self.approved,
            )

    def test_rejects_mutable_approval_collection(self):
        with self.assertRaises(TypeError):
            verify_approved_image(
                self.policy,
                {self.approved_reference},
            )

    def test_rejects_invalid_approval_entries(self):
        invalid = frozenset(
            {self.approved_reference, None}
        )

        with self.assertRaises(ValueError):
            verify_approved_image(
                self.policy,
                invalid,
            )


if __name__ == "__main__":
    unittest.main()
