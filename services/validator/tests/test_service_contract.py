
"""Tests for the validator's data-only service contract."""

import json
import unittest

from services.validator.service_contract import (
    MAX_REQUEST_BYTES,
    parse_service_request,
)


class ServiceContractTests(unittest.TestCase):

    def test_accepts_recovery_inspection(self):
        payload = (
            b'{"version":1,"operation":"recovery.inspect"}'
        )

        request = parse_service_request(payload)

        self.assertEqual(request.version, 1)
        self.assertEqual(
            request.operation,
            "recovery.inspect",
        )

    def test_rejects_execution_operation(self):
        payload = (
            b'{"version":1,"operation":"docker.run"}'
        )

        with self.assertRaisesRegex(
            ValueError,
            "service_request_operation_denied",
        ):
            parse_service_request(payload)

    def test_rejects_command_injection_fields(self):
        payload = json.dumps({
            "version": 1,
            "operation": "recovery.inspect",
            "command": ["docker", "run"],
        }).encode("utf-8")

        with self.assertRaisesRegex(
            ValueError,
            "service_request_invalid_fields",
        ):
            parse_service_request(payload)

    def test_rejects_duplicate_json_fields(self):
        payload = (
            b'{"version":1,"version":1,'
            b'"operation":"recovery.inspect"}'
        )

        with self.assertRaisesRegex(
            ValueError,
            "service_request_duplicate_field",
        ):
            parse_service_request(payload)

    def test_rejects_unsupported_version(self):
        payload = (
            b'{"version":2,"operation":"recovery.inspect"}'
        )

        with self.assertRaisesRegex(
            ValueError,
            "service_request_unsupported_version",
        ):
            parse_service_request(payload)

    def test_rejects_oversized_request(self):
        with self.assertRaisesRegex(
            ValueError,
            "service_request_invalid_size",
        ):
            parse_service_request(
                b"x" * (MAX_REQUEST_BYTES + 1)
            )

    def test_rejects_invalid_json(self):
        with self.assertRaisesRegex(
            ValueError,
            "service_request_invalid_json",
        ):
            parse_service_request(b"{invalid")

    def test_rejects_boolean_version(self):
        payload = (
            b'{"version":true,'
            b'"operation":"recovery.inspect"}'
        )

        with self.assertRaisesRegex(
            ValueError,
            "service_request_unsupported_version",
        ):
            parse_service_request(payload)

    def test_rejects_nonfinite_constant(self):
        payload = (
            b'{"version":1,'
            b'"operation":NaN}'
        )

        with self.assertRaisesRegex(
            ValueError,
            "service_request_invalid_constant",
        ):
            parse_service_request(payload)


if __name__ == "__main__":
    unittest.main()
