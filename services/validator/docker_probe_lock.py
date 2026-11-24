
"""OS-backed exclusive lock for a Docker probe journal.

Serializes cooperating processes using the same journal path.

The lock is released by the operating system when the
owning process exits, including after most process crashes.

This does not terminate Docker daemon operations or
protect against processes that ignore this lock.
"""

import os
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def exclusive_probe_lock(database_path):
    """Acquire a nonblocking exclusive lock for one journal."""

    if not isinstance(database_path, (str, Path)):
        raise ValueError("invalid_probe_lock_path")

    path = Path(database_path).resolve()

    if path.is_dir():
        raise ValueError("invalid_probe_lock_path")

    if not path.parent.is_dir():
        raise ValueError("probe_lock_directory_missing")

    lock_path = Path(str(path) + ".lock")

    # The lock file remains on disk. The OS lock, not
    # the file's existence, determines ownership.
    with open(lock_path, "a+b") as handle:

        # Windows byte-range locking requires an
        # existing byte in the file.
        handle.seek(0, os.SEEK_END)

        if handle.tell() == 0:
            handle.write(b"\x00")
            handle.flush()

        handle.seek(0)

        acquired = False

        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(
                    handle.fileno(),
                    msvcrt.LK_NBLCK,
                    1,
                )
            except OSError as exc:
                raise RuntimeError(
                    "docker_probe_lock_unavailable"
                ) from exc

            acquired = True

            try:
                yield
            finally:
                if acquired:
                    handle.seek(0)
                    msvcrt.locking(
                        handle.fileno(),
                        msvcrt.LK_UNLCK,
                        1,
                    )

        elif os.name == "posix":
            import fcntl

            try:
                fcntl.flock(
                    handle.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
            except OSError as exc:
                raise RuntimeError(
                    "docker_probe_lock_unavailable"
                ) from exc

            acquired = True

            try:
                yield
            finally:
                if acquired:
                    fcntl.flock(
                        handle.fileno(),
                        fcntl.LOCK_UN,
                    )

        else:
            raise RuntimeError(
                "unsupported_probe_lock_platform"
            )
