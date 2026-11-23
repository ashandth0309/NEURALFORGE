
"""Tests for Docker image metadata verification."""

import unittest
from copy import deepcopy
from dataclasses import replace

from services.validator.image_identity import (
    ImageIdentity,
    verify_image_identity,
)
from services.validator.isolation import IsolationPolicy


class ImageIdentityTests(unittest.TestCase):

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

    def verify(self, metadata=None, policy=None, approved=None):
        return verify_image_identity(
            policy=self.policy if policy is None else policy,
            approved_images=(
                self.approved if approved is None else approved
            ),
            metadata=(
                self.metadata if metadata is None else metadata
            ),
        )

    def test_accepts_matching_image_metadata(self):
        result = self.verify()

        self.assertIsInstance(result, ImageIdentity)
        self.assertEqual(result.reference, self.reference)
        self.assertEqual(result.image_id, self.metadata["Id"])
        self.assertEqual(result.os, "linux")
        self.assertEqual(result.architecture, "amd64")

    def test_rejects_missing_approved_digest(self):
        metadata = deepcopy(self.metadata)
        metadata["RepoDigests"] = [
            "node@sha256:" + "c" * 64
        ]

        with self.assertRaises(ValueError):
            self.verify(metadata=metadata)

    def test_rejects_invalid_image_id(self):
        metadata = deepcopy(self.metadata)
        metadata["Id"] = "invalid"

        with self.assertRaises(ValueError):
            self.verify(metadata=metadata)

    def test_rejects_windows_image(self):
        metadata = deepcopy(self.metadata)
        metadata["Os"] = "windows"

        with self.assertRaises(ValueError):
            self.verify(metadata=metadata)

    def test_rejects_wrong_architecture(self):
        metadata = deepcopy(self.metadata)
        metadata["Architecture"] = "arm64"

        with self.assertRaises(ValueError):
            self.verify(metadata=metadata)

    def test_rejects_unapproved_image(self):
        with self.assertRaises(ValueError):
            self.verify(approved=frozenset({"other"}))

    def test_rejects_insecure_policy(self):
        unsafe = replace(self.policy, privileged=True)

        with self.assertRaises(ValueError):
            self.verify(policy=unsafe)

    def test_rejects_invalid_metadata_type(self):
        with self.assertRaises(TypeError):
            self.verify(metadata="not metadata")


if __name__ == "__main__":
    unittest.main()
