
"""Validate recovery reports before returning them to callers.

Pure data validation. No filesystem or Docker operations.
"""

VALID_DISCOVERY_STATUSES = frozenset({
    "present_owned",
    "absent_at_check",
    "mismatch",
    "uncertain",
})

REQUIRED_FIELDS = frozenset({
    "schema_version",
    "report_type",
    "read_only",
    "automatic_cleanup_allowed",
    "recovery_required",
    "unresolved_count",
    "records",
})

RECORD_FIELDS = frozenset({
    "name",
    "phase",
    "expected_image_id",
    "recorded_container_id",
    "discovery_status",
    "discovered_container_id",
    "requires_manual_review",
    "automatic_cleanup_allowed",
    "safe_to_retry",
})


def validate_recovery_report(report: object) -> None:
    """Reject structurally invalid or contradictory reports."""

    if type(report) is not dict:
        raise ValueError("invalid_recovery_report")

    keys = frozenset(report)

    if not REQUIRED_FIELDS.issubset(keys):
        raise ValueError("invalid_recovery_report")

    if keys - REQUIRED_FIELDS - {"docker_available"}:
        raise ValueError("invalid_recovery_report")

    if (
        type(report["schema_version"]) is not int
        or report["schema_version"] != 1
        or report["report_type"] != "docker_probe_recovery"
        or report["read_only"] is not True
        or report["automatic_cleanup_allowed"] is not False
    ):
        raise ValueError("invalid_recovery_report")

    if "docker_available" in report:
        if report["docker_available"] is not None and (
            type(report["docker_available"]) is not bool
        ):
            raise ValueError("invalid_recovery_report")

    records = report["records"]

    if type(records) is not list:
        raise ValueError("invalid_recovery_report")

    if (
        type(report["unresolved_count"]) is not int
        or report["unresolved_count"] != len(records)
        or type(report["recovery_required"]) is not bool
        or report["recovery_required"] != bool(records)
    ):
        raise ValueError("invalid_recovery_report")

    for record in records:
        if (
            type(record) is not dict
            or frozenset(record) != RECORD_FIELDS
        ):
            raise ValueError("invalid_recovery_record")

        if (
            type(record["name"]) is not str
            or not record["name"]
            or type(record["phase"]) is not str
            or not record["phase"]
            or type(record["expected_image_id"]) is not str
            or not record["expected_image_id"]
        ):
            raise ValueError("invalid_recovery_record")

        for field in (
            "recorded_container_id",
            "discovered_container_id",
        ):
            if record[field] is not None and (
                type(record[field]) is not str
                or not record[field]
            ):
                raise ValueError("invalid_recovery_record")

        if (
            type(record["discovery_status"]) is not str
            or record["discovery_status"]
            not in VALID_DISCOVERY_STATUSES
            or record["requires_manual_review"] is not True
            or record["automatic_cleanup_allowed"] is not False
            or record["safe_to_retry"] is not False
        ):
            raise ValueError("invalid_recovery_record")

        if (
            record["discovery_status"] != "present_owned"
            and record["discovered_container_id"] is not None
        ):
            raise ValueError("invalid_recovery_record")
