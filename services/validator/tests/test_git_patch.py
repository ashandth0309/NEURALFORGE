
import hashlib
import shutil
import tempfile
import unittest

import subprocess

import os
import subprocess
from unittest.mock import patch

from unittest.mock import patch

from pathlib import Path

from services.validator.git_patch import _resolve_git_executable

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


    def test_reports_missing_git(self):
        with patch(
            "services.validator.git_patch.subprocess.run",
            side_effect=FileNotFoundError(),
        ):
            result = self.verify()

        self.assertFalse(result.passed)
        self.assertEqual(result.reason, "git_unavailable")
        self.assertIsNone(result.actual_sha256)

    def test_reports_git_timeout(self):
        with patch(
            "services.validator.git_patch.subprocess.run",
            side_effect=subprocess.TimeoutExpired(
                cmd=["git", "init"],
                timeout=10,
            ),
        ):
            result = self.verify()

        self.assertFalse(result.passed)
        self.assertEqual(result.reason, "git_timeout")
        self.assertIsNone(result.actual_sha256)

    def test_reports_git_initialization_failure(self):
        failed = subprocess.CompletedProcess(
            args=["git", "init"],
            returncode=1,
            stdout=b"",
            stderr=b"initialization failed",
        )

        with patch(
            "services.validator.git_patch.subprocess.run",
            return_value=failed,
        ):
            result = self.verify()

        self.assertFalse(result.passed)
        self.assertEqual(
            result.reason,
            "git_initialization_failed",
        )

    def test_reports_git_patch_check_failure(self):
        successful = subprocess.CompletedProcess(
            args=["git", "init"],
            returncode=0,
            stdout=b"",
            stderr=b"",
        )

        failed = subprocess.CompletedProcess(
            args=["git", "apply", "--check"],
            returncode=1,
            stdout=b"",
            stderr=b"patch rejected",
        )

        with patch(
            "services.validator.git_patch.subprocess.run",
            side_effect=[successful, failed],
        ) as mocked:
            result = self.verify()

        self.assertFalse(result.passed)
        self.assertEqual(
            result.reason,
            "git_patch_check_failed",
        )
        self.assertEqual(mocked.call_count, 2)



    def test_git_subprocess_ignores_inherited_git_settings(self):
        successful = subprocess.CompletedProcess(
            args=["git"],
            returncode=0,
            stdout=b"",
            stderr=b"",
        )

        inherited = {
            "GIT_DIR": "C:\\outside-repository",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.autocrlf",
            "GIT_CONFIG_VALUE_0": "true",
        }

        with patch.dict(os.environ, inherited):
            with patch(
                "services.validator.git_patch.subprocess.run",
                return_value=successful,
            ) as mocked:
                result = self.verify()

        # Mocked Git never applies the patch.
        self.assertFalse(result.passed)
        self.assertEqual(mocked.call_count, 3)

        for call in mocked.call_args_list:
            environment = call.kwargs["env"]

            self.assertNotIn("GIT_DIR", environment)
            self.assertNotIn("GIT_CONFIG_COUNT", environment)
            self.assertNotIn("GIT_CONFIG_KEY_0", environment)
            self.assertNotIn("GIT_CONFIG_VALUE_0", environment)

            self.assertEqual(
                environment["GIT_CONFIG_NOSYSTEM"],
                "1",
            )
            self.assertEqual(
                environment["GIT_CONFIG_GLOBAL"],
                os.devnull,
            )
            self.assertEqual(
                environment["GIT_TERMINAL_PROMPT"],
                "0",
            )

    def test_resolves_explicit_git_executable(self):
        import shutil

        executable = shutil.which("git")
        self.assertIsNotNone(executable)

        with patch.dict(
            os.environ,
            {"NEURALFORGE_GIT_EXECUTABLE": executable},
        ):
            resolved = _resolve_git_executable()

        self.assertIsNotNone(resolved)
        self.assertTrue(Path(resolved).is_file())
        self.assertTrue(Path(resolved).is_absolute())

    def test_rejects_relative_git_executable(self):
        with patch.dict(
            os.environ,
            {"NEURALFORGE_GIT_EXECUTABLE": "git.exe"},
        ):
            with patch(
                "services.validator.git_patch.subprocess.run"
            ) as mocked:
                result = self.verify()

        self.assertFalse(result.passed)
        self.assertEqual(
            result.reason,
            "git_unavailable",
        )
        mocked.assert_not_called()

    def test_rejects_missing_configured_executable(self):
        with patch.dict(
            os.environ,
            {
                "NEURALFORGE_GIT_EXECUTABLE":
                    r"C:\nonexistent\git.exe"
            },
        ):
            with patch(
                "services.validator.git_patch.subprocess.run"
            ) as mocked:
                result = self.verify()

        self.assertFalse(result.passed)
        self.assertEqual(
            result.reason,
            "git_unavailable",
        )
        mocked.assert_not_called()


if __name__ == "__main__":
    unittest.main()
