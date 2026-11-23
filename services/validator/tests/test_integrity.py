
import hashlib
import unittest
from dataclasses import FrozenInstanceError

from services.indexer.indexer import MAX_FILE_SIZE
from services.validator.integrity import verify_patch_integrity
from services.validator.policy import create_validation_plan


class PatchIntegrityTests(unittest.TestCase):

    def setUp(self):
        self.original = b'export const version = "1";\n'
        self.proposed = b'export const version = "2";\n'

    def digest(self, content):
        return hashlib.sha256(content).hexdigest()

    def make_plan(self, original=None, proposed=None):
        original = (
            self.original if original is None else original
        )
        proposed = (
            self.proposed if proposed is None else proposed
        )

        return create_validation_plan(
            repository_id="demo-repo",
            source_path="src/app/page.tsx",
            original_sha256=self.digest(original),
            proposed_sha256=self.digest(proposed),
            checks=("patch_integrity",),
        )

    def test_accepts_valid_content(self):
        plan = self.make_plan()

        result = verify_patch_integrity(
            plan,
            self.original,
            self.proposed,
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.reason, "verified")
        self.assertEqual(
            result.proposed_sha256,
            plan.proposed_sha256,
        )

    def test_rejects_wrong_original_digest(self):
        plan = self.make_plan()

        result = verify_patch_integrity(
            plan,
            b"modified original",
            self.proposed,
        )

        self.assertFalse(result.passed)
        self.assertEqual(
            result.reason,
            "original_digest_mismatch",
        )

    def test_rejects_wrong_proposed_digest(self):
        plan = self.make_plan()

        result = verify_patch_integrity(
            plan,
            self.original,
            b"unexpected proposal",
        )

        self.assertFalse(result.passed)
        self.assertEqual(
            result.reason,
            "proposed_digest_mismatch",
        )

    def test_rejects_oversized_original(self):
        plan = self.make_plan()

        result = verify_patch_integrity(
            plan,
            b"x" * (MAX_FILE_SIZE + 1),
            self.proposed,
        )

        self.assertFalse(result.passed)
        self.assertEqual(
            result.reason,
            "size_limit_exceeded",
        )

    def test_rejects_oversized_proposal(self):
        plan = self.make_plan()

        result = verify_patch_integrity(
            plan,
            self.original,
            b"x" * (MAX_FILE_SIZE + 1),
        )

        self.assertFalse(result.passed)
        self.assertEqual(
            result.reason,
            "size_limit_exceeded",
        )

    def test_rejects_invalid_utf8(self):
        invalid = b"\xff\xfe"
        plan = self.make_plan(proposed=invalid)

        result = verify_patch_integrity(
            plan,
            self.original,
            invalid,
        )

        self.assertFalse(result.passed)
        self.assertEqual(
            result.reason,
            "invalid_utf8",
        )

    def test_rejects_non_byte_content(self):
        plan = self.make_plan()

        with self.assertRaises(TypeError):
            verify_patch_integrity(
                plan,
                "not bytes",
                self.proposed,
            )

    def test_integrity_result_is_immutable(self):
        plan = self.make_plan()

        result = verify_patch_integrity(
            plan,
            self.original,
            self.proposed,
        )

        with self.assertRaises(FrozenInstanceError):
            result.passed = False


if __name__ == "__main__":
    unittest.main()
