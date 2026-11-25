"""Authentication gate tests. No real Docker, storage or IPC listener."""

import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
from unittest.mock import patch

from services.validator.service_auth import create_authenticated_envelope
from services.validator.service_boundary import AuthenticatedRecoveryBoundary

KEY = b"k" * 32
VALID = b'{"version":1,"operation":"recovery.inspect"}'
GOOD_REPLY = b'{"version":1,"operation":"recovery.inspect","success":true,"report":{}}'


class ServiceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.dispatcher = Mock(return_value=GOOD_REPLY)
        self.boundary = AuthenticatedRecoveryBoundary(KEY, dispatcher=self.dispatcher)

    def make(self, **kwargs):
        return create_authenticated_envelope(VALID, KEY, **kwargs)

    def test_valid_envelope_dispatches_once(self):
        self.assertEqual(self.boundary.handle(self.make()), GOOD_REPLY)
        self.dispatcher.assert_called_once()
        self.assertEqual(json.loads(self.dispatcher.call_args.args[0]), json.loads(VALID))

    def test_wrong_key_cannot_dispatch(self):
        raw = create_authenticated_envelope(VALID, b"z" * 32)
        self.assertFalse(json.loads(self.boundary.handle(raw))["success"])
        self.dispatcher.assert_not_called()

    def test_replay_cannot_dispatch_twice(self):
        envelope = self.make()
        self.boundary.handle(envelope)
        denied = json.loads(self.boundary.handle(envelope))
        self.assertFalse(denied["success"])
        self.assertFalse(denied["safe_to_retry"])
        self.dispatcher.assert_called_once()

    def test_unsigned_payload_cannot_dispatch(self):
        self.assertFalse(json.loads(self.boundary.handle(VALID))["success"])
        self.dispatcher.assert_not_called()

    def test_oversized_envelope_cannot_dispatch(self):
        self.assertFalse(json.loads(self.boundary.handle(b"x" * 9000))["success"])
        self.dispatcher.assert_not_called()

    def test_malformed_reply_fails_closed(self):
        self.dispatcher.return_value = b"not json"
        reply = self.boundary.handle(self.make())
        self.assertFalse(json.loads(reply)["success"])
        self.assertNotIn(b"not json", reply)

    def test_dispatcher_exception_fails_closed(self):
        self.dispatcher.side_effect = RuntimeError("private path")
        reply = self.boundary.handle(self.make())
        self.assertFalse(json.loads(reply)["success"])
        self.assertNotIn(b"private path", reply)

    def test_concurrent_same_nonce_dispatches_once(self):
        envelope = self.make(nonce="a" * 32)
        barrier = threading.Barrier(8)

        def worker(_):
            barrier.wait(timeout=10)
            return self.boundary.handle(envelope)

        with ThreadPoolExecutor(max_workers=8) as pool:
            replies = list(pool.map(worker, range(8)))
        self.assertEqual(self.dispatcher.call_count, 1)
        self.assertEqual(sum(json.loads(v)["success"] for v in replies), 1)

    def test_invalid_key_is_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            AuthenticatedRecoveryBoundary(b"short", dispatcher=self.dispatcher)
