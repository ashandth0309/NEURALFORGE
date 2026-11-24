
"""Data-only dispatcher for the future validator service.

No transport, authentication, or Docker mutation.
This module must not be exposed to untrusted callers
until a separate service security boundary exists.
"""

import json

from services.validator.service_contract import (
    ALLOWED_OPERATION,
    parse_service_request,
)
from services.validator.docker_probe_operator import (
    inspect_persistent_recovery,
)


MAX_RESPONSE_BYTES = 65536


def dispatch_service_request(payload: bytes) -> bytes:
    """Validate and process one recovery inspection request."""

    request = parse_service_request(payload)

    if request.operation != ALLOWED_OPERATION:
        raise ValueError("service_operation_denied")

    try:
        report = inspect_persistent_recovery()

        if (
            not isinstance(report, dict)
            or report.get("report_type")
            != "docker_probe_recovery"
            or report.get("read_only") is not True
            or report.get("automatic_cleanup_allowed")
            is not False
        ):
            raise RuntimeError("invalid_recovery_report")

        response = {
            "version": 1,
            "operation": request.operation,
            "success": True,
            "report": report,
        }

        encoded = json.dumps(
            response,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")

        if len(encoded) > MAX_RESPONSE_BYTES:
            raise RuntimeError("service_response_too_large")

        return encoded

    except Exception:
        # Do not expose local paths, exceptions,
        # or internal operating-system details.
        return json.dumps({
            "version": 1,
            "operation": ALLOWED_OPERATION,
            "success": False,
            "error": "recovery_inspection_failed",
            "recovery_status": "unknown",
            "safe_to_retry": False,
        }, separators=(",", ":")).encode("utf-8")
