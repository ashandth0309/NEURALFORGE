

\# Milestone 04 — Reviewed Patch Proposals



\## Status



Read-only patch proposal workflow implemented and verified.



Latest verified regression: 109 passing tests.



\## Capabilities



\- Deterministic text replacement proposals

\- Unified diff generation

\- Git-compatible patch formatting

\- SHA-256 source verification

\- SQLite-indexed source selection

\- Authorization before repository reads

\- Rejection of stale, missing and unsafe source paths

\- Symlink rejection

\- No source modification during proposal generation



\## API



POST /repos/{repo\_id}/patch-proposals



The endpoint accepts:

\- path

\- old\_text

\- new\_text

\- expected\_sha256



The response includes:

\- repository\_id

\- path

\- original\_sha256

\- proposed\_sha256

\- unified\_diff

\- changed

\- applied



The current implementation always returns applied=false.



\## Live Verification



Date: 2026-11-23



Repository: demo-repo

File: src/app/page.tsx



Original text: Deploy Now

Proposed text: Launch NEURALFORGE



HTTP status: 200



Original SHA-256:

5a51fdb3f4c514f83e3415b8568d481455656afec2167d61167181c6483c62ff



Proposed SHA-256:

82bcf26892f46f136c3c8edad0c9e796e4cdfa5dbdcfb46487c308444712b642



Confirmed:

\- Unified diff returned successfully

\- changed=true

\- applied=false

\- Original file digest unchanged

\- Git working tree clean



\## Security Limitations



This is a trusted localhost development prototype.



X-Demo-User is a spoofable identity header, not

production authentication.



Source path and symlink checks do not eliminate

filesystem time-of-check/time-of-use races.



The current system cannot approve or apply patches.

No patch application endpoint is implemented.



\## Future Approval Workflow



A future implementation should require:



1\. Immutable proposal identification

2\. Explicit approval associated with an authenticated user

3\. Repository and target-file authorization

4\. Reverification of the source digest at application time

5\. Safe filesystem operations

6\. Conflict detection

7\. Audit records

8\. Validation before and after application

9\. Failure handling and recovery



Do not expose patch application to untrusted users

without completing a separate security review.
