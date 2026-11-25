# M05 isolated one-request worker — lab only

Starting Git ref `ea44ab8`. Adds a **standalone, standard-library-only** Python prototype that can run as `NFValidatorSvc` without importing the main repo. No Docker execution, no listener, no Windows service installation.

## Development verification (normal repo CMD)

Extract at repository root (new files only), then `call verify_m05_worker.cmd`. Ten new tests are expected, for **352 tests total** based on the verified baseline of 342. Tests use temporary directories; they never touch `C:\ProgramData`.

## Windows lab setup (explicit, manual; only after reviewing script)

1. Verify the existing ACL on `C:\ProgramData\NEURALFORGE-M05-IsolationLab`: only `NFValidatorSvc:Modify`, `Administrators:Full`, `SYSTEM:Full`. Do not change the existing `%LOCALAPPDATA%` journal.
2. In **elevated** PowerShell, create a separate **code** folder `C:\ProgramData\NEURALFORGE-M05-WorkerCode` if absent, restrict inheritance, grant `SYSTEM` and `Administrators` full control, grant `NFValidatorSvc` **ReadAndExecute only**. Never grant the worker write access to code. Inspect resulting ACL with `icacls`. Do not overwrite arbitrary existing files.
3. Copy `tools\m05_isolated_worker.py` from your repo into the protected code folder *as administrator*, after reviewing the diff. The worker must not be able to edit its own executable code.
4. In the `NFValidatorSvc` CMD window (created using `runas`), run `C:\Python312\python.exe C:\ProgramData\NEURALFORGE-M05-WorkerCode\m05_isolated_worker.py --initialize-lab`. This refuses initialization if either its **new** `probe_lifecycle.sqlite3` or HMAC key file already exists. This lab currently has only a prior disposable `m05_test.sqlite3`, which is unaffected.
5. Under the same service identity run `C:\Python312\python.exe C:\ProgramData\NEURALFORGE-M05-WorkerCode\m05_isolated_worker.py --selftest`. Confirm an empty read-only report.
6. In the normal non-elevated CMD verify attempts to open both the new journal and the key fail with access denied. Never display the key's bytes or paste them into chat.

## Important limitations and review gates

- **Not a real Windows service**; `runas` starts an interactive process, not a Service Control Manager service.
- `--stdio-once` is a one-shot framed *stdio demonstration*, not an authenticated OS IPC transport or pipe with verified peer identity; do not expose it to untrusted callers.
- Replay protection is **not durable** in this one-shot worker: the HMAC+time-window envelope could be replayed by a caller holding an authorized key. Here the key exists only in the service-owned lab as a single-identity selftest.
- Do not share key with application user; in particular normal-user requests **cannot** authenticate using it. A later authorized client identity, trust model and OS-enforced IPC must be designed separately.
- The isolated lab worker reports **counts only**, not full `docker_probe_recovery` records. It does not use the main validator's reconciliation or `service_response` schema and does not claim to replace them. It neither discovers nor touches Docker.
- The worker does not independently verify effective Windows ACLs, mitigate all junction/race attacks or pin the journal handle. SQLite safety depends on the protected directory and an exclusively trusted writer.
- Before production: design separate Windows service installation, signed/writable-code protection, secure key lifecycle, a Windows named pipe with restricted DACL and effective client-token authentication, timeout/resource limits, crash recovery, and independent security review.
