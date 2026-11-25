# M05 Windows service identity: read-only preflight

Base commit: `8704d96` on `feat/validator-service-boundary`.

## Purpose

Check the proposed *separate* low-privilege service identity and a dedicated storage-lab destination without mutating Windows. The existing `%LOCALAPPDATA%\NEURALFORGE\validator` journal and lock remain untouched. The script is a plan/audit, **not** an installer.

## Usage (normal, non-administrator CMD)

```cmd
call verify_m05_isolation_plan.cmd
```

With a **pre-existing, separately created** low-privilege Windows account, optionally inspect its SID and direct local administrator membership:

```cmd
powershell -NoProfile -ExecutionPolicy Bypass -File tools\plan_m05_service_isolation.ps1 -ServiceAccount "COMPUTERNAME\account" -Json
```

Replace the quoted identity with the actual account name. Do not create an account or alter ACLs until the threat model and account ownership have been reviewed. Never put credentials in these scripts or Git.

## Intended security boundary (not implemented here)

- Dedicated **non-admin** Windows service identity distinct from the interactive development user.
- Service-owned data directory with deliberate explicit ACLs for service SID, SYSTEM and necessary administrators; remove broad write rights; verify **effective** permissions and group membership under separate tokens.
- Separate trusted local IPC with Windows peer identity/access checks. HMAC alone does not create an OS security boundary.
- Protect application code and key material against writes by untrusted identities; handle journal, lock, -wal and -shm creation correctly.
- Treat service restarts and clock rollback as replay risks. The existing nonce guard is process-local and resets on restart.
- Validate negative access from another actual Windows standard-user token; repeat after reboot and failure recovery.
- Keep live Docker probes and untrusted-code execution disabled until independent review.

## Known limitations

This preflight does not demonstrate service isolation, account privilege, effective access, durable replay safety, named-pipe security, or recovery correctness. A local Administrator or SYSTEM can generally override ACLs. Parent access and reparse-point changes may invalidate assumptions. The proposed directory under ProgramData is a *future isolated test location*, not configured runtime storage.
