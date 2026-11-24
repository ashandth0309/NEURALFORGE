
"""Tests for strict recovery report validation."""

import unittest

from services.validator.service_response import (
    validate_recovery_report,
)


def valid_report():
    return {
        "schema_version": 1,
        "report_type": "docker_probe_recovery",
        "read_only": True,
        "automatic_cleanup_allowed": False,
        "recovery_required": False,
        "unresolved_count": 0,
        "records": [],
        "docker_available": None,
    }


class ServiceResponseTests(unittest.TestCase):

    def test_accepts_valid_empty_report(self):
        validate_recovery_report(valid_report())

    def test_rejects_inconsistent_count(self):
        report = valid_report()
        report["unresolved_count"] = 1

        with self.assertRaises(ValueError):
            validate_recovery_report(report)

    def test_rejects_inconsistent_recovery_status(self):
        report = valid_report()
        report["recovery_required"] = True

        with self.assertRaises(ValueError):
            validate_recovery_report(report)

    def test_rejects_boolean_count(self):
        report = valid_report()
        report["unresolved_count"] = False

        with self.assertRaises(ValueError):
            validate_recovery_report(report)

    def test_rejects_automatic_cleanup(self):
        report = valid_report()
        report["automatic_cleanup_allowed"] = True

        with self.assertRaises(ValueError):
            validate_recovery_report(report)

    def test_rejects_unexpected_field(self):
        report = valid_report()
        report["command"] = "docker run"

        with self.assertRaises(ValueError):
            validate_recovery_report(report)


if __name__ == "__main__":
    unittest.main()
