
import unittest
from dataclasses import FrozenInstanceError

from services.validator.policy import create_validation_plan
from services.validator.report import (
    CheckReport,
    create_validation_report,
)


class ValidationReportTests(unittest.TestCase):

    def setUp(self):
        self.plan = create_validation_plan(
            repository_id="demo-repo",
            source_path="src/app/page.tsx",
            original_sha256="a" * 64,
            proposed_sha256="b" * 64,
            checks=(
                "patch_integrity",
                "typescript_typecheck",
            ),
        )

    def test_creates_successful_report(self):
        results = (
            CheckReport("patch_integrity", True, "verified", 15),
            CheckReport("typescript_typecheck", True, "verified", 250),
        )

        report = create_validation_report(self.plan, results)

        self.assertTrue(report.passed)
        self.assertEqual(report.total_duration_ms, 265)
        self.assertEqual(len(report.checks), 2)

    def test_creates_failed_report(self):
        results = (
            CheckReport("patch_integrity", True, "verified", 10),
            CheckReport(
                "typescript_typecheck",
                False,
                "type_error",
                120,
            ),
        )

        report = create_validation_report(self.plan, results)

        self.assertFalse(report.passed)
        self.assertEqual(report.total_duration_ms, 130)

    def test_rejects_missing_results(self):
        results = (
            CheckReport("patch_integrity", True, "verified", 10),
        )

        with self.assertRaises(ValueError):
            create_validation_report(self.plan, results)

    def test_rejects_wrong_check_order(self):
        results = (
            CheckReport("typescript_typecheck", True, "verified", 10),
            CheckReport("patch_integrity", True, "verified", 10),
        )

        with self.assertRaises(ValueError):
            create_validation_report(self.plan, results)

    def test_rejects_negative_duration(self):
        results = (
            CheckReport("patch_integrity", True, "verified", -1),
            CheckReport("typescript_typecheck", True, "verified", 10),
        )

        with self.assertRaises(ValueError):
            create_validation_report(self.plan, results)

    def test_rejects_invalid_reason(self):
        results = (
            CheckReport(
                "patch_integrity",
                False,
                "C:\\private\\secret.txt",
                10,
            ),
            CheckReport("typescript_typecheck", True, "verified", 10),
        )

        with self.assertRaises(ValueError):
            create_validation_report(self.plan, results)

    def test_rejects_inconsistent_success(self):
        results = (
            CheckReport("patch_integrity", True, "timeout", 10),
            CheckReport("typescript_typecheck", True, "verified", 10),
        )

        with self.assertRaises(ValueError):
            create_validation_report(self.plan, results)

    def test_serializes_report(self):
        results = (
            CheckReport("patch_integrity", True, "verified", 5),
            CheckReport("typescript_typecheck", True, "verified", 8),
        )

        report = create_validation_report(self.plan, results)
        data = report.to_dict()

        self.assertEqual(data["repository_id"], "demo-repo")
        self.assertEqual(data["total_duration_ms"], 13)
        self.assertEqual(data["checks"][0]["check"], "patch_integrity")

    def test_report_is_immutable(self):
        results = (
            CheckReport("patch_integrity", True, "verified", 5),
            CheckReport("typescript_typecheck", True, "verified", 8),
        )

        report = create_validation_report(self.plan, results)

        with self.assertRaises(FrozenInstanceError):
            report.passed = False


if __name__ == "__main__":
    unittest.main()
