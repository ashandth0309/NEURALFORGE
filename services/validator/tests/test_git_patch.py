
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from services.patcher.proposal import propose_replacement
from services.validator.git_patch import verify_git_patch
from services.validator.policy import (
    ValidationPlan,
    create_validation_plan,
)


@unittest.skipUnless(
    shutil.which("git"),
    "Git is required for patch validation tests",
)
class GitPatchValidationTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.source = 'export const message = "hello";\n'
        self.original = self.source.encode("utf-8")

        self.old_text = '"hello"'
        self.new_text = '"hello world"'
        self.path = "src/example.ts"

        proposed_source = self.source.replace(
            self.old_text,
            self.new_text,
            1,
        )
        self.proposed = proposed_source.encode("utf-8")

        self.original_digest = hashlib.sha256(
            self.original
        ).hexdigest()

        self.proposed_digest = hashlib.sha256(
            self.proposed
        ).hexdigest()

        self.plan = create_validation_plan(
            repository_id="demo-repo",
            source_path=self.path,
            original_sha256=self.original_digest,
            proposed_sha256=self.proposed_digest,
            checks=("patch_integrity",),
        )

        self.proposal = propose_replacement(
            path=self.path,
            source=self.source,
            old_text=self.old_text,
            new_text=self.new_text,
            expected_sha256=self.original_digest,
        )

    def verify(self, **changes):
        arguments = {
            "plan": self.plan,
            "original_content": self.original,
            "old_text": self.old_text,
            "new_text": self.new_text,
            "proposal": self.proposal,
        }
        arguments.update(changes)
        return verify_git_patch(**arguments)

    def test_valid_patch_applies_to_temporary_copy(self):
        result = self.verify()

        self.assertTrue(result.passed, result.reason)
        self.assertEqual(result.reason, "verified")
        self.assertEqual(
            result.actual_sha256,
            self.proposed_digest,
        )

    def test_original_content_remains_unchanged(self):
        original_copy = bytes(self.original)

        result = self.verify()

        self.assertTrue(result.passed)
        self.assertEqual(self.original, original_copy)

    def test_does_not_modify_external_source(self):
        external = Path(self.temp.name) / "original.ts"
        external.write_bytes(self.original)

        result = self.verify()

        self.assertTrue(result.passed)
        self.assertEqual(
            external.read_bytes(),
            self.original,
        )

    def test_rejects_tampered_diff(self):
        proposal = {
            **self.proposal,
            "unified_diff": "invalid patch",
        }

        result = self.verify(proposal=proposal)

        self.assertFalse(result.passed)
        self.assertEqual(
            result.reason,
            "proposal_mismatch",
        )

    def test_rejects_wrong_original_content(self):
        result = self.verify(
            original_content=b"unexpected source"
        )

        self.assertFalse(result.passed)

    def test_rejects_mismatched_proposed_digest(self):
        bad_plan = create_validation_plan(
            repository_id="demo-repo",
            source_path=self.path,
            original_sha256=self.original_digest,
            proposed_sha256="f" * 64,
            checks=("patch_integrity",),
        )

        result = self.verify(plan=bad_plan)

        self.assertFalse(result.passed)
        self.assertEqual(
            result.reason,
            "proposed_digest_mismatch",
        )

    def test_rejects_unsafe_manually_created_plan(self):
        unsafe_plan = ValidationPlan(
            repository_id="demo-repo",
            source_path="../outside.ts",
            original_sha256=self.original_digest,
            proposed_sha256=self.proposed_digest,
            checks=("patch_integrity",),
        )

        result = self.verify(plan=unsafe_plan)

        self.assertFalse(result.passed)
        self.assertEqual(result.reason, "invalid_plan")

    def test_supports_source_without_final_newline(self):
        source = 'export const message = "hello";'

        original = source.encode("utf-8")
        proposed = source.replace(
            '"hello"',
            '"hello world"',
        ).encode("utf-8")

        original_digest = hashlib.sha256(
            original
        ).hexdigest()

        plan = create_validation_plan(
            repository_id="demo-repo",
            source_path="src/example.ts",
            original_sha256=original_digest,
            proposed_sha256=hashlib.sha256(
                proposed
            ).hexdigest(),
            checks=("patch_integrity",),
        )

        proposal = propose_replacement(
            path="src/example.ts",
            source=source,
            old_text='"hello"',
            new_text='"hello world"',
            expected_sha256=original_digest,
        )

        result = self.verify(
            plan=plan,
            original_content=original,
            proposal=proposal,
        )

        self.assertTrue(result.passed, result.reason)


if __name__ == "__main__":
    unittest.main()
