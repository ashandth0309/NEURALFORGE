# NEURALFORGE M05 — offline hardening batch

Starting ref: `10c4dd2`, branch `feat/validator-service-boundary`.

This batch is **not complete M05 production service isolation**.

## Included

- `service_auth.py`: canonical HMAC-SHA256 signed request envelope, timestamp, nonce, bounded parsing, in-memory replay prevention. **Offline building block only.**
- `test_service_auth.py`: authorization-negative, corruption, stale clock, replay and concurrency tests.
- `test_service_adversarial.py`: real temporary SQLite and OS lock with mocked Docker paths and fail-closed checks.
- `verify_m05.cmd`: compile and full validator test commands.

## Explicitly not implemented / not authorized

- Listener, API endpoint, Windows service installation or IPC transport.
- Service authentication through Windows token / named pipe ACLs.
- Separate service identity and protected database/lock directory ACLs.
- Durable multi-worker replay prevention, key provisioning/rotation/zeroization.
- Independent security review, Windows race-resistance, Docker isolation proof.
- Arbitrary untrusted-code execution, Docker create/start/stop/remove.

**Never place an HMAC key in the repository or transmit the key to untrusted clients.** This exercise is not evidence that HMAC by itself creates a trust boundary; a compromised caller holding the shared key is authorized by the MAC.

## Installation on Windows

1. Back up / commit your changes. Run `git status` and verify branch is `feat/validator-service-boundary`.
2. Extract the ZIP into the NEURALFORGE repository root, keeping directories.
3. Run `verify_m05.cmd` from repository root.
4. Inspect `git status --short`, `git diff --check` and untracked new files.
5. Do not commit until local tests pass and code is reviewed. Keep Docker execution disabled.

## Acceptance gates for real M05 completion

1. Threat model and principal/permission boundaries reviewed.
2. Windows service identity + ACLs applied and verified from separate low-privileged account.
3. An authenticated local transport that enforces OS peer identity; request signing and replay persistence if used.
4. Persistent journal/lock protection and safe failover on crashes and path substitution.
5. Independent adversarial security verification and operational recovery drills.
6. Real Docker read-only/diagnostic behavior reviewed and verified under a dedicated constrained identity.
7. Security docs, limitations, reproducible benchmark, end-to-end evidence accepted.
