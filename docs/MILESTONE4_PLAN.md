# Milestone 4 implementation and verification plan

Base: verified `c73d99f`; branch `feat/private-alpha-hardening`. Milestone 3 draft PR: https://github.com/AtharvaSamant4/RagForge/pull/1. Do not merge or publicly deploy. Existing stacks/volumes remain separate; new operational tests use disposable Compose projects and databases.

1. Contain parsing in bounded subprocesses: wall/CPU/memory/output limits, process-tree cleanup, restricted environment and tested Linux filesystem/network/process restrictions where supported. Validate malformed/oversized/bomb inputs and fail closed in strict alpha mode. Preserve ordinary local onboarding and old exported copies.
2. Add operator bootstrap, single-use expiring invites, account/session/key rotation and revocation, enforced storage/document/job/export/request/provider budgets with atomic concurrency controls.
3. Add safe operational metrics, readiness and authenticated diagnostics; structured request/job/error identifiers without questions, documents or credentials in logs.
4. Build versioned backup/restore tooling and execute an account/project/document/citation round trip into an empty isolated PostgreSQL/storage environment, including standalone state. Document consistency, retention, encryption and restore boundaries.
5. Extend human review/correction and frozen independent evaluation. Prepare an external-developer onboarding/pilot package with five tasks and honest empty measurement/feedback forms; invite nobody without separate authorization.
6. Provide a loopback HTTPS private-alpha Compose profile with secure cookies, private networking, persistent storage, limits and log rotation. Execute full SQLite/PostgreSQL regressions, negative/concurrency/parser tests, real desktop/mobile alpha browser QA, bounded load/recovery and standalone tests.
7. Audit every requirement against current artifacts and executed evidence; document remaining risk and readiness gates, commit/push feature branch only.

No malware-scanning or complete sandbox claim is permitted without implementation and actual tests. A process/OS-resource boundary alone does not eliminate parser RCE risk. No general accuracy or real-user participation claim is inferred from engineering fixtures.
