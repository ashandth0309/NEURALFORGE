
"""Strict data-only request contract for a future validator service.

This module does not open sockets, read the journal, or execute
Docker commands. Authentication and transport are not implemented.
"""

import json
from dataclasses import dataclass


MAX_REQUEST_BYTES = 4096
PROTOCOL_VERSION = 1
ALLOWED_OPERATION = "recovery.inspect"

EXPECTED_KEYS = frozenset({
    "version",
    "operation",
})


@dataclass(frozen=True)
class ValidatorServiceRequest:
    version: int
    operation: str


def parse_service_request(
    payload: bytes,
) -> ValidatorServiceRequest:
    """Validate a complete UTF-8 JSON request.

    Reject unknown fields, duplicate keys, unsupported
    operations, and oversized or malformed requests.
    """

    if not isinstance(payload, bytes):
        raise ValueError("service_request_invalid_type")

    if not 0 < len(payload) <= MAX_REQUEST_BYTES:
        raise ValueError("service_request_invalid_size")

    try:
        def unique_object(pairs):
            result = {}

            for key, value in pairs:
                if key in result:
                    raise ValueError(
                        "service_request_duplicate_field"
                    )
                result[key] = value

            return result

        data = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=lambda value: (
                _reject_constant(value)
            ),
        )

    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "service_request_invalid_json"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError("service_request_invalid_shape")

    if frozenset(data) != EXPECTED_KEYS:
        raise ValueError("service_request_invalid_fields")

    if (
        type(data["version"]) is not int
        or data["version"] != PROTOCOL_VERSION
    ):
        raise ValueError(
            "service_request_unsupported_version"
        )

    if (
        type(data["operation"]) is not str
        or data["operation"] != ALLOWED_OPERATION
    ):
        raise ValueError(
            "service_request_operation_denied"
        )

    return ValidatorServiceRequest(
        version=PROTOCOL_VERSION,
        operation=ALLOWED_OPERATION,
    )


def _reject_constant(value):
    raise ValueError("service_request_invalid_constant")
