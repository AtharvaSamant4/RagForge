# Implementation progress

## Current milestone: developer pilot preparation

M5 is being implemented on `feat/developer-pilot-validation` from verified M4 `04f6ef2`. Added opt-in enrollment/consent/retention/deletion, a deduplicated ten-stage technical funnel, restricted operator reporting, private feedback/triage, offline runtime proof and unfamiliar/approved-query evaluation import. No real participants, external invitations, human label approvals or adoption claims exist.

Executed final Windows SQLite backend suite: 115 passed, 3 platform-specific skips. Frontend typecheck and optimized Docker production build passed. Earlier focused checks passed 47 feature/export/review/compiled-runtime tests, four real desktop/mobile pilot browser workflows and an actual independent Docker runtime with all ten technical stages. Final browser/runtime verification of the latest usability/client refinements and complete remote CI remain in progress.

The initial latency investigation reproduced multi-second tails and isolated a Windows localhost IPv6 refusal: ::1 connection refusal took 2135 ms versus IPv4 connect 0.4 ms. A matched C4 TLS proxy burst measured P95 2502 ms with default transport and 482 ms with explicit IPv4 while retaining the hostname. Median did not improve uniformly. Cold model load and WAL/lock waits also varied. No quota, TLS or grounding threshold was relaxed; final repeated measurements, clean remote installation and complete CI remain in progress.

External phase: blocked pending explicit user authorization, approved target-host controls, real human label review and actual participants. See PILOT_PLAN/TASKS/METRICS/RESULTS and `pilot/readiness.json`.

## Verified Milestone 4 baseline

