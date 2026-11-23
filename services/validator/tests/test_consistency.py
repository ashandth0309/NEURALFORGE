
import hashlib
import unittest

from services.patcher.proposal import propose_replacement
from services.validator.consistency import (
    verify_proposal_consistency,
)
from services.validator.policy import create_validation_plan


class ProposalConsistencyTests(unittest.TestCase):

    def setUp(self):
        self.source = 'export const message = "hello";\n'
        self.old_text = '"hello"'
        self.new_text = '"hello world"'
        self.path = "src/example.ts"

        self.original = self.source.encode("utf-8")
        self.proposed = self.source.replace(
            self.old_text,
            self.new_text,
            1,
        ).encode("utf-8")

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
        return verify_proposal_consistency(**arguments)

    def test_accepts_matching_proposal(self):
        result = self.verify()
        self.assertTrue(result.passed)
        self.assertEqual(result.reason, "verified")

    def test_rejects_modified_diff(self):
        altered = {
            **self.proposal,
            "unified_diff": "fake diff",
        }
        result = self.verify(proposal=altered)
        self.assertFalse(result.passed)
        self.assertEqual(result.reason, "proposal_mismatch")

    def test_rejects_wrong_proposed_digest(self):
        altered = {
            **self.proposal,
            "proposed_sha256": "f" * 64,
        }
        result = self.verify(proposal=altered)
        self.assertFalse(result.passed)

    def test_rejects_wrong_path(self):
        altered = {
            **self.proposal,
            "path": "src/other.ts",
        }
        result = self.verify(proposal=altered)
        self.assertFalse(result.passed)

    def test_rejects_missing_field(self):
        altered = dict(self.proposal)
        del altered["unified_diff"]

        result = self.verify(proposal=altered)
        self.assertFalse(result.passed)
        self.assertEqual(
            result.reason,
            "missing_proposal_field",
        )

    def test_rejects_modified_original(self):
        result = self.verify(
            original_content=b"changed source"
        )
        self.assertFalse(result.passed)

    def test_rejects_incorrect_replacement(self):
        result = self.verify(
            new_text='"unexpected"',
        )
        self.assertFalse(result.passed)

    def test_rejects_duplicate_target(self):
        duplicated = (
            'const a = "hello";\n'
            'const b = "hello";\n'
        ).encode("utf-8")

        result = self.verify(
            original_content=duplicated,
        )

        self.assertFalse(result.passed)
        self.assertEqual(
            result.reason,
            "target_not_unique",
        )

    def test_rejects_non_dictionary_proposal(self):
        result = self.verify(proposal="invalid")
        self.assertFalse(result.passed)
        self.assertEqual(
            result.reason,
            "invalid_proposal",
        )

    def test_does_not_modify_original(self):
        before = bytes(self.original)

        result = self.verify()

        self.assertTrue(result.passed)
        self.assertEqual(self.original, before)


if __name__ == "__main__":
    unittest.main()
