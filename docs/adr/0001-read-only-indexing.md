# ADR-0001: Read-Only Repository Indexing

- Status: Proposed

- Date: 2026-11-23

- Project: NEURALFORGE

## Context

NEURALFORGE must inspect approved TypeScript repositories

without executing the imported application code.

The existing indexer produces deterministic file metadata,

SHA-256 hashes, and top-level AST symbols.

The current implementation has no persistent database,

incremental index, or sandboxed parser execution.

## Decision

1\. Keep indexing and retrieval read-only.

2\. Accept repositories only within an explicit allowed root.

3\. Index supported .ts and .tsx source files.

4\. Exclude generated, hidden, and unsupported paths.

5\. Enforce file-size and file-count limits.

6\. Keep source paths repository-relative.

7\. Return deterministic metadata and search results.

8\. Treat repository content as untrusted input.

9\. Introduce durable storage behind a separate interface.

10\. Require explicit human review for future code changes.

## Trust Boundaries

- Indexing must not execute imported source code.

- No automatic patch application or Git merging.

- The existing path checks reduce risk but do not

&#x20; eliminate filesystem race conditions.

- The Node parser is not yet sandboxed.

- Future API routes require repository ownership checks.

- Actual secrets must never be committed or indexed.

## Alternatives

### Full-stack implementation immediately

Rejected for the first milestone because adding the API,

database, workers, and UI together would make individual

failures harder to isolate.

### Regex-only symbol extraction

Rejected because syntax-aware extraction provides a more

appropriate foundation for TypeScript declarations.

### Unrestricted filesystem indexing

Rejected because it violates the repository trust boundary.

## Consequences

Advantages:

- Smaller components with independently testable behavior.

- Clear separation between indexing and future API logic.

- Deterministic metadata for regression testing.

Limitations:

- No database persistence yet.

- No incremental indexing yet.

- No complete cross-file dependency graph.

- Parser isolation and race-resistant file access remain open.

## Verification Evidence

Commit bfe309e:

- 28 Python tests passed.

- 6 Node.js parser tests passed.

- No tracked environment or generated dependency files

&#x20; appeared in the specified Git filename check.

Frontend lint and production-build verification remain

pending at the time of writing.

## Next Milestone

Design and implement persistent storage for indexed

files, hashes, and symbols, with schema validation and tests.