Milestone 4, private-alpha readiness, is implemented on `feat/private-alpha-hardening`, based on verified M3 `c73d99f79f85cc10f7200c101ce9e483aa7a3879`. Main and the M2/M3 branches are preserved. M3 draft PR [#1](https://github.com/AtharvaSamant4/RagForge/pull/1) is unmerged. No public deployment, paid model call or external pilot invitation occurred.

## Completed functionality

- Isolated bounded parsing: private child/environment, Linux Landlock/seccomp, Windows Job Object resource limits, CPU/memory/wall/output bounds, ZIP metadata/expansion/path/encoding safeguards and safe failure states.
- Invite/disabled alpha enrollment, serialized initial administrator, expiring keys/sessions, password rotation/revocation, disabled-account/public-widget guards and preserved development onboarding.
- Atomic owner/global quota reservations, bounded uploads/jobs/exports, retained-archive limits, request budgets and hosted-provider daily/input/output safeguards (disabled in alpha).
- Safe request IDs/route logs, input-redacted validation errors, identified frontend transport failures without mutation retries, isolated alpha environment loading, persistent counters/latency buckets, query/job/export/resource diagnostics, continuous worker heartbeats and actionable readiness.
- Encrypted consistent database/source/configuration backup, authenticated safe archives, separate empty-target restore guards, excluded sessions/secrets and tested hosted/standalone recovery.
- Audited source/answer inspection, correction/reopen/approve/reject workflow for 120 unverified candidates; frozen evaluation with separate development/human/holdout splits.
- Onboarding/tutorials/sample, five realistic pilot tasks, blank feedback/measurement records, issue template, HTTPS/resource-limited deployment configuration and operator/launch documentation.
- Generator 1.1.0 preserves standalone independence, secure authentication, strict Linux parsing, credential expiry, additive state migration, quotas and provider budgets. Old 1.0 exports are unchanged and still work.

## Executed verification

- Final complete GitHub database matrix on code commit `bbcf7e1`: PostgreSQL **91 passed**; Linux SQLite **89 passed, 2 PostgreSQL-only skips**, zero failures/errors. JUnit artifacts retain the counts. Earlier full local runs passed 87 PostgreSQL cases and 84 Windows SQLite cases with 3 platform-specific skips; later targeted regressions covered the added startup/publication, input-redaction, partial-write and delayed-rate-window cases.
- CPU-loop, memory allocation, wall timeout and subsequent valid parsing verified; Linux unrelated-file/network/process probes blocked. Concurrent upload/export/provider reservations and invitation redemption respect exact caps. Rotation invalidates sessions and project keys. Missing/corrupt model artifacts fail without fallback.
- Hosted encrypted backup: separate empty restore preserved source identity/hash, retrieval and exact citations; wrong passphrase failed before writes, old sessions were excluded and nonempty target restore was refused. See `qa/m4-hosted-recovery-load.json`.
- New standalone Docker app answered with matching citations while the isolated source stack was stopped and after restart. Its encrypted backup restored to a second empty deployment with matching source/citations and a new credential. Both old 1.0 apps still reject anonymous requests and answer/refuse honestly. See `qa/m4-standalone-acceptance.json` and `qa/m4-standalone-recovery.json`.
- Actual SIGKILL during ingestion recovered on attempt 2, with a cited query after recovery: 47.42 seconds including a QA-only five-second lease/crash interval/startup and an 832 KB document producing 747 chunks. Four concurrent sample PDF uploads reached ready in 9.17 seconds (0.436 docs/s). Unique password/source/question markers were absent from ordinary server logs. See `qa/m4-worker-recovery-ingestion.json`.
- Real Chromium HTTPS alpha desktop/mobile workflows passed: invitation rejection, secure cookie, project/upload/error/quota/job status, citations, evaluation, export, publication prohibition, logout and actual DB session expiry. Mobile is viewport/touch emulation, not physical-device or Safari certification. Screenshots inspected for layout/overflow; the expanded quote is also checked within the scroll panel above the composer.
- Frontend TypeScript and optimized Docker production builds passed. Final development/widget and HTTPS alpha desktop/mobile workflows passed with the streaming proxy. All six GitHub jobs passed on application commit `bbcf7e1`, including exact-template independence/restart, standalone recovery and hosted recovery. See [the M4 audit](MILESTONE4_AUDIT.md) and [CI receipt](qa/m4-ci-results.json). Finalization changes documents/evidence and QA protocol wording; application/runtime components are unchanged.
- Frozen 30-fixture development evaluation ran without tuning. All 120 proposed questions remain unverified; human-approved and independent holdout splits contain zero cases and report no score. No pilot participation/feedback is fabricated.

## Resource and verification observations

The final deployed rate-counter/proxy load measured 9.488 / 4.461 responses per second at concurrency 1 / 4, with P95 152.94 / 4364.96 ms. At concurrency 8, 21/24 requests succeeded and 3 returned the enforced minute quota; the 8.302 responses/s includes rejections. All stages shared one fixed minute. End snapshots: alpha API 200.7 MiB, worker 186.8 MiB, DB 50.57 MiB. These are small shared-host measurements, not peak-memory or production capacity claims. See `qa/m4-query-load-final.json`.

Keeping 42 containers plus host browsers/IDE active left about 1.3 GiB physical memory available. During overlapping verification/restarts, one valid PDF hit its wall deadline and a workflow hit its overall test deadline; a later upstream connection reset exposed a plain proxy 500. The streaming proxy now returns safe identified failures. The complete workflow budget is 240 seconds; individual action and parser limits remain unchanged. The parser failed visibly. Disposable M4 recovery copies were stopped with volumes preserved and verification was rerun without overlapping restarts. Existing MVP/M2/M3 and legacy standalone deployments were not stopped for this cleanup. Do not infer normal deployment requirements from running every historical QA environment simultaneously.

## Remaining limits and next priority

Not production-certified; no full malware scanning/independent sandbox audit, managed identity/reset/secret service, physical per-tenant DB/index accounting, automatic source-orphan/history cleanup, managed alerting/off-host backup activation or HA. Quotes prove provenance rather than truth/entailment. Hosted adapters have no live paid-provider verification. Initial dependencies/model downloads require network. Larger full reindexes require deliberate queue-cap adjustment. Windows development has resource containment, not Linux filesystem/network controls.

Before invitations: authorize participants, approve private networking/trusted TLS/firewalls/data policy, rotate real deployment secrets, configure backups/alerts/retention, verify containment/model readiness on the target host and run a measured consenting pilot. See LAUNCH_CHECKLIST.md. No billing, marketplace, OCR/multimedia, Kubernetes, multi-cloud or agent framework was added.
