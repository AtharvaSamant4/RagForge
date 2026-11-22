# Milestone 5 engineering audit

Branch: `feat/developer-pilot-validation`, based on verified M4 `04f6ef26420fe188aba93c30de5b07ac95ca31ad`. **Engineering preparation is complete.** All seven CI jobs passed on code commit `5beded422d0fa9a16f47734297fc395548085332`; finalization adds documentation, evidence and readiness state without runtime changes. The external pilot is **blocked pending human action**. Real participants/trials and human-approved evaluation cases are zero.

## Implementation and acceptance map

| Requirement | Delivered behavior and evidence |
|---|---|
| 1. Preserve the milestone stack | Separate M5 branch; no merges. [M3 draft PR #1](https://github.com/AtharvaSamant4/RagForge/pull/1) remains open; [M4 draft PR #2](https://github.com/AtharvaSamant4/RagForge/pull/2) targets M3; [M5 draft PR #3](https://github.com/AtharvaSamant4/RagForge/pull/3) targets M4. Review each delta against its immediate predecessor. |
| 2. Activation funnel | Ten timestamped server-observed stages, opt-in start, no historical activity backfill, independently signed startup/query evidence rather than ZIP inference. Actual Docker proof in [local receipt](qa/m5-pilot-runtime.json). |
| 3. Operator dashboard | Administrator-only counters, latency, failures, cohorts, reported problems and sanitized numeric/enum report. Human outcomes remain separate from technical stages. |
| 4. Five usability tasks | [Task protocol](PILOT_TASKS.md), participant timer/manual duration, status/errors/assistance/difficulty/optional feedback, private operator review and explicit actual-trial attestation. Unattempted tasks can remain unrated. |
| 5. Independent evaluation | Permission-aware import/normalization with original and prepared checksums; source inspection/correction/audited approval; separate development, human, holdout and permitted pilot-query splits. [Definitions](PILOT_METRICS.md). |
| 6. Latency investigation | Controlled M4/M5 cold/warm and concurrency runs, DB/WAL/function/cgroup measurements, actual competing ingestion, rate-window probe and transport diagnosis. [Protocol and measurements](BENCHMARKS.md). |
| 7. Clean installation | Exact remote clone, uncached dependency builds, empty model and absent DB volume, new configuration/account/PDF, cited/refused answers, external API and independent export/restart. [CI receipt](qa/m5-clean-install-ci.json). |
| 8. Private triage | Nine categories, four severities, internal engineering reference, manual sanitized reproduction and explicit export approval. No automatic public issue creation. |
| 9. Participant controls | Enrollment requires prior authorization; separate optional consent, 30-day expiry, withdrawal and self/operator deletion. Hosted backup omits study rows and proof-bearing export state. [Plan](PILOT_PLAN.md), [security](SECURITY.md), [backup](BACKUP_RESTORE.md). |
| 10. Readiness gate | Runtime diagnostics plus separate operator, access authorization, human evaluation and actual-trial state. [Machine report](../pilot/readiness.json); local readiness never grants external access. |
| 11. Success criteria | Proposed five-person learning targets remain unapproved; actual human results are empty. [Results](PILOT_RESULTS.md). |
| 12. Regression verification | Complete PostgreSQL/SQLite, TypeScript/production build, Chromium desktop/mobile, independent generated runtimes and encrypted recovery. Consent, isolation, redaction, cap/deduplication concurrency, deletion and feedback regressions included. |
| 13. Documentation | PILOT_PLAN/TASKS/METRICS/RESULTS, PRIVATE_ALPHA, LAUNCH_CHECKLIST, PROGRESS and this audit. Start/monitor/end operator steps are explicit. |
| 14. Scope | No billing, marketplace, OCR/multimedia, Kubernetes, multi-cloud provisioning or agent framework. |
| 15. Completion boundary | Engineering acceptance and real external participation are separate. No invitation, participant contact, paid call or public deployment performed. |
| 16. Delivery | Versioned source/evidence, pushed feature branch and a stacked review path; main and prior milestone branches remain unmerged. |

## Executed verification

- Windows Python 3.12 complete backend: **115 passed, 3 platform-specific skips**, no failures/errors; JUnit retained in ignored local artifacts. Linux CI: PostgreSQL **118 passed**; SQLite **116 passed, 2 PostgreSQL-only skips**. The final [CI receipt](qa/m5-ci-results.json) records the exact tested code commit and all seven jobs.
- TypeScript and the optimized Docker frontend build passed. Four latest local HTTPS Chromium pilot workflows passed on desktop/mobile viewport/touch emulation: consent, task feedback, private triage, sanitized downloads, withdrawal/deletion and signed runtime-proof import. [Browser result](qa/m5-pilot-browser-results.json) and [screenshots](qa/screenshots/m5/) are engineering fixtures, not human usability evidence. Layout and overflow were inspected; no physical-device/Safari claim.
- Actual generator **1.2.0** Docker application matched source citations, refused an unsupported question, required its own credential, persisted its own index after restart and worked with Python, JavaScript and cURL while the isolated source was offline. The bundled Python/JS clients used the initialized nondefault port without URL overrides. [Acceptance](qa/m5-standalone-acceptance.json). Historical downloaded packages and original stacks were preserved.
- Clean remote installation required neither an inherited app virtual environment, model cache, database nor secret file. CI's fresh runner built pinned dependencies with `--no-cache --pull`, verified empty volumes, downloaded the pinned model and obtained a cited answer at 59.788 seconds and independent deployment/restart/client acceptance at 137.908 seconds from clone start. Setup timings describe this runner, not a human onboarding estimate.
- Frozen development evaluation ran all **30 authored fixtures**, with Hit@5/recall@5, citation provenance and refusal-contract match 1.0 on these known specifications. Three other splits report zero cases and no score. All original **120 candidates remain unverified**. [Evaluation limits and receipts](BENCHMARKS.md#milestone-5-frozen-evaluation).

## Performance interpretation

The matched C4 transport probe measured P95 **2501.83 → 481.84 ms** with explicit IPv4 while retaining the HTTPS hostname; median **210.74 → 282.44 ms** did not improve. Windows `::1` refusal took about 2135 ms before reaching the API. Local HTTP examples/defaults now select IPv4; approved HTTPS identity/verification, quotas, model and grounding settings remain intact. The final three-repeat default-off comparison recorded pooled P95 M4/M5 of 236.61/314.58 ms (C1), 742.94/1219.47 ms (C4) and 1663.73/929.40 ms (C8), with all 504 ordinary requests successful including the separate consent-on pass. Both quota probes returned exactly three enforced rejections. Independent cold/warm, worker, cache, DB, scheduling and resource observations are retained in [the profiling receipt](qa/m5-query-profiling.json), with methodology and limits in [BENCHMARKS.md](BENCHMARKS.md). [Normalized image-source verification](qa/m5-image-source-verification.json) confirms baseline/candidate code identity and the unchanged proxy path. Small shared-host samples do not establish production capacity or uniformly lower latency.

## Remaining operator and human work

The operator must approve target-host private networking, trusted TLS/firewall, model/parser containment readiness, monitored alerts, backup/restore/retention, incident ownership and real credential rotation. Paid providers remain disabled absent separate approval. Then obtain explicit authorization per participant, explain permitted non-sensitive documents and limitations, and collect optional study consent. Proposed success criteria still require user approval.

Authorized humans must inspect/correct/approve evaluation labels and supply an unfamiliar permitted holdout. Actual developers must attempt the five tasks; failures and incomplete tasks must be retained. Technical QA, key-authenticated requests, a signed owner-controlled package and an operator attestation do not independently prove human adoption or answer truth.

Existing security limits remain: no independent containment/malware audit, managed identity/reset/secret service, HA or physical per-tenant storage isolation; first installation needs dependency/model download access. Windows development has resource containment rather than the Linux parser filesystem/network policy. Signed runtime evidence is owner-controlled provenance, not remote attestation. Deleted delivered copies and separately retained operator reports cannot be remotely revoked. Human review of exported issue text remains necessary.

Use [the operator plan](PILOT_PLAN.md), [launch gate](LAUNCH_CHECKLIST.md) and [machine readiness](../pilot/readiness.json). No human completion rate, satisfaction, accuracy or market-validation claim is justified yet.
