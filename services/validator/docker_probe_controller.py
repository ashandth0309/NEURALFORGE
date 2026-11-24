
"""Controlled Docker runtime probe lifecycle.

Runs only the fixed diagnostic defined by docker_probe_commands.
Does not authorize execution of untrusted project code.

Docker daemon operations may outlive a timed-out CLI.
Cleanup uncertainty always causes failure.
"""

import json
import os
import re
import secrets

from services.validator.bounded_capture import (
    BoundedProcessTimeout,
    run_bounded,
)
from services.validator.docker_executable import (
    resolve_docker_executable,
)
from services.validator.docker_inspect import (
    inspect_approved_image,
)
from services.validator.docker_probe_commands import (
    PROBE_LABEL_KEY,
    build_probe_commands,
)
from services.validator.docker_probe_identity import (
    verify_probe_container,
)
from services.validator.docker_probe_journal import ProbeJournal
from services.validator.isolation import IsolationPolicy
from services.validator.runtime_probe import parse_runtime_probe


CONTAINER_ID_PATTERN = re.compile(r"[0-9a-f]{64}")

CLI_TIMEOUT = 15
CLI_OUTPUT_LIMIT = 65536


def run_fixed_docker_probe(
    policy: IsolationPolicy,
    approved_images: frozenset[str],
    expected_image_id: str,
    *,
    journal: ProbeJournal | None = None,
):
    """Run the fixed diagnostic with conservative cleanup.

    Journal records reflect controller observations.
    They are not independent Docker security attestations.

    The optional journal preserves existing mock-test
    compatibility. Production integration must require it.
    """

    identity = inspect_approved_image(
        policy,
        approved_images,
        expected_image_id=expected_image_id,
    )

    executable = resolve_docker_executable()

    if executable is None:
        raise RuntimeError("docker_unavailable")

    name = "neuralforge-probe-" + secrets.token_hex(12)

    journal_phase = None

    def advance_journal(expected_phase, next_phase, **kwargs):
        nonlocal journal_phase

        if journal is None:
            return

        journal.advance(
            name,
            expected_phase,
            next_phase,
            **kwargs,
        )

        # Change local state only after the database
        # transaction completes successfully.
        journal_phase = next_phase

    def record_uncertain():
        """Persist unresolved status, failing closed on errors."""

        if journal is None:
            return

        if journal_phase in (
            None,
            "cleanup_unconfirmed",
            "removed",
        ):
            return

        try:
            advance_journal(
                journal_phase,
                "cleanup_unconfirmed",
            )
        except Exception as exc:
            raise RuntimeError(
                "docker_probe_journal_unconfirmed"
            ) from exc

    # The initial record must exist before Docker
    # creation can be requested.
    if journal is not None:
        journal.prepare(name, identity.image_id)
        journal_phase = "prepared"

    create, inspect, start, cleanup = build_probe_commands(
        policy=policy,
        image_id=identity.image_id,
        executable=executable,
        container_name=name,
    )

    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("DOCKER_")
    }

    def invoke(command, timeout=CLI_TIMEOUT):
        return run_bounded(
            list(command),
            env=environment,
            timeout_seconds=timeout,
            max_output_bytes=CLI_OUTPUT_LIMIT,
        )

    def inspect_metadata(command):
        result = invoke(command)

        if result.returncode != 0:
            raise RuntimeError(
                "docker_probe_inspect_failed"
            )

        try:
            metadata = json.loads(result.stdout)
        except (ValueError, UnicodeError) as exc:
            raise RuntimeError(
                "docker_probe_invalid_metadata"
            ) from exc

        if not isinstance(metadata, dict):
            raise RuntimeError(
                "docker_probe_invalid_metadata"
            )

        return metadata

    container_id = None
    ownership_verified = False
    create_attempted = False
    create_outcome_uncertain = False

    try:
        # Persist intent before contacting Docker.
        if journal is not None:
            advance_journal(
                "prepared",
                "create_requested",
            )

        create_attempted = True

        try:
            created = invoke(create)
        except (BoundedProcessTimeout, OSError):
            create_outcome_uncertain = True
            raise

        if created.returncode != 0:
            create_outcome_uncertain = True
            raise RuntimeError(
                "docker_probe_create_failed"
            )

        try:
            candidate = created.stdout.decode(
                "ascii"
            ).strip()
        except UnicodeError as exc:
            create_outcome_uncertain = True
            raise RuntimeError(
                "docker_probe_invalid_container_id"
            ) from exc

        if CONTAINER_ID_PATTERN.fullmatch(candidate) is None:
            create_outcome_uncertain = True
            raise RuntimeError(
                "docker_probe_invalid_container_id"
            )

        container_id = candidate

        # Persist the Docker ID before inspection.
        if journal is not None:
            advance_journal(
                "create_requested",
                "created",
                container_id=container_id,
            )

        # Use the exact container ID for all
        # subsequent Docker lifecycle operations.
        inspect_id = (
            *inspect[:-1],
            container_id,
        )

        start_id = (
            *start[:-1],
            container_id,
        )

        metadata = inspect_metadata(inspect_id)

        # Establish ownership before either starting
        # or force-removing the container.
        config = metadata.get("Config")

        labels = (
            config.get("Labels")
            if isinstance(config, dict)
            else None
        )

        if (
            metadata.get("Id") != container_id
            or metadata.get("Name") != "/" + name
            or not isinstance(labels, dict)
            or labels.get(PROBE_LABEL_KEY) != name
        ):
            raise RuntimeError(
                "docker_probe_ownership_mismatch"
            )

        ownership_verified = True

        # Confirm the fixed diagnostic command and
        # the complete required isolation policy.
        verify_probe_container(
            metadata,
            policy=policy,
            expected_image_id=identity.image_id,
            expected_name=name,
            expected_container_id=container_id,
        )

        if journal is not None:
            advance_journal(
                "created",
                "verified",
            )

        # This phase means start was REQUESTED,
        # not that execution has been confirmed.
        if journal is not None:
            advance_journal(
                "verified",
                "started",
            )

        # Execute only the fixed diagnostic.
        started = invoke(
            start_id,
            timeout=policy.timeout_seconds,
        )

        if started.returncode != 0:
            raise RuntimeError(
                "docker_probe_start_failed"
            )

        # Inspect Docker's reported final state.
        finished = inspect_metadata(inspect_id)

        if (
            finished.get("Id") != container_id
            or finished.get("Image") != identity.image_id
            or finished.get("Name") != "/" + name
        ):
            raise RuntimeError(
                "docker_probe_identity_changed"
            )

        finished_config = finished.get("Config")

        finished_labels = (
            finished_config.get("Labels")
            if isinstance(finished_config, dict)
            else None
        )

        if (
            not isinstance(finished_labels, dict)
            or finished_labels.get(PROBE_LABEL_KEY) != name
        ):
            raise RuntimeError(
                "docker_probe_ownership_changed"
            )

        state = finished.get("State")

        if (
            not isinstance(state, dict)
            or state.get("Status") != "exited"
            or state.get("Running") is not False
            or type(state.get("ExitCode")) is not int
            or state["ExitCode"] != 0
        ):
            raise RuntimeError(
                "docker_probe_exit_failed"
            )

        # Runtime observations must match policy.
        evidence = parse_runtime_probe(
            started.stdout,
            policy,
        )

        return evidence

    finally:
        if create_attempted:
            # Never delete a container whose ownership
            # was not verified.
            if not ownership_verified:
                record_uncertain()

                raise RuntimeError(
                    "docker_probe_cleanup_unconfirmed"
                )

            remove_command = (
                *cleanup[:-1],
                container_id,
            )

            try:
                removed = invoke(remove_command)

                if removed.returncode != 0:
                    raise RuntimeError(
                        "docker_probe_remove_failed"
                    )

                # Confirm Docker can answer a query and
                # currently does not list this exact ID.
                list_command = (
                    executable,
                    "--context",
                    "desktop-linux",
                    "ps",
                    "-a",
                    "--no-trunc",
                    "--filter",
                    f"id={container_id}",
                    "--format",
                    "{{.ID}}",
                )

                listed = invoke(list_command)

                if (
                    listed.returncode != 0
                    or listed.stdout.strip()
                ):
                    raise RuntimeError(
                        "docker_probe_still_present"
                    )

            except Exception as exc:
                record_uncertain()

                raise RuntimeError(
                    "docker_probe_cleanup_unconfirmed"
                ) from exc

            # A previously ambiguous create cannot
            # be retroactively declared safe merely
            # because one listing is empty.
            if create_outcome_uncertain:
                record_uncertain()

                raise RuntimeError(
                    "docker_probe_cleanup_unconfirmed"
                )

            # A successful removal should only be
            # recorded from an appropriate journal phase.
            if journal is not None:
                if journal_phase in ("verified", "started"):
                    try:
                        advance_journal(
                            journal_phase,
                            "removed",
                        )
                    except Exception as exc:
                        raise RuntimeError(
                            "docker_probe_journal_unconfirmed"
                        ) from exc
                else:
                    record_uncertain()

                    raise RuntimeError(
                        "docker_probe_cleanup_unconfirmed"
                    )
