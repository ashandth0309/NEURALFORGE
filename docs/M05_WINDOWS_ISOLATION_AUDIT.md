# M05 Windows service identity and ACL audit — read-only batch

Base commit `0010aee` (`feat/validator-service-boundary`). This is a **diagnostic package**, not a completed secure deployment.

## Scope

- `tools/audit_m05_windows_acl.ps1` inventories NTFS owner, inheritance, ACE identities/rights, possible broad writable ACEs and reparse-point indicators for the journal directory, SQLite database, `.lock`, `-wal` and `-shm` files. The parent directory is included.
- `verify_m05_windows.cmd` runs the existing validator regression suite and then the read-only inventory. Does **not** create directories, change permissions, start services or connect to Docker.
- Findings are advisory: effective access must be independently tested using a different low-privilege Windows account. Absence of an alert is **not** evidence of security.

## Run from Windows CMD in the repository root

```bat
call verify_m05_windows.cmd
```

Run the audit alone, optionally with a service account that already exists (do **not** create one just to make the report pass):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\audit_m05_windows_acl.ps1 -ServiceAccount 'NT AUTHORITY\LocalService'
```

You can explicitly select the journal directory when your design moves it out of `LOCALAPPDATA`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\audit_m05_windows_acl.ps1 -JournalDirectory 'C:\ProgramData\NEURALFORGE\validator'
```

Caution: Do not treat `LocalService` as a ready-made authorized NEURALFORGE service identity. It is a shared OS account; service SIDs and an independently reviewed identity design are preferred. **Do not move existing journal files or reset ACLs without a backed-up migration and recovery plan.** Never paste access secrets or full identity inventories into public issue trackers.

## Security-relevant limitations and minimum acceptance gates

1. Specify Windows service principal, service SID, privileges, service lifetime and who may authenticate to IPC. Use a dedicated least-privilege identity, not the interactive user or Administrators.
2. Place the persistent journal under a service-controlled, protected directory (not a caller-writable `%LOCALAPPDATA%` tree). Protect parent directories, database, lock, WAL and SHM. Review read/write/delete/replace rights for *all* principals, including inherited ACEs, groups and service owner.
3. Add a protected Windows named-pipe transport or similarly OS-verified local IPC. Enforce caller token identity and per-connection timeouts/limits. HMAC alone does not supply a Windows security boundary; current replay guard is process-local and not restart-safe.
4. Validate effective access with separate Windows account sessions: unauthorized reads/writes/renames/removals must fail; authorized service must continue to work across restart and power loss.
5. Confirm log redaction, crash recovery, journal backup/restore, key provisioning, revocation and rotation. No credentials or keys in Git or diagnostic logs.
6. Perform controlled read-only Docker checks with real permissions and independent security review. Do not enable arbitrary-code execution or Docker mutation based on this audit.

## Suggested evidence to record for each gate

Who was the Windows principal? Which Windows build? What was the path and ACL inheritance? Was the denied-access test run under a *different token*? Were journaling and recovery cases exercised? What are the remaining unresolved findings?
