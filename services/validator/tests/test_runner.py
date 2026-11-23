
import hashlib
import shutil
import unittest
from unittest.mock import patch

from services.patcher.proposal import propose_replacement
from services.validator.git_patch import GitPatchResult
from services.validator.policy import create_validation_plan
from services.validator.runner import run_patch_validation


class ValidationRunnerTests(unittest.TestCase):

    def setUp(self):
        self.source = 'export const message = "hello";\n'
        self.original = self.source.encode("utf-8")
        self.old_text = '"hello"'
        self.new_text = '"hello world"'

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
            source_path="src/example.ts",
            original_sha256=self.original_digest,
            proposed_sha256=self.proposed_digest,
            checks=("patch_integrity",),
        )

        self.proposal = propose_replacement(
            path="src/example.ts",
            source=self.source,
            old_text=self.old_text,
            new_text=self.new_text,
            expected_sha256=self.original_digest,
        )

    def run_validation(self, **changes):
        arguments = {
            "plan": self.plan,
            "original_content": self.original,
            "old_text": self.old_text,
            "new_text": self.new_text,
            "proposal": self.proposal,
        }
        arguments.update(changes)

        return run_patch_validation(**arguments)

    @unittest.skipUnless(
        shutil.which("git"),
        "Git required for real validation",
    )
    def test_successful_real_git_validation(self):
        report = self.run_validation()

        self.assertTrue(report.passed)
        self.assertEqual(len(report.checks), 1)
        self.assertEqual(
            report.checks[0].reason,
            "verified",
        )
        self.assertGreaterEqual(
            report.total_duration_ms,
            0,
        )

    def test_tampered_patch_produces_failed_report(self):
        altered = {
            **self.proposal,
            "unified_diff": "tampered patch",
        }

        report = self.run_validation(
            proposal=altered,
        )

        self.assertFalse(report.passed)
        self.assertEqual(
            report.checks[0].reason,
            "proposal_mismatch",
        )

    def test_rejects_unimplemented_typescript_check(self):
        plan = create_validation_plan(
            repository_id="demo-repo",
            source_path="src/example.ts",
            original_sha256=self.original_digest,
            proposed_sha256=self.proposed_digest,
            checks=(
                "patch_integrity",
                "typescript_typecheck",
            ),
        )

        with patch(
            "services.validator.runner.verify_git_patch"
        ) as mocked:
            with self.assertRaises(ValueError):
                self.run_validation(plan=plan)

        mocked.assert_not_called()

    def test_reports_git_unavailable(self):
        with patch(
            "services.validator.runner.verify_git_patch",
            return_value=GitPatchResult(
                False,
                "git_unavailable",
                None,
            ),
        ):
            report = self.run_validation()

        self.assertFalse(report.passed)
        self.assertEqual(
            report.checks[0].reason,
            "git_unavailable",
        )

    def test_report_is_json_serializable(self):
        with patch(
            "services.validator.runner.verify_git_patch",
            return_value=GitPatchResult(
                True,
                "verified",
                self.proposed_digest,
            ),
        ):
            report = self.run_validation()

        data = report.to_dict()

        self.assertEqual(
            data["repository_id"],
            "demo-repo",
        )
        self.assertTrue(data["passed"])
        self.assertEqual(
            data["checks"][0]["check"],
            "patch_integrity",
        )

    def test_original_content_is_preserved(self):
        original_copy = bytes(self.original)

        with patch(
            "services.validator.runner.verify_git_patch",
            return_value=GitPatchResult(
                True,
                "verified",
                self.proposed_digest,
            ),
        ):
            self.run_validation()

        self.assertEqual(
            self.original,
            original_copy,
        )


if __name__ == "__main__":
    unittest.main()
