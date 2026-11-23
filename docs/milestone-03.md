

\# Milestone 03 — Indexed Retrieval and Evidence Q\&A



\## Overview



NEURALFORGE provides deterministic repository symbol search

and evidence-backed answers using a SQLite index.



The current implementation is a trusted local-development

prototype, not a production multi-user service.



\## Implemented capabilities



\- TypeScript and TSX repository indexing

\- AST-based symbol extraction

\- SHA-256 metadata for indexed source files

\- Transactional SQLite snapshot replacement

\- Deterministic symbol search

\- Evidence-linked question answering

\- Match counts and evidence truncation metadata

\- Point-in-time freshness checks for returned evidence

\- Authorization-before-store-read checks



\## API endpoints



GET /health



GET /repos/{repo\_id}/symbols?q=RootLayout



POST /repos/{repo\_id}/ask



Example request body:



&#x20;   {"question": "Where is RootLayout defined?"}



For the local demo, repository requests use:



&#x20;   X-Demo-User: demo-user



\## Indexing the demo repository



From the NEURALFORGE repository root, with the Python

virtual environment activated:



&#x20;   python -m services.indexer.persist apps/web --allowed-root . --repository-id demo-repo --database neuralforge-api.sqlite3



Start the API locally:



&#x20;   python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8001



Open:



&#x20;   http://127.0.0.1:8001/docs



If port 8001 is already occupied, stop the existing

server before starting another instance.



\## Running the regression tests



&#x20;   python -m unittest discover -s services/indexer/tests -v



&#x20;   python -m unittest apps.api.tests.test\_main -v



&#x20;   node --test apps/web/scripts/symbols.test.cjs



\## Freshness semantics



current:

The source file's SHA-256 matched the indexed digest

when the file was read.



stale:

The source file's content hash differed from the

indexed digest.



missing:

The indexed source path did not exist during checking.



unavailable:

The source could not be checked safely or successfully.



not\_verified:

No trusted repository root was configured for checking.



Freshness is evaluated for returned Q\&A evidence.

It does not prove that every indexed source file is current.



\## Security boundaries



1\. X-Demo-User is a spoofable demonstration header.

&#x20;  It is NOT real authentication.



2\. The repository owner mapping is hardcoded for local

&#x20;  development. Replace it with authenticated identities

&#x20;  and persistent authorization before production use.



3\. Repository roots are configured by the server.

&#x20;  API callers must not supply arbitrary host paths.



4\. Path validation and symlink rejection reduce risks,

&#x20;  but do not eliminate filesystem race conditions.



5\. A source file may change during or immediately after

&#x20;  a freshness check. The result is point-in-time only.



6\. This implementation does not provide sandboxing,

&#x20;  operating-system isolation, or secure execution of

&#x20;  untrusted repositories.



7\. Indexed symbol locations are metadata. They are

&#x20;  not proof that an arbitrary behavioral claim about

&#x20;  the source code is correct.



8\. No arbitrary user-supplied host commands are executed

&#x20;  by the current retrieval and question-answering API.



\## Production requirements



Before exposing this service beyond trusted localhost

development, implement and review:



\- Real authentication and repository-level authorization

\- Strong filesystem isolation for untrusted repositories

\- Safe file-opening strategies resistant to link races

\- Resource limits and request rate limiting

\- Structured audit logging

\- Automated CI testing and dependency review

\- Deployment configuration and secrets management

\- Clear behavior when freshness verification fails



\## Known non-failing warning



The FastAPI test suite currently emits a Starlette

deprecation warning involving httpx. Tests pass, but

the dependency compatibility should be reviewed before

upgrading or replacing packages.



