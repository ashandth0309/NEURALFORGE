
"""Structured, read-only Docker probe recovery reporting.

Produces a JSON-serializable report from existing recovery
assessments. Does not contact Docker or modify SQLite.

A point-in-time observation never authorizes automatic
cleanup or clearing an unresolved journal record.
"""

from services.validator.docker_probe_recovery import (
    RecoveryAssessment,
)


VALID_STATUSES = frozenset({
    "present_owned",
    "absent_at_check",
    "mismatch",
    "uncertain",
})


def build_recovery_report(
    assessments: list[RecoveryAssessment],
) -> dict:
    """Convert recovery assessments to an operator report."""

    if not isinstance(assessments, list):
        raise ValueError("invalid_recovery_assessments")

    records = []

    for assessment in assessments:
        if not isinstance(assessment, RecoveryAssessment):
            raise ValueError("invalid_recovery_assessment")

        record = assessment.record
        discovery = assessment.discovery

        status = discovery.status

        if status not in VALID_STATUSES:
            status = "uncertain"

        records.append({
            "name": record.name,
            "phase": record.phase,
            "expected_image_id": record.image_id,
            "recorded_container_id": record.container_id,
            "discovery_status": status,
            "discovered_container_id": (
                discovery.container_id
                if status == "present_owned"
                else None
            ),
            "requires_manual_review": True,
            "automatic_cleanup_allowed": False,
            "safe_to_retry": False,
        })

    return {
        "schema_version": 1,
        "report_type": "docker_probe_recovery",
        "read_only": True,
        "unresolved_count": len(records),
        "recovery_required": bool(records),
        "automatic_cleanup_allowed": False,
        "records": records,
    }
