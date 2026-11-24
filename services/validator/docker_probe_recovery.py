
"""Read-only recovery assessments for persisted Docker probes.

Loads unresolved lifecycle records and compares them with
current Docker observations.

Never creates, starts, stops, removes, or modifies containers.
Never changes journal phases automatically.

An absent container is only absent at the time of inspection.
"""

from dataclasses import dataclass
from typing import Callable

from services.validator.docker_probe_journal import (
    ProbeJournal,
    ProbeRecord,
)
from services.validator.docker_probe_reconciliation import (
    ProbeDiscovery,
    reconcile_probe_presence,
)


@dataclass(frozen=True)
class RecoveryAssessment:
    record: ProbeRecord
    discovery: ProbeDiscovery


def assess_unresolved_probes(
    journal: ProbeJournal,
    executable: str,
    *,
    discover: Callable = reconcile_probe_presence,
    max_records: int = 1000,
) -> list[RecoveryAssessment]:
    """Assess persisted unfinished probes without mutations.

    These observations must not be treated as automatic
    authorization to remove containers or mark them removed.
    """

    if not isinstance(journal, ProbeJournal):
        raise ValueError("invalid_probe_journal")

    if not isinstance(max_records, int) or isinstance(
        max_records, bool
    ) or not 1 <= max_records <= 1000:
        raise ValueError("invalid_recovery_limit")

    if not callable(discover):
        raise ValueError("invalid_recovery_discovery")

    records = journal.unresolved()

    if len(records) > max_records:
        raise RuntimeError("recovery_record_limit_exceeded")

    assessments = []

    for record in records:
        try:
            result = discover(
                executable=executable,
                container_name=record.name,
                expected_image_id=record.image_id,
                expected_container_id=record.container_id,
            )

            if not isinstance(result, ProbeDiscovery):
                result = ProbeDiscovery("uncertain")

            if result.status not in {
                "present_owned",
                "absent_at_check",
                "uncertain",
                "mismatch",
            }:
                result = ProbeDiscovery("uncertain")

            # Preserve journal identity even if a future
            # discovery implementation returns conflicting
            # or incorrectly classified evidence.
            if result.status == "present_owned":
                if (
                    result.container_id is None
                    or (
                        record.container_id is not None
                        and result.container_id
                        != record.container_id
                    )
                ):
                    result = ProbeDiscovery("uncertain")

        except Exception:
            # A failed Docker read is not evidence of absence.
            result = ProbeDiscovery("uncertain")

        assessments.append(
            RecoveryAssessment(
                record=record,
                discovery=result,
            )
        )

    return assessments
