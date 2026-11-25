
"""Tests for strict recovery report validation."""

import unittest

from services.validator.service_response import (
    validate_recovery_report,
)


def valid_report():
    """Create a valid empty recovery report."""

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


def report_with_record():
    """Create a valid report with one unresolved probe."""

    report = valid_report()

    report["recovery_required"] = True
    report["unresolved_count"] = 1
    report["docker_available"] = False

    report["records"] = [{
        "name": "neuralforge-probe-" + "a" * 24,
        "phase": "create_requested",
        "expected_image_id": "sha256:" + "b" * 64,
        "recorded_container_id": None,
        "discovery_status": "uncertain",
        "discovered_container_id": None,
        "requires_manual_review": True,
        "automatic_cleanup_allowed": False,
        "safe_to_retry": False,
    }]

    return report


class ServiceResponseTests(unittest.TestCase):

    def test_accepts_valid_empty_report(self):
        validate_recovery_report(valid_report())

    def test_accepts_valid_unresolved_record(self):
        validate_recovery_report(report_with_record())

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

    def test_rejects_invalid_probe_name(self):
        report = report_with_record()
        report["records"][0]["name"] = "../other-probe"

        with self.assertRaises(ValueError):
            validate_recovery_report(report)

    def test_rejects_invalid_image_digest(self):
        report = report_with_record()
        report["records"][0]["expected_image_id"] = (
            "sha256:not-a-digest"
        )

        with self.assertRaises(ValueError):
            validate_recovery_report(report)

    def test_rejects_invalid_lifecycle_phase(self):
        report = report_with_record()
        report["records"][0]["phase"] = "unknown"

        with self.assertRaises(ValueError):
            validate_recovery_report(report)

    def test_rejects_removed_record_as_unresolved(self):
        report = report_with_record()
        report["records"][0]["phase"] = "removed"

        with self.assertRaises(ValueError):
            validate_recovery_report(report)

    def test_rejects_malformed_container_id(self):
        report = report_with_record()
        report["records"][0]["recorded_container_id"] = (
            "invalid-container-id"
        )

        with self.assertRaises(ValueError):
            validate_recovery_report(report)

    def test_rejects_nonstring_container_id(self):
        report = report_with_record()
        report["records"][0]["recorded_container_id"] = 123

        with self.assertRaisesRegex(
            ValueError,
            "invalid_recovery_record",
        ):
            validate_recovery_report(report)

    def test_rejects_owned_container_without_id(self):
        report = report_with_record()

        report["records"][0]["discovery_status"] = (
            "present_owned"
        )

        with self.assertRaises(ValueError):
            validate_recovery_report(report)

    def test_rejects_owned_container_id_mismatch(self):
        report = report_with_record()

        record = report["records"][0]
        record["recorded_container_id"] = "c" * 64
        record["discovered_container_id"] = "d" * 64
        record["discovery_status"] = "present_owned"

        with self.assertRaises(ValueError):
            validate_recovery_report(report)

    def test_accepts_matching_owned_container(self):
        report = report_with_record()

        record = report["records"][0]
        record["recorded_container_id"] = "c" * 64
        record["discovered_container_id"] = "c" * 64
        record["discovery_status"] = "present_owned"

        validate_recovery_report(report)


if __name__ == "__main__":
    unittest.main()
