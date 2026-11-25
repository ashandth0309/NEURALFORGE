"""Offline authenticated request-envelope primitives for a future trusted service.

Does NOT create a listener, grant privileges, or authorize Docker execution.
The replay cache is process-local: it MUST NOT be treated as restart-safe.
Only use this within a separately authenticated, OS-isolated transport design.
"""

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from dataclasses import dataclass

from services.validator.service_contract import (
    MAX_REQUEST_BYTES,
    parse_service_request,
)

AUTH_VERSION = 1
MAX_ENVELOPE_BYTES = 8192
MAX_CLOCK_SKEW_SECONDS = 60
NONCE_PATTERN = re.compile(r"[0-9a-f]{32}")
MAC_PATTERN = re.compile(r"[0-9a-f]{64}")
ENVELOPE_FIELDS = frozenset({"version", "timestamp", "nonce", "request", "mac"})


def _pairs_no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("service_auth_duplicate_field")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("service_auth_invalid_json")


def _json_bytes(value):
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("ascii")


def _check_key(key):
    if type(key) is not bytes or len(key) < 32:
        raise ValueError("service_auth_invalid_key")


def _unsigned(version, timestamp, nonce, request):
    return {
        "version": version,
        "timestamp": timestamp,
        "nonce": nonce,
        "request": request,
    }


@dataclass(frozen=True)
class AuthenticatedRequest:
    payload: bytes
    nonce: str
    timestamp: int


class ReplayGuard:
    """Thread-safe, bounded, process-local nonce memory (not durable)."""

    def __init__(self, *, max_entries=4096):
        if type(max_entries) is not int or not 1 <= max_entries <= 65536:
            raise ValueError("service_auth_invalid_capacity")
        self._max_entries = max_entries
        self._nonces = {}
        self._mutex = threading.Lock()

    def claim(self, nonce, now):
        with self._mutex:
            expired = [
                n for n, timestamp in self._nonces.items()
                if abs(now - timestamp) > MAX_CLOCK_SKEW_SECONDS
            ]
            for n in expired:
                del self._nonces[n]
            if nonce in self._nonces:
                raise ValueError("service_auth_replay")
            if len(self._nonces) >= self._max_entries:
                raise ValueError("service_auth_capacity_exceeded")
            self._nonces[nonce] = now


def create_authenticated_envelope(payload: bytes, key: bytes, *, now=None, nonce=None) -> bytes:
    """Encode one canonical, signed recovery request; offline/test use only."""
    _check_key(key)
    parse_service_request(payload)
    if now is None:
        now = int(time.time())
    if type(now) is not int or now < 0:
        raise ValueError("service_auth_invalid_timestamp")
    if nonce is None:
        nonce = secrets.token_hex(16)
    if type(nonce) is not str or NONCE_PATTERN.fullmatch(nonce) is None:
        raise ValueError("service_auth_invalid_nonce")
    request = json.loads(payload.decode("utf-8"))
    unsigned = _unsigned(AUTH_VERSION, now, nonce, request)
    mac = hmac.new(key, _json_bytes(unsigned), hashlib.sha256).hexdigest()
    envelope = _json_bytes({**unsigned, "mac": mac})
    if len(envelope) > MAX_ENVELOPE_BYTES:
        raise ValueError("service_auth_invalid_size")
    return envelope


def verify_authenticated_envelope(envelope: bytes, key: bytes, guard: ReplayGuard, *, now=None) -> AuthenticatedRequest:
    """Verify timestamp, canonical MAC, strict request and process-local replay."""
    _check_key(key)
    if type(guard) is not ReplayGuard:
        raise ValueError("service_auth_guard_missing")
    if type(envelope) is not bytes or not 0 < len(envelope) <= MAX_ENVELOPE_BYTES:
        raise ValueError("service_auth_invalid_size")
    if now is None:
        now = int(time.time())
    if type(now) is not int or now < 0:
        raise ValueError("service_auth_invalid_timestamp")
    try:
        data = json.loads(
            envelope.decode("utf-8"),
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("service_auth_invalid_json") from exc
    if type(data) is not dict or frozenset(data) != ENVELOPE_FIELDS:
        raise ValueError("service_auth_invalid_fields")
    if type(data["version"]) is not int or data["version"] != AUTH_VERSION:
        raise ValueError("service_auth_invalid_version")
    if type(data["timestamp"]) is not int or data["timestamp"] < 0:
        raise ValueError("service_auth_invalid_timestamp")
    if abs(now - data["timestamp"]) > MAX_CLOCK_SKEW_SECONDS:
        raise ValueError("service_auth_expired")
    if type(data["nonce"]) is not str or NONCE_PATTERN.fullmatch(data["nonce"]) is None:
        raise ValueError("service_auth_invalid_nonce")
    if type(data["mac"]) is not str or MAC_PATTERN.fullmatch(data["mac"]) is None:
        raise ValueError("service_auth_invalid_mac")
    if type(data["request"]) is not dict:
        raise ValueError("service_auth_invalid_request")
    request_bytes = _json_bytes(data["request"])
    if len(request_bytes) > MAX_REQUEST_BYTES:
        raise ValueError("service_auth_invalid_request")
    parse_service_request(request_bytes)
    unsigned = _unsigned(data["version"], data["timestamp"], data["nonce"], data["request"])
    expected = hmac.new(key, _json_bytes(unsigned), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, data["mac"]):
        raise ValueError("service_auth_invalid_mac")
    guard.claim(data["nonce"], now)
    return AuthenticatedRequest(request_bytes, data["nonce"], data["timestamp"])
