
"""Tests for the data-only validator request dispatcher."""

import json
import unittest
from unittest.mock import patch

from services.validator.service_dispatcher import (
    dispatch_service_request,
)


MODULE = "services.validator.service_dispatcher"
VALID_REQUEST = (
    b'{"version":1,"operation":"recovery.inspect"}'
)


def sample_report():
    return {
        "schema_version": 1,
        "report_type": "docker_probe_recovery",
        "read_only": True,
        "automatic_cleanup_allowed": False,
        "recovery_required": False,
        "unresolved_count": 0,
        "records": [],
    }


class ServiceDispatcherTests(unittest.TestCase):

    def test_successful_recovery_inspection(self):
        with patch(
            MODULE + ".inspect_persistent_recovery",
            return_value=sample_report(),
        ) as inspect:
            response = json.loads(
                dispatch_service_request(VALID_REQUEST)
            )

        self.assertTrue(response["success"])
        self.assertEqual(
            response["operation"],
            "recovery.inspect",
        )
        self.assertEqual(
            response["report"]["unresolved_count"],
            0,
        )
        inspect.assert_called_once_with()

    def test_rejects_execution_request_before_dispatch(self):
        with patch(
            MODULE + ".inspect_persistent_recovery"
        ) as inspect:
            with self.assertRaises(ValueError):
                dispatch_service_request(
                    b'{"version":1,"operation":"docker.run"}'
                )

        inspect.assert_not_called()

    def test_rejects_caller_supplied_command(self):
        with patch(
            MODULE + ".inspect_persistent_recovery"
        ) as inspect:
            with self.assertRaises(ValueError):
                dispatch_service_request(
                    b'{"version":1,'
                    b'"operation":"recovery.inspect",'
                    b'"command":"docker run"}'
                )

        inspect.assert_not_called()

    def test_recovery_failure_is_not_reported_as_safe(self):
        with patch(
            MODULE + ".inspect_persistent_recovery",
            side_effect=RuntimeError(
                "private_filesystem_information"
            ),
        ):
            raw = dispatch_service_request(VALID_REQUEST)

        response = json.loads(raw)

        self.assertFalse(response["success"])
        self.assertEqual(
            response["recovery_status"],
            "unknown",
        )
        self.assertFalse(response["safe_to_retry"])
        self.assertNotIn(
            b"private_filesystem_information",
            raw,
        )

    def test_rejects_invalid_report(self):
        invalid = sample_report()
        invalid["automatic_cleanup_allowed"] = True

        with patch(
            MODULE + ".inspect_persistent_recovery",
            return_value=invalid,
        ):
            response = json.loads(
                dispatch_service_request(VALID_REQUEST)
            )

        self.assertFalse(response["success"])
        self.assertFalse(response["safe_to_retry"])

    def test_rejects_oversized_response(self):
        large = sample_report()
        large["records"] = ["x" * 70000]

        with patch(
            MODULE + ".inspect_persistent_recovery",
            return_value=large,
        ):
            raw = dispatch_service_request(VALID_REQUEST)

        response = json.loads(raw)

        self.assertFalse(response["success"])
        self.assertLess(len(raw), 65536)


if __name__ == "__main__":
    unittest.main()
