
"""Persistent lifecycle records for fixed Docker probes.

Stores probe identity and lifecycle state in SQLite.
Does not execute Docker commands or authorize cleanup.

Records describe controller-reported events; they are
not independent proof of Docker daemon state.
"""

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from contextlib import contextmanager
from services.validator.docker_probe_commands import (
    NAME_PATTERN,
)
from services.validator.image_identity import DIGEST_PATTERN


CONTAINER_ID_PATTERN = re.compile(r"[0-9a-f]{64}")

PHASES = frozenset({
    "prepared",
    "create_requested",
    "created",
    "verified",
    "started",
    "cleanup_unconfirmed",
    "removed",
})

TRANSITIONS = {
    "prepared": {"create_requested", "cleanup_unconfirmed"},
    "create_requested": {
        "created",
        "cleanup_unconfirmed",
    },
"created": {
    "verified",
    "cleanup_unconfirmed",
    "removed",
},
    "verified": {"started", "cleanup_unconfirmed", "removed"},
    "started": {"cleanup_unconfirmed", "removed"},
    "cleanup_unconfirmed": {"removed"},
    "removed": set(),
}


@dataclass(frozen=True)
class ProbeRecord:
    name: str
    image_id: str
    container_id: str | None
    phase: str


class ProbeJournal:
    """Simple transactional SQLite lifecycle journal."""

    def __init__(self, database_path: str | Path):
        path = Path(database_path)

        if str(path) in ("", ".") or path.is_dir():
            raise ValueError("invalid_journal_path")

        self.path = path



    @contextmanager
    def _connect(self, *, create: bool = False):
        """Open SQLite without implicit creation during normal use.

        Database creation is permitted only when explicitly
        requested by initialize().
        """

        uri = self.path.absolute().as_uri()
        mode = "rwc" if create else "rw"

        connection = sqlite3.connect(
            f"{uri}?mode={mode}",
            uri=True,
            timeout=5,
        )

        try:
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA busy_timeout=5000")

            with connection:
                yield connection

        finally:
            connection.close()



    def initialize(self):
        with self._connect(create=True) as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS probe_lifecycle (
                    name TEXT PRIMARY KEY,
                    image_id TEXT NOT NULL,
                    container_id TEXT,
                    phase TEXT NOT NULL,
                    created_at TEXT NOT NULL
                        DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL
                        DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def prepare(self, name: str, image_id: str):
        if (
            not isinstance(name, str)
            or NAME_PATTERN.fullmatch(name) is None
        ):
            raise ValueError("invalid_probe_name")

        if (
            not isinstance(image_id, str)
            or DIGEST_PATTERN.fullmatch(image_id) is None
        ):
            raise ValueError("invalid_image_id")

        with self._connect() as db:
            db.execute(
                """
                INSERT INTO probe_lifecycle
                    (name, image_id, container_id, phase)
                VALUES (?, ?, NULL, 'prepared')
                """,
                (name, image_id),
            )

    def get(self, name: str) -> ProbeRecord | None:
        if (
            not isinstance(name, str)
            or NAME_PATTERN.fullmatch(name) is None
        ):
            raise ValueError("invalid_probe_name")

        with self._connect() as db:
            row = db.execute(
                """
                SELECT name, image_id, container_id, phase
                FROM probe_lifecycle
                WHERE name = ?
                """,
                (name,),
            ).fetchone()

        return ProbeRecord(*row) if row else None

    def advance(
        self,
        name: str,
        expected_phase: str,
        next_phase: str,
        *,
        container_id: str | None = None,
    ):
        if (
            expected_phase not in PHASES
            or next_phase not in TRANSITIONS[expected_phase]
        ):
            raise ValueError("invalid_phase_transition")

        if container_id is not None and (
            not isinstance(container_id, str)
            or CONTAINER_ID_PATTERN.fullmatch(
                container_id
            ) is None
        ):
            raise ValueError("invalid_container_id")

        with self._connect() as db:
            current = db.execute(
                """
                SELECT phase, container_id
                FROM probe_lifecycle
                WHERE name = ?
                """,
                (name,),
            ).fetchone()

            if current is None:
                raise ValueError("probe_record_missing")

            phase, known_id = current

            if phase != expected_phase:
                raise ValueError("probe_phase_conflict")

            if (
                container_id is not None
                and known_id is not None
                and container_id != known_id
            ):
                raise ValueError("probe_container_id_conflict")

            effective_id = (
                container_id
                if container_id is not None
                else known_id
            )

            result = db.execute(
                """
                UPDATE probe_lifecycle
                SET phase = ?,
                    container_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE name = ? AND phase = ?
                """,
                (
                    next_phase,
                    effective_id,
                    name,
                    expected_phase,
                ),
            )

            if result.rowcount != 1:
                raise RuntimeError("probe_journal_update_failed")

    def unresolved(self) -> list[ProbeRecord]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT name, image_id, container_id, phase
                FROM probe_lifecycle
                WHERE phase != 'removed'
                ORDER BY created_at, name
                """
            ).fetchall()

        return [ProbeRecord(*row) for row in rows]
