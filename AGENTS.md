# Repository development rules

Build SymSoil as a community-controlled local application. Read docs/product/PRD.md and the current release scope before changing behavior.

Current increment: R0.4; read docs/development/R04_SCOPE.md and API_CONTRACT_R04.md alongside the R0.3 and R0.2 baseline contracts. The uploaded implementation-plan alignment is docs/product/IMPLEMENTATION_ALIGNMENT.md. All current increments remain synthetic development, not a complete R1 release. Read CONTINUATION.md before resuming work to avoid concurrent branch changes.

- R0 is a synthetic-data development release. Never imply that a synthetic acceptance or discussion is a real community decision.
- Accuracy confirmation, sharing permission, stance, approval, and task acceptance are different operations.
- Enforce authentication, object access, version checks, and idempotency on the server.
- Administrators do not get blanket access to private expressions.
- Keep real community data, secrets, backups, generated databases, and model weights out of Git.
- Use approved manual paths when AI is unavailable. Do not disguise canned output as model inference.
- Knowledge drafts stay out of the published Document table; list, count, retrieval, full text, citations and model return all require current publication and audience checks. A designated reviewer may read only the exact submitted revision.
- Run backend tests, frontend type checking/build, and applicable browser verification before handing off changes.
- Describe release limitations and migration steps honestly. Do not mark unimplemented PRD requirements complete.

- Correction text is explicitly shared only between requester and verified document uploader. Admin roles do not grant access. Never ingest correction text into retrieval; source access and correction sharing are independent.
