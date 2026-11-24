
"""Read-only reconciliation for Docker runtime probes.

Discovers a probe by its generated name and checks its
identity. Never starts, stops, or removes containers.

Results are point-in-time observations, not guarantees
against delayed Docker daemon operations.
"""

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from services.validator.bounded_capture import run_bounded
from services.validator.docker_probe_commands import (
    NAME_PATTERN,
    PROBE_LABEL_KEY,
)
from services.validator.image_identity import DIGEST_PATTERN


CONTAINER_ID_PATTERN = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class ProbeDiscovery:
    status: str
    container_id: str | None = None


def reconcile_probe_presence(
    executable: str,
    container_name: str,
    expected_image_id: str,
    expected_container_id: str | None = None,
    *,
    runner=run_bounded,
) -> ProbeDiscovery:
    """Inspect probe identity without performing mutations.

    Status:
      present_owned  - exact name, label and image match
      absent_at_check - no matching container in current list
      uncertain      - contradictory or unavailable evidence
      mismatch       - an inspected object fails identity checks
    """

    if (
        not isinstance(executable, str)
        or not Path(executable).is_absolute()
    ):
        raise ValueError("invalid_docker_executable")

    if (
        not isinstance(container_name, str)
        or NAME_PATTERN.fullmatch(container_name) is None
    ):
        raise ValueError("invalid_probe_container_name")

    if (
        not isinstance(expected_image_id, str)
        or DIGEST_PATTERN.fullmatch(expected_image_id) is None
    ):
        raise ValueError("invalid_expected_image_id")

    if expected_container_id is not None and (
        not isinstance(expected_container_id, str)
        or CONTAINER_ID_PATTERN.fullmatch(
            expected_container_id
        ) is None
    ):
        raise ValueError("invalid_expected_container_id")

    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("DOCKER_")
    }

    base = (
        executable,
        "--context",
        "desktop-linux",
    )

    inspect_command = (
        *base,
        "container",
        "inspect",
        "--format",
        "{{json .}}",
        container_name,
    )

    list_command = (
        *base,
        "ps",
        "-a",
        "--no-trunc",
        "--filter",
        f"name=^/{container_name}$",
        "--format",
        "{{.ID}}",
    )

    def invoke(command):
        return runner(
            list(command),
            env=environment,
            timeout_seconds=15,
            max_output_bytes=65536,
        )

    # Query both views. A failed inspect alone is not
    # sufficient proof that the container is absent.
    try:
        inspected = invoke(inspect_command)
        listed = invoke(list_command)
    except Exception:
        return ProbeDiscovery("uncertain")

    if listed.returncode != 0:
        return ProbeDiscovery("uncertain")

    try:
        listed_ids = [
            line.strip()
            for line in listed.stdout.decode(
                "ascii"
            ).splitlines()
            if line.strip()
        ]
    except UnicodeError:
        return ProbeDiscovery("uncertain")

    if any(
        CONTAINER_ID_PATTERN.fullmatch(item) is None
        for item in listed_ids
    ):
        return ProbeDiscovery("uncertain")

    if len(listed_ids) != len(set(listed_ids)):
        return ProbeDiscovery("uncertain")

    if inspected.returncode != 0:
        if listed_ids:
            return ProbeDiscovery("uncertain")

        return ProbeDiscovery("absent_at_check")

    try:
        metadata = json.loads(
            inspected.stdout.decode("utf-8")
        )
    except (ValueError, UnicodeError):
        return ProbeDiscovery("uncertain")

    if not isinstance(metadata, dict):
        return ProbeDiscovery("uncertain")

    found_id = metadata.get("Id")

    if (
        not isinstance(found_id, str)
        or CONTAINER_ID_PATTERN.fullmatch(found_id) is None
    ):
        return ProbeDiscovery("uncertain")

    # Contradictory inspect/list responses are not
    # sufficient evidence of reliable ownership.
    if listed_ids != [found_id]:
        return ProbeDiscovery("uncertain")

    config = metadata.get("Config")
    labels = (
        config.get("Labels")
        if isinstance(config, dict)
        else None
    )

    if (
        metadata.get("Name") != "/" + container_name
        or metadata.get("Image") != expected_image_id
        or not isinstance(labels, dict)
        or labels.get(PROBE_LABEL_KEY) != container_name
        or (
            expected_container_id is not None
            and found_id != expected_container_id
        )
    ):
        return ProbeDiscovery("mismatch", found_id)

    return ProbeDiscovery("present_owned", found_id)
