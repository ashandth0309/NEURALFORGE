"""Bounded byte framing tests, using memory streams only."""

import io
import json
import struct
import unittest
from unittest.mock import Mock

from services.validator.service_auth import create_authenticated_envelope
from services.validator.service_boundary import AuthenticatedRecoveryBoundary
from services.validator.service_framing import (
    encode_frame, read_frame, handle_one_framed_request,
)

KEY = b"a" * 32
REQ = b'{"version":1,"operation":"recovery.inspect"}'
REPLY = b'{"version":1,"operation":"recovery.inspect","success":true}'


class ServiceFramingTests(unittest.TestCase):
    def test_frame_roundtrip(self):
        self.assertEqual(read_frame(io.BytesIO(encode_frame(b"abc"))), b"abc")

    def test_rejects_zero_length(self):
        with self.assertRaisesRegex(ValueError, "service_frame_invalid_size"):
            read_frame(io.BytesIO(struct.pack("!I", 0)))

    def test_rejects_oversized_length_before_reading_body(self):
        with self.assertRaisesRegex(ValueError, "service_frame_invalid_size"):
            read_frame(io.BytesIO(struct.pack("!I", 999999)))

    def test_rejects_truncated_body(self):
        with self.assertRaisesRegex(ValueError, "service_frame_incomplete"):
            read_frame(io.BytesIO(struct.pack("!I", 4) + b"a"))

    def test_rejects_truncated_header(self):
        with self.assertRaisesRegex(ValueError, "service_frame_incomplete"):
            read_frame(io.BytesIO(b"\x00"))

    def test_authenticated_framed_dispatch(self):
        dispatch = Mock(return_value=REPLY)
        boundary = AuthenticatedRecoveryBoundary(KEY, dispatcher=dispatch)
        envelope = create_authenticated_envelope(REQ, KEY)
        sink = io.BytesIO()
        handle_one_framed_request(io.BytesIO(encode_frame(envelope)), sink, boundary)
        self.assertEqual(read_frame(io.BytesIO(sink.getvalue()), max_bytes=65536), REPLY)
        dispatch.assert_called_once()
        self.assertEqual(json.loads(dispatch.call_args.args[0]), json.loads(REQ))

    def test_invalid_frame_never_dispatches(self):
        dispatch = Mock(return_value=REPLY)
        boundary = AuthenticatedRecoveryBoundary(KEY, dispatcher=dispatch)
        sink = io.BytesIO()
        handle_one_framed_request(io.BytesIO(struct.pack("!I", 999999)), sink, boundary)
        result = json.loads(read_frame(io.BytesIO(sink.getvalue()), max_bytes=65536))
        self.assertFalse(result["success"])
        dispatch.assert_not_called()

    def test_invalid_auth_never_dispatches(self):
        dispatch = Mock(return_value=REPLY)
        boundary = AuthenticatedRecoveryBoundary(KEY, dispatcher=dispatch)
        sink = io.BytesIO()
        handle_one_framed_request(io.BytesIO(encode_frame(b"bad")), sink, boundary)
        result = json.loads(read_frame(io.BytesIO(sink.getvalue()), max_bytes=65536))
        self.assertFalse(result["success"])
        dispatch.assert_not_called()
