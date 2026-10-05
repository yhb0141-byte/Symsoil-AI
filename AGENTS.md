# Repository development rules

Build SymSoil as a community-controlled local application. Read docs/product/PRD.md and the current release scope before changing behavior.

- R0 is a synthetic-data development release. Never imply that a synthetic acceptance or discussion is a real community decision.
- Accuracy confirmation, sharing permission, stance, approval, and task acceptance are different operations.
- Enforce authentication, object access, version checks, and idempotency on the server.
- Administrators do not get blanket access to private expressions.
- Keep real community data, secrets, backups, generated databases, and model weights out of Git.
- Use approved manual paths when AI is unavailable. Do not disguise canned output as model inference.
- Run backend tests, frontend type checking/build, and applicable browser verification before handing off changes.
- Describe release limitations and migration steps honestly. Do not mark unimplemented PRD requirements complete.
