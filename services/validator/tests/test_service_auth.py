"""Offline authentication-protocol tests. No sockets or Docker."""

import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from services.validator.service_auth import (
    ReplayGuard,
    create_authenticated_envelope,
    verify_authenticated_envelope,
)

KEY = b"a" * 32
REQUEST = b'{"version":1,"operation":"recovery.inspect"}'
NOW = 2000000000


class ServiceAuthTests(unittest.TestCase):
    def make(self, **kwargs):
        return create_authenticated_envelope(REQUEST, KEY, now=NOW, **kwargs)

    def test_valid_envelope(self):
        result = verify_authenticated_envelope(self.make(), KEY, ReplayGuard(), now=NOW)
        self.assertEqual(json.loads(result.payload)["operation"], "recovery.inspect")

    def test_replay_denied(self):
        guard = ReplayGuard()
        envelope = self.make()
        verify_authenticated_envelope(envelope, KEY, guard, now=NOW)
        with self.assertRaisesRegex(ValueError, "service_auth_replay"):
            verify_authenticated_envelope(envelope, KEY, guard, now=NOW)

    def test_tampered_request_denied(self):
        envelope = json.loads(self.make())
        envelope["request"]["operation"] = "docker.run"
        with self.assertRaises(ValueError):
            verify_authenticated_envelope(json.dumps(envelope).encode(), KEY, ReplayGuard(), now=NOW)

    def test_wrong_key_denied(self):
        with self.assertRaisesRegex(ValueError, "service_auth_invalid_mac"):
            verify_authenticated_envelope(self.make(), b"b" * 32, ReplayGuard(), now=NOW)

    def test_expired_denied(self):
        with self.assertRaisesRegex(ValueError, "service_auth_expired"):
            verify_authenticated_envelope(self.make(), KEY, ReplayGuard(), now=NOW + 61)

    def test_future_timestamp_denied(self):
        with self.assertRaisesRegex(ValueError, "service_auth_expired"):
            verify_authenticated_envelope(self.make(), KEY, ReplayGuard(), now=NOW - 61)

    def test_boolean_timestamp_denied(self):
        envelope = json.loads(self.make())
        envelope["timestamp"] = True
        with self.assertRaisesRegex(ValueError, "service_auth_invalid_timestamp"):
            verify_authenticated_envelope(json.dumps(envelope).encode(), KEY, ReplayGuard(), now=NOW)

    def test_duplicate_fields_denied(self):
        malformed = self.make().replace(b'"version":1', b'"version":1,"version":1')
        with self.assertRaisesRegex(ValueError, "service_auth_duplicate_field"):
            verify_authenticated_envelope(malformed, KEY, ReplayGuard(), now=NOW)

    def test_unsupported_operation_cannot_be_signed(self):
        with self.assertRaises(ValueError):
            create_authenticated_envelope(b'{"version":1,"operation":"docker.run"}', KEY, now=NOW)

    def test_short_key_denied(self):
        with self.assertRaisesRegex(ValueError, "service_auth_invalid_key"):
            create_authenticated_envelope(REQUEST, b"tiny", now=NOW)

    def test_replay_guard_fails_closed_at_capacity(self):
        guard = ReplayGuard(max_entries=1)
        guard.claim("a" * 32, NOW)
        with self.assertRaisesRegex(ValueError, "service_auth_capacity_exceeded"):
            guard.claim("b" * 32, NOW)

    def test_concurrent_same_nonce_only_one_succeeds(self):
        envelope = self.make(nonce="a" * 32)
        guard = ReplayGuard()
        barrier = threading.Barrier(8)

        def worker(_):
            barrier.wait(timeout=10)
            try:
                verify_authenticated_envelope(envelope, KEY, guard, now=NOW)
                return True
            except ValueError as exc:
                self.assertEqual(str(exc), "service_auth_replay")
                return False

        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(worker, range(8)))
        self.assertEqual(sum(outcomes), 1)


if __name__ == "__main__":
    unittest.main()
