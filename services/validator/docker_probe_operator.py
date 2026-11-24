
"""Operator-only, read-only Docker recovery inspection.

Run with:
    python -m services.validator.docker_probe_operator

No Docker create/start/stop/remove commands are issued.
Unresolved records are never cleared automatically.
"""

import json
import sys

from services.validator.docker_executable import (
    resolve_docker_executable,
)
from services.validator.docker_probe_lock import (
    exclusive_probe_lock,
)
from services.validator.docker_probe_reconciliation import (
    ProbeDiscovery,
)
from services.validator.docker_probe_recovery import (
    assess_unresolved_probes,
)
from services.validator.docker_probe_report import (
    build_recovery_report,
)
from services.validator.docker_probe_storage import (
    open_persistent_probe_journal,
)


def inspect_persistent_recovery() -> dict:
    """Inspect persisted records without Docker mutations."""

    journal = open_persistent_probe_journal()

    # Serialize the assessment with cooperating probe
    # controllers, keeping the journal snapshot stable.
    with exclusive_probe_lock(journal.path):
        records = journal.unresolved()

        if not records:
            report = build_recovery_report([])
            report["docker_available"] = None
            return report

        executable = resolve_docker_executable()

        if executable is None:
            # Missing Docker cannot prove that any
            # previously requested container is absent.
            assessments = assess_unresolved_probes(
                journal,
                "",
                discover=lambda **kwargs: ProbeDiscovery(
                    "uncertain"
                ),
            )
        else:
            assessments = assess_unresolved_probes(
                journal,
                executable,
            )

        report = build_recovery_report(assessments)
        report["docker_available"] = executable is not None

        return report


def main() -> int:
    """Print one JSON report and return an exit status."""

    try:
        report = inspect_persistent_recovery()

        print(json.dumps(
            report,
            indent=2,
            sort_keys=True,
        ))

        # 0 = no unresolved records
        # 2 = recovery required
        return 2 if report["recovery_required"] else 0

    except Exception as exc:
        # Do not expose sensitive local filesystem
        # information in the default JSON error.
        print(json.dumps({
            "report_type": "docker_probe_recovery",
            "read_only": True,
            "error": "recovery_inspection_failed",
            "error_type": type(exc).__name__,
            "recovery_status": "unknown",
            "safe_to_retry": False,
        }), file=sys.stderr)

        return 1


if __name__ == "__main__":
    sys.exit(main())
