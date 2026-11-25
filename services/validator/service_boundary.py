"""Authenticated recovery entry point for a future isolated service.

No listener, service installation, or Windows identity boundary is created here.
Call only from a trusted service process which owns the secret and replay guard.
"""

import json
from threading import Lock

from services.validator.service_auth import (
    ReplayGuard,
    verify_authenticated_envelope,
)
from services.validator.service_dispatcher import (
    dispatch_service_request,
)

MAX_REPLY_BYTES = 65536


def _error_reply() -> bytes:
    return json.dumps({
        "version": 1,
        "operation": "recovery.inspect",
        "success": False,
        "error": "authenticated_inspection_failed",
        "recovery_status": "unknown",
        "safe_to_retry": False,
    }, separators=(",", ":")).encode("ascii")


class AuthenticatedRecoveryBoundary:
    """Fail-closed in-process adapter, not a transport or OS boundary.

    The same instance/ReplayGuard must outlive individual requests. A restart
    clears nonce memory, so this is not a durable multi-process replay defense.
    """

    def __init__(self, key: bytes, *, guard: ReplayGuard | None = None,
                 dispatcher=None):
        if type(key) is not bytes or len(key) < 32:
            raise ValueError("service_boundary_invalid_key")
        if guard is not None and type(guard) is not ReplayGuard:
            raise ValueError("service_boundary_invalid_guard")
        if dispatcher is not None and not callable(dispatcher):
            raise ValueError("service_boundary_invalid_dispatcher")
        self._key = key
        self._guard = guard if guard is not None else ReplayGuard()
        self._dispatcher = (dispatcher if dispatcher is not None
                            else dispatch_service_request)
        # Avoid dispatch of multiple recovery requests concurrently in one
        # process. Cross-process serialization remains the journal OS lock.
        self._dispatch_lock = Lock()

    def handle(self, envelope: bytes) -> bytes:
        """Authenticate before invoking the recovery dispatcher.

        Invalid/unknown requests receive a generic bounded error. No caller
        input chooses a Docker command, path, or different operation.
        """
        try:
            authenticated = verify_authenticated_envelope(
                envelope, self._key, self._guard
            )
            with self._dispatch_lock:
                reply = self._dispatcher(authenticated.payload)
            if type(reply) is not bytes or not 0 < len(reply) <= MAX_REPLY_BYTES:
                raise RuntimeError("service_boundary_invalid_reply")
            # Require the dispatcher to produce a legitimate JSON object.
            response = json.loads(reply.decode("utf-8"))
            if (
                type(response) is not dict
                or response.get("version") != 1
                or response.get("operation") != "recovery.inspect"
                or type(response.get("success")) is not bool
            ):
                raise RuntimeError("service_boundary_invalid_reply")
            return reply
        except Exception:
            return _error_reply()
