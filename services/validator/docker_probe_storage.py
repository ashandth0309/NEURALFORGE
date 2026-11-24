
"""Persistent storage validation for fixed Docker probes.

Opens an existing per-user SQLite journal.

Does not create an arbitrary database, clear unresolved
records, execute Docker commands, or change permissions.

Filesystem checks are defensive checks, not a complete
protection against concurrent path replacement.
"""

import os
import sqlite3
import stat
from pathlib import Path
from contextlib import closing
from services.validator.docker_probe_journal import ProbeJournal
from services.validator.docker_probe_lock import (
    exclusive_probe_lock,
)


DATABASE_FILENAME = "probe_lifecycle.sqlite3"


def _check_existing_path(path: Path, *, directory: bool):
    """Reject missing paths and directly visible links."""

    if path.is_symlink():
        raise RuntimeError("probe_storage_link_rejected")

    # Python 3.12+ provides an explicit junction check.
    is_junction = getattr(path, "is_junction", None)

    if callable(is_junction) and is_junction():
        raise RuntimeError("probe_storage_junction_rejected")

    try:
        mode = path.stat().st_mode
    except OSError as exc:
        raise RuntimeError("probe_storage_missing") from exc

    valid = (
        stat.S_ISDIR(mode)
        if directory
        else stat.S_ISREG(mode)
    )

    if not valid:
        raise RuntimeError("probe_storage_invalid_type")


def open_persistent_probe_journal() -> ProbeJournal:
    """Open and validate the existing local journal.

    The parent directory and database must already exist.
    Journal initialization is a separate administrative step.
    """

    local_appdata = os.environ.get("LOCALAPPDATA")

    if not local_appdata:
        raise RuntimeError("probe_storage_location_missing")

    root = Path(local_appdata).absolute()

    if not root.is_absolute():
        raise RuntimeError("probe_storage_location_invalid")

    directory = root / "NEURALFORGE" / "validator"
    database = directory / DATABASE_FILENAME
    lockfile = Path(str(database) + ".lock")

    # Check the relevant path hierarchy before opening.
    for item in (
        root,
        root / "NEURALFORGE",
        directory,
    ):
        _check_existing_path(item, directory=True)

    _check_existing_path(database, directory=False)

    if lockfile.exists() or lockfile.is_symlink():
        _check_existing_path(lockfile, directory=False)

    # Prevent cooperating NEURALFORGE processes from
    # concurrently changing this journal during preflight.
    with exclusive_probe_lock(database):
        # Read-only mode prevents SQLite from silently
        # creating a missing or replacement database.
        try:
            uri = database.as_uri() + "?mode=ro"

            with closing(sqlite3.connect(uri, uri=True)) as db:
                result = db.execute(
                    "PRAGMA quick_check"
                ).fetchone()

                if result != ("ok",):
                    raise RuntimeError(
                        "probe_storage_integrity_failed"
                    )

                # Validate the schema without changing it.
                db.execute(
                    """
                    SELECT name, image_id, container_id, phase
                    FROM probe_lifecycle
                    LIMIT 0
                    """
                )

        except sqlite3.DatabaseError as exc:
            raise RuntimeError(
                "probe_storage_database_invalid"
            ) from exc

        journal = ProbeJournal(database)

        # Ensure the journal can read its persisted state.
        journal.unresolved()

    return journal
