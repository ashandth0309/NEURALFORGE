# NEURALFORGE M05 — authenticated in-process boundary and byte framing

Base ref: `5fa513f` (`feat/validator-service-boundary`).

## Contents

- `service_boundary.py`: verifies authenticated recovery envelopes before calling the existing dispatcher, reuses process-local ReplayGuard, serializes dispatch per boundary instance, sanitizes failures.
- `service_framing.py`: four-byte big-endian length framing for **an already trusted byte stream**. Strict request bound 8192 bytes and response bound 65536 bytes. Reads a single message only.
- Two test modules: negative authentication, concurrent replay, framing, and no-dispatch-on-malformed-input. These tests use mocks and memory buffers, **not a live listener, Docker, or persistent storage**.
- `verify_m05_boundary.cmd`: verification script.

## Installation

Extract at repository root, preserving directory layout. Check `git status` before extraction to protect local edits. Then `call verify_m05_boundary.cmd`. Review changes before committing.

## Security limitations (critical)

This is **not an authenticated OS transport**. It opens NO named pipe, Unix socket, TCP socket, listener, or Windows service. An attacker with the key can authenticate, and a compromised caller or service identity can bypass controls. ReplayGuard is **process-local** and loses memory after a restart. The framing layer does not enforce timeouts and must never be fed an untrusted stream without trusted host process limits. The service operator still may perform *read-only* Docker inspection for unresolved records.

A future trusted Windows service must enforce identity/ACLs on its named pipe, provision and protect secrets separately, enforce connection/IO deadlines, run under separate least-privilege credentials, protect SQLite and `.lock` from other processes, test under separate Windows principals, and validate recovery after crashes and path swaps. Do not enable untrusted-code execution or live Docker diagnostics based on this prototype.
