
"""Persistent entry point for NEURALFORGE's fixed Docker diagnostic.

Uses the configured, existing SQLite lifecycle journal.
Does not accept a caller-supplied journal or database path.

Importing this module never executes Docker commands.
This diagnostic does not authorize untrusted project code.
"""

from services.validator.docker_probe_controller import (
    run_fixed_docker_probe,
)
from services.validator.docker_probe_storage import (
    open_persistent_probe_journal,
)
from services.validator.isolation import IsolationPolicy


def run_persistent_fixed_docker_probe(
    policy: IsolationPolicy,
    approved_images: frozenset[str],
    expected_image_id: str,
):
    """Run the fixed diagnostic using validated persistent storage.

    Storage validation must complete before the controller
    is invoked. The controller independently enforces its
    exclusive lock and unresolved-record preflight.
    """
    journal = open_persistent_probe_journal()

    return run_fixed_docker_probe(
        policy,
        approved_images,
        expected_image_id,
        journal=journal,
    )
