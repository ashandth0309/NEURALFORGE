
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
from services.validator.isolation import IsolationPolicy
from services.validator.runtime_probe import parse_runtime_probe


CONTAINER_ID_PATTERN = re.compile(r"[0-9a-f]{64}")

CLI_TIMEOUT = 15
CLI_OUTPUT_LIMIT = 65536


def run_fixed_docker_probe(
    policy: IsolationPolicy,
    approved_images: frozenset[str],
    expected_image_id: str,
):
    """Perform a fixed probe with explicit cleanup checks.

    The returned evidence represents observed probe behavior.
    It is not an authorization token or security attestation.
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
        create_attempted = True


        try:
            created = invoke(create)
        except (BoundedProcessTimeout, OSError):
            # The Docker daemon may have received the
            # create request even if the CLI failed.
            create_outcome_uncertain = True
            raise


        if created.returncode != 0:
            raise RuntimeError(
                "docker_probe_create_failed"
            )

        try:
            candidate = created.stdout.decode(
                "ascii"
            ).strip()
        except UnicodeError as exc:
            raise RuntimeError(
                "docker_probe_invalid_container_id"
            ) from exc

        if CONTAINER_ID_PATTERN.fullmatch(candidate) is None:
            raise RuntimeError(
                "docker_probe_invalid_container_id"
            )

        container_id = candidate

        # Use the Docker container ID instead of
        # its name for subsequent operations.
        inspect_id = (
            *inspect[:-1],
            container_id,
        )

        start_id = (
            *start[:-1],
            container_id,
        )

        # Verify the stopped container's identity
        # and requested isolation configuration.

        metadata = inspect_metadata(inspect_id)

        # Establish ownership before any automatic
        # force-removal operation is permitted.

        # Require the exact container ID, name,
        # and ownership label before starting or
        # force-removing this probe.
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


        verify_probe_container(

            metadata,
            policy=policy,
            expected_image_id=identity.image_id,
            expected_name=name,
            expected_container_id=container_id,
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

        # Inspect the completed container.
        finished = inspect_metadata(inspect_id)

        if (
            finished.get("Id") != container_id
            or finished.get("Image") != identity.image_id
        ):
            raise RuntimeError(
                "docker_probe_identity_changed"
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

        # Parse and validate observed security controls.
        evidence = parse_runtime_probe(
            started.stdout,
            policy,
        )

        return evidence


    finally:
        if create_attempted:
            # Never force-remove a container until both
            # its exact ID and generated name are verified.
            #
            # If creation failed or inspection was unavailable,
            # ownership remains uncertain. A separate recovery
            # process must reconcile that container safely.
            if not ownership_verified:
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

                # Verify Docker responds successfully and
                # does not list the exact container ID.
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
                raise RuntimeError(
                    "docker_probe_cleanup_unconfirmed"
                ) from exc

            # Do not report success after any ambiguous
            # Docker creation outcome.
            if create_outcome_uncertain:
                raise RuntimeError(
                    "docker_probe_cleanup_unconfirmed"
                )
