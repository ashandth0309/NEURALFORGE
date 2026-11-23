
import unittest
from dataclasses import FrozenInstanceError

from services.validator.policy import (
    ValidationPlan,
    create_validation_plan,
)


class ValidationPolicyTests(unittest.TestCase):

    def setUp(self):
        self.options = {
            "repository_id": "demo-repo",
            "source_path": "src/app/page.tsx",
            "original_sha256": "a" * 64,
            "proposed_sha256": "b" * 64,
            "checks": (
                "patch_integrity",
                "typescript_typecheck",
            ),
        }

    def make_plan(self, **changes):
        return create_validation_plan(
            **{**self.options, **changes}
        )

    def test_creates_allowed_plan(self):
        plan = self.make_plan()

        self.assertIsInstance(plan, ValidationPlan)
        self.assertEqual(
            plan.repository_id,
            "demo-repo",
        )
        self.assertEqual(len(plan.checks), 2)

    def test_plan_is_immutable(self):
        plan = self.make_plan()

        with self.assertRaises(FrozenInstanceError):
            plan.repository_id = "different"

    def test_rejects_arbitrary_command(self):
        with self.assertRaises(ValueError):
            self.make_plan(
                checks=(
                    "patch_integrity",
                    "cmd /c whoami",
                )
            )

    def test_rejects_missing_integrity_check(self):
        with self.assertRaises(ValueError):
            self.make_plan(
                checks=("typescript_typecheck",)
            )

    def test_rejects_duplicate_checks(self):
        with self.assertRaises(ValueError):
            self.make_plan(
                checks=(
                    "patch_integrity",
                    "patch_integrity",
                )
            )

    def test_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            self.make_plan(
                source_path="../outside.ts"
            )

    def test_rejects_windows_absolute_path(self):
        with self.assertRaises(ValueError):
            self.make_plan(
                source_path="C:\\temp\\file.ts"
            )

    def test_rejects_invalid_digest(self):
        with self.assertRaises(ValueError):
            self.make_plan(
                original_sha256="invalid"
            )

    def test_rejects_unchanged_digest(self):
        with self.assertRaises(ValueError):
            self.make_plan(
                proposed_sha256="a" * 64
            )

    def test_allows_integrity_only(self):
        plan = self.make_plan(
            checks=("patch_integrity",)
        )

        self.assertEqual(
            plan.checks,
            ("patch_integrity",),
        )


if __name__ == "__main__":
    unittest.main()
