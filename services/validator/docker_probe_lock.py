
"""OS-backed exclusive lock for a Docker probe journal.

Serializes cooperating processes using the same journal path.

The lock is released by the operating system when the
owning process exits, including after most process crashes.

This does not terminate Docker daemon operations or
protect against processes that ignore this lock.
"""

import os
import stat
from contextlib import contextmanager
from pathlib import Path


def _assert_lock_identity(lock_path: Path, handle) -> None:
    """Check that the pathname refers to the opened lock file.

    This is a point-in-time check. It is not a substitute
    for OS-enforced handle or directory protection.
    """

    try:
        if lock_path.is_symlink():
            raise RuntimeError("docker_probe_lock_identity_changed")

        is_junction = getattr(lock_path, "is_junction", None)

        if callable(is_junction) and is_junction():
            raise RuntimeError("docker_probe_lock_identity_changed")

        opened = os.fstat(handle.fileno())
        named = os.stat(lock_path, follow_symlinks=False)

    except OSError as exc:
        raise RuntimeError(
            "docker_probe_lock_identity_unavailable"
        ) from exc

    if (
        not stat.S_ISREG(opened.st_mode)
        or not stat.S_ISREG(named.st_mode)
        or not opened.st_ino
        or not named.st_ino
        or (opened.st_dev, opened.st_ino)
        != (named.st_dev, named.st_ino)
    ):
        raise RuntimeError(
            "docker_probe_lock_identity_changed"
        )

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
                _assert_lock_identity(lock_path, handle)
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
                _assert_lock_identity(lock_path, handle)
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
