"""Bounded single-message framing for a trusted local byte stream.

This code does not open a socket, pipe or listener and does not authenticate
OS peer identities. The caller must supply an already trusted byte stream.
"""

import struct

from services.validator.service_auth import MAX_ENVELOPE_BYTES
from services.validator.service_boundary import MAX_REPLY_BYTES

FRAME_HEADER_BYTES = 4


def encode_frame(payload: bytes, *, max_bytes: int = MAX_REPLY_BYTES) -> bytes:
    if type(payload) is not bytes or not 0 < len(payload) <= max_bytes:
        raise ValueError("service_frame_invalid_size")
    return struct.pack("!I", len(payload)) + payload


def _read_exact(stream, count: int) -> bytes:
    remaining = count
    chunks = []
    while remaining:
        block = stream.read(remaining)
        if type(block) is not bytes or not block:
            raise ValueError("service_frame_incomplete")
        if len(block) > remaining:
            raise ValueError("service_frame_invalid_stream")
        chunks.append(block)
        remaining -= len(block)
    return b"".join(chunks)


def read_frame(stream, *, max_bytes: int = MAX_ENVELOPE_BYTES) -> bytes:
    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("service_frame_invalid_limit")
    header = _read_exact(stream, FRAME_HEADER_BYTES)
    (length,) = struct.unpack("!I", header)
    if not 0 < length <= max_bytes:
        raise ValueError("service_frame_invalid_size")
    return _read_exact(stream, length)


def handle_one_framed_request(stream_in, stream_out, boundary) -> None:
    """Read one bounded envelope, invoke boundary, emit one bounded reply.

    Stream ownership, timeouts, ACLs, identity and transport lifecycle belong
    to the future trusted service host, not to this module.
    """
    try:
        envelope = read_frame(stream_in, max_bytes=MAX_ENVELOPE_BYTES)
        response = boundary.handle(envelope)
    except Exception:
        # No request was authenticated; do not dispatch or provide detail.
        from services.validator.service_boundary import _error_reply
        response = _error_reply()
    stream_out.write(encode_frame(response, max_bytes=MAX_REPLY_BYTES))
    stream_out.flush()
