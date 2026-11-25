"""M05 restricted-account, one-shot recovery worker (offline laboratory only).

No listener, Docker commands, or writable journal inspection. stdlib only.
Install code read-only for the service principal; keep data in separately ACLed lab.
"""
import hashlib
from contextlib import closing
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import struct
import sys
import time

LAB = Path(r"C:\ProgramData\NEURALFORGE-M05-IsolationLab")
DB_NAME = "probe_lifecycle.sqlite3"
KEY_NAME = "m05_lab_hmac.key"
MAX_INPUT = 8192
MAX_OUTPUT = 65536
MAX_AGE = 60


def _encode(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _pairs(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError("duplicate_json_field")
        d[k] = v
    return d


def _invalid_constant(_):
    raise ValueError("invalid_constant")


def _read_key(root):
    raw = (root / KEY_NAME).read_bytes()
    if len(raw) != 32:
        raise ValueError("invalid_key_file")
    return raw


def initialize(root):
    """Explicit lab-only initialization; never invoked by inspection."""
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError("lab_directory_missing_or_linked")
    key_file = root / KEY_NAME
    db_file = root / DB_NAME
    if key_file.exists() or db_file.exists():
        raise RuntimeError("lab_already_initialized")
    # Only initialize in a dedicated, empty lab. Caller must be NFValidatorSvc.
    created_key = False
    try:
        with key_file.open("xb") as handle:
            handle.write(secrets.token_bytes(32))
        created_key = True
        with closing(sqlite3.connect(db_file)) as db:
            with db:
                db.execute("""CREATE TABLE probe_lifecycle (
                    name TEXT PRIMARY KEY, image_id TEXT NOT NULL,
                    container_id TEXT, phase TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )""")
        return "LAB_INITIALIZED"
    except Exception:
        # Avoid removing any database after an unexpected partial commit.
        if created_key and not db_file.exists():
            key_file.unlink(missing_ok=True)
        raise


def inspection(root):
    """Read pre-existing SQLite only; no Docker and no automatic cleanup."""
    db_path = root / DB_NAME
    if root.is_symlink() or not root.is_dir() or db_path.is_symlink() or not db_path.is_file():
        raise RuntimeError("invalid_storage_path")
    uri = db_path.absolute().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=2)) as db:
        if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise RuntimeError("database_integrity_failed")
        # No Docker discovery is attempted; unresolved records stay unknown.
        count = db.execute("SELECT COUNT(*) FROM probe_lifecycle WHERE phase != 'removed'").fetchone()[0]
    if type(count) is not int or count < 0:
        raise RuntimeError("invalid_record_count")
    return {"schema_version": 1, "report_type": "m05_isolated_lab_recovery",
            "read_only": True, "recovery_required": bool(count),
            "unresolved_count": count, "recovery_status": "unknown" if count else "none",
            "automatic_cleanup_allowed": False, "safe_to_retry": False,
            "docker_contacted": False}


def make_envelope(key, *, now=None, nonce=None):
    if now is None:
        now = int(time.time())
    if nonce is None:
        nonce = secrets.token_hex(16)
    request = {"version": 1, "operation": "recovery.inspect"}
    unsigned = {"version": 1, "timestamp": now, "nonce": nonce, "request": request}
    mac = hmac.new(key, _encode(unsigned), hashlib.sha256).hexdigest()
    return _encode({**unsigned, "mac": mac})


def failure():
    return _encode({"version": 1, "operation": "recovery.inspect", "success": False,
                    "error": "isolated_inspection_failed", "recovery_status": "unknown",
                    "safe_to_retry": False})


def process(payload, root, *, now=None):
    """Authenticate before any journal access. One request per process."""
    try:
        if type(payload) is not bytes or not 0 < len(payload) <= MAX_INPUT:
            raise ValueError("invalid_input_size")
        if now is None:
            now = int(time.time())
        data = json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=_invalid_constant)
        if type(data) is not dict or set(data) != {"version", "timestamp", "nonce", "request", "mac"}:
            raise ValueError("invalid_envelope")
        request = data["request"]
        if (type(data["version"]) is not int or data["version"] != 1
                or type(data["timestamp"]) is not int
                or abs(now - data["timestamp"]) > MAX_AGE
                or type(data["nonce"]) is not str or len(data["nonce"]) != 32
                or any(c not in "0123456789abcdef" for c in data["nonce"])
                or type(data["mac"]) is not str or len(data["mac"]) != 64
                or any(c not in "0123456789abcdef" for c in data["mac"])
                or type(request) is not dict
                or request != {"version": 1, "operation": "recovery.inspect"}
                or type(request.get("version")) is not int):
            raise ValueError("invalid_envelope")
        unsigned = {key: data[key] for key in ("version", "timestamp", "nonce", "request")}
        key = _read_key(root)
        expected = hmac.new(key, _encode(unsigned), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, data["mac"]):
            raise ValueError("invalid_mac")
        result = _encode({"version": 1, "operation": "recovery.inspect", "success": True,
                          "report": inspection(root)})
        if len(result) > MAX_OUTPUT:
            raise RuntimeError("oversize_reply")
        return result
    except Exception:
        return failure()


def serve_stdio_once(root, incoming, outgoing):
    """Single bounded binary stdin frame; no listener, no persistent replay cache."""
    header = incoming.read(4)
    if len(header) != 4:
        response = failure()
    else:
        (length,) = struct.unpack("!I", header)
        if not 0 < length <= MAX_INPUT:
            response = failure()
        else:
            body = incoming.read(length)
            response = process(body, root) if len(body) == length else failure()
    outgoing.write(struct.pack("!I", len(response)) + response)
    outgoing.flush()


def main(argv):
    if len(argv) != 2 or argv[1] not in {"--initialize-lab", "--selftest", "--stdio-once"}:
        print("Usage: m05_isolated_worker.py --initialize-lab | --selftest | --stdio-once", file=sys.stderr)
        return 2
    mode = argv[1]
    try:
        if mode == "--initialize-lab":
            print(initialize(LAB))
        elif mode == "--selftest":
            key = _read_key(LAB)
            report = json.loads(process(make_envelope(key), LAB))
            print(json.dumps(report, indent=2))
            return 0 if report.get("success") is True else 1
        else:
            serve_stdio_once(LAB, sys.stdin.buffer, sys.stdout.buffer)
        return 0
    except Exception:
        print("M05_LAB_OPERATION_FAILED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
