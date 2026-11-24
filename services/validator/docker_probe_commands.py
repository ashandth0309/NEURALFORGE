
"""Build fixed Docker runtime-probe commands.

This module never launches Docker or containers.
"""

import re
from pathlib import Path

from services.validator.image_identity import DIGEST_PATTERN
from services.validator.isolation import (
    IsolationPolicy,
    validate_isolation_policy,
)


NAME_PATTERN = re.compile(r"neuralforge-probe-[0-9a-f]{24}")
PROBE_LABEL_KEY = "com.neuralforge.probe.name"

# Fixed diagnostic for the currently supported
# Linux amd64 / cgroup v1 Node.js probe image.
PROBE_SCRIPT = r"""
const fs = require('fs');
const os = require('os');

const raw = fs.readFileSync('/proc/self/status', 'utf8');
const fields = {};

for (const line of raw.split('\n')) {
  const index = line.indexOf(':');
  if (index > 0) {
    fields[line.slice(0, index)] =
      line.slice(index + 1).trim();
  }
}

const status = {};
for (const key of [
  'Seccomp',
  'Seccomp_filters',
  'CapEff',
  'CapBnd',
  'NoNewPrivs'
]) {
  status[key] = fields[key] ?? null;
}

let filesystem_write_error = null;

try {
  fs.writeFileSync(
    '/tmp/neuralforge-runtime-probe',
    'probe'
  );
  filesystem_write_error = 'WRITE_SUCCEEDED';
} catch (error) {
  filesystem_write_error = error.code ?? 'UNKNOWN';
}

function read(path) {
  return fs.readFileSync(path, 'utf8').trim();
}

console.log(JSON.stringify({
  uid: process.getuid(),
  gid: process.getgid(),
  status,
  interfaces: Object.keys(os.networkInterfaces()),
  filesystem_write_error,
  memory: read(
    '/sys/fs/cgroup/memory/memory.limit_in_bytes'
  ),
  cpuQuota: read(
    '/sys/fs/cgroup/cpu/cpu.cfs_quota_us'
  ),
  cpuPeriod: read(
    '/sys/fs/cgroup/cpu/cpu.cfs_period_us'
  ),
  pids: read(
    '/sys/fs/cgroup/pids/pids.max'
  )
}));
""".strip()


def build_probe_commands(
    policy: IsolationPolicy,
    image_id: str,
    executable: str,
    container_name: str,
) -> tuple[tuple[str, ...], ...]:
    """Return create, start and forced-removal commands."""

    validate_isolation_policy(policy)

    if (
        not isinstance(image_id, str)
        or DIGEST_PATTERN.fullmatch(image_id) is None
    ):
        raise ValueError("invalid_probe_image_id")

    if (
        not isinstance(container_name, str)
        or NAME_PATTERN.fullmatch(container_name) is None
    ):
        raise ValueError("invalid_probe_container_name")

    if (
        not isinstance(executable, str)
        or not executable
        or not Path(executable).is_absolute()
    ):
        raise ValueError("invalid_docker_executable")


    base = (
        executable,
        "--context",
        "desktop-linux",
    )

    create = (
        *base,
        "create",
        "--cgroupns",
        "private",
        "--name",
        container_name,
        "--label",
        f"{PROBE_LABEL_KEY}={container_name}",
        "--pull",
        "never",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges=true",
        "--security-opt",
        "seccomp=builtin",
        "--memory",
        f"{policy.memory_mb}m",
        "--memory-swap",
        f"{policy.memory_mb}m",
        "--cpus",
        str(policy.cpu_count),
        "--pids-limit",
        str(policy.pids_limit),
        "--user",
        policy.user,
        "--init",
        "--entrypoint",
        "/usr/local/bin/node",
        image_id,
        "-e",
        PROBE_SCRIPT,
    )


    start = (
        *base,
        "start",
        "--attach",
        container_name,
    )

    cleanup = (
        *base,
        "rm",
        "--force",
        container_name,
    )


    inspect = (
        *base,
        "inspect",
        "--format",
        "{{json .}}",
        container_name,
    )

    return create, inspect, start, cleanup
