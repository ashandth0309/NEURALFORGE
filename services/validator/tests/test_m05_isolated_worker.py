"""Standalone offline worker security tests. No Windows ACL or Docker operations."""
import importlib.util
from contextlib import closing
import io
import json
from pathlib import Path
import sqlite3
import struct
import tempfile
import unittest

WORKER_PATH = Path(__file__).resolve().parents[3] / "tools" / "m05_isolated_worker.py"
spec = importlib.util.spec_from_file_location("m05_isolated_worker", WORKER_PATH)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class IsolatedWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assertEqual(worker.initialize(self.root), "LAB_INITIALIZED")
        self.key = (self.root / worker.KEY_NAME).read_bytes()

    def test_initialized_key_and_schema(self):
        self.assertEqual(len(self.key), 32)
        with closing(sqlite3.connect(self.root / worker.DB_NAME)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM probe_lifecycle").fetchone()[0], 0)

    def test_no_reinitialize_existing_storage(self):
        with self.assertRaises(RuntimeError):
            worker.initialize(self.root)

    def test_authorized_empty_report(self):
        result = json.loads(worker.process(worker.make_envelope(self.key, now=200000), self.root, now=200000))
        self.assertTrue(result["success"])
        self.assertFalse(result["report"]["recovery_required"])
        self.assertFalse(result["report"]["docker_contacted"])

    def test_unresolved_is_not_safe_to_retry(self):
        with closing(sqlite3.connect(self.root / worker.DB_NAME)) as db:
            db.execute("INSERT INTO probe_lifecycle (name,image_id,phase) VALUES (?,?,?)",
                       ("neuralforge-probe-" + "a" * 24, "sha256:" + "b" * 64, "prepared"))
            db.commit()
        result = json.loads(worker.process(worker.make_envelope(self.key), self.root))
        self.assertTrue(result["success"])
        self.assertEqual(result["report"]["unresolved_count"], 1)
        self.assertFalse(result["report"]["safe_to_retry"])

    def test_wrong_mac_fails_closed(self):
        envelope = json.loads(worker.make_envelope(self.key))
        envelope["mac"] = "0" * 64
        result = json.loads(worker.process(json.dumps(envelope).encode(), self.root))
        self.assertFalse(result["success"])

    def test_unsigned_request_fails_closed(self):
        result = json.loads(worker.process(b'{"version":1,"operation":"recovery.inspect"}', self.root))
        self.assertFalse(result["success"])

    def test_missing_database_fails_closed_without_recreation(self):
        db = self.root / worker.DB_NAME
        db.unlink()
        result = json.loads(worker.process(worker.make_envelope(self.key), self.root))
        self.assertFalse(result["success"])
        self.assertFalse(db.exists())

    def test_truncated_frame_fails_closed(self):
        dst = io.BytesIO()
        worker.serve_stdio_once(self.root, io.BytesIO(struct.pack("!I", 100) + b"x"), dst)
        result = json.loads(dst.getvalue()[4:])
        self.assertFalse(result["success"])

    def test_oversized_frame_fails_closed(self):
        dst = io.BytesIO()
        worker.serve_stdio_once(self.root, io.BytesIO(struct.pack("!I", 99999999)), dst)
        result = json.loads(dst.getvalue()[4:])
        self.assertFalse(result["success"])

    def test_framed_valid_inspection(self):
        envelope = worker.make_envelope(self.key)
        incoming = io.BytesIO(struct.pack("!I", len(envelope)) + envelope)
        dst = io.BytesIO()
        worker.serve_stdio_once(self.root, incoming, dst)
        raw = dst.getvalue()
        self.assertEqual(struct.unpack("!I", raw[:4])[0], len(raw) - 4)
        self.assertTrue(json.loads(raw[4:])["success"])


if __name__ == "__main__":
    unittest.main()
