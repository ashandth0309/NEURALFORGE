
"""Bounded subprocess output capture.

Designed for trusted, fixed-command inspection utilities.

Limits captured stdout in memory and imposes a timeout.
Does not provide a complete process-tree sandbox.
"""

import subprocess
import threading


class BoundedOutputError(RuntimeError):
    """Subprocess output exceeded the configured limit."""


class BoundedProcessTimeout(RuntimeError):
    """Subprocess exceeded its execution deadline."""


def run_bounded(
    command: list[str],
    *,
    env: dict[str, str],
    timeout_seconds: float = 10,
    max_output_bytes: int = 65536,
) -> subprocess.CompletedProcess:
    """Execute a fixed command and capture bounded stdout.

    Stderr is discarded to avoid creating a second
    unbounded output channel.
    """

    if not command or not all(
        isinstance(part, str) and part
        for part in command
    ):
        raise ValueError("Invalid subprocess command")

    if timeout_seconds <= 0:
        raise ValueError("Invalid subprocess timeout")

    if max_output_bytes <= 0:
        raise ValueError("Invalid output limit")

    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=env,
        shell=False,
        close_fds=True,
    )

    chunks = []
    captured_bytes = 0
    state = {
        "oversized": False,
        "error": None,
    }

    def reader():
        nonlocal captured_bytes

        try:
            assert process.stdout is not None

            while True:
                chunk = process.stdout.read1(4096)

                if not chunk:
                    break

                if (
                    captured_bytes + len(chunk)
                    > max_output_bytes
                ):
                    state["oversized"] = True
                    return

                chunks.append(chunk)
                captured_bytes += len(chunk)

        except (OSError, ValueError) as exc:
            state["error"] = exc

    worker = threading.Thread(
        target=reader,
        name="neuralforge-bounded-reader",
        daemon=True,
    )

    try:
        worker.start()
        worker.join(timeout_seconds)

        if worker.is_alive():
            raise BoundedProcessTimeout(
                "subprocess_timeout"
            )

        if state["oversized"]:
            raise BoundedOutputError(
                "subprocess_output_too_large"
            )

        if state["error"] is not None:
            raise RuntimeError(
                "subprocess_output_read_failed"
            ) from state["error"]

        try:
            returncode = process.wait(timeout=2)
        except subprocess.TimeoutExpired as exc:
            raise BoundedProcessTimeout(
                "subprocess_timeout"
            ) from exc

        return subprocess.CompletedProcess(
            args=command,
            returncode=returncode,
            stdout=b"".join(chunks),
            stderr=b"",
        )

    finally:
        if process.poll() is None:
            process.kill()

        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass

        worker.join(timeout=1)

        if process.stdout is not None and not worker.is_alive():
            process.stdout.close()
