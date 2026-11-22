# Milestone 4 requirement audit

Baseline: M3 `c73d99f79f85cc10f7200c101ce9e483aa7a3879`; branch `feat/private-alpha-hardening`. This is private-alpha engineering readiness, not production certification or authorization for external invitations.

| Requirement | Implementation and reproducible evidence |
|---|---|
| Preserve/branch/prepare M3 PR | M4 descends from verified M3; existing branches/data retained; draft PR #1 remains unmerged. |
| Security/parser hardening | `parse_isolation`, `parser_child`, `parser_sandbox`, DOCX preflight; hardening/ingestion/tenant/export tests on Windows/Linux/PostgreSQL; actual denied file/socket/exec and CPU/memory/wall probes. |
| Private-alpha access | Invite/disabled modes, first-admin CLI lock, expiry/rotation/disabled-user guards; real HTTPS invite and secure-cookie browser/API checks. |
| Enforced quotas | Owner/global serialized storage/doc/job/export reservations, atomic rates/provider caps, length/body/container/retention limits; concurrent exact-winner tests and real quota UI. |
| Observability | Safe route/request-ID events, input-redacted validation errors, identified streamed frontend transport failures, API latency buckets, aggregate query/job/export/resource metrics, worker heartbeat, health/readiness/admin diagnostics; private markers absent from ordinary logs. |
| Backup/restore | Encrypted pg_dump + validated sources/config/runtime manifest; separate empty hosted/standalone restores; source/citation identity checks, wrong-password/nonempty-target/session tests. See recovery JSON reports. |
| Human review/independent evaluation | Source/answer inspection, correction/reopen/decisions + immutable audit. Frozen configuration, separate splits. 120 unverified candidates and zero real approvals/holdout cases retained honestly. |
| Pilot preparation | PRIVATE_ALPHA, feedback form, issue template, five timed tasks and empty measurements.json. No real tester participation/invitations claimed. |
| Deployment | HTTPS Caddy overlay, secure cookies/private DB/loopback ports, persistent volumes, resource/tmpfs/PID limits, log rotation, operator backup scheduling/recovery instructions. No public deployment. |
| Negative automated tests | Tenant/export/expired/revoked/disabled credentials; invalid formats/PDF/encoding/bombs; parser limits; concurrent caps; model corruption; encryption integrity; actual SIGKILL recovery and safe log markers. |
| Browser QA | Real Chromium desktop and mobile emulation; HTTPS invite and expiry/quota/export/citations/evaluation workflows; development widget regression and screenshot inspection. See final QA report. |
| Bounded load | 60 warm queries at concurrency 1/4/8, nearest-rank P95, resource snapshots, quota rejections, four-doc ingestion and real recovery. Hardware/protocol/limits in BENCHMARKS and JSON. |
| Documentation | SECURITY, PRIVATE_ALPHA, OPERATIONS, BACKUP_RESTORE, BENCHMARKS, PROGRESS, LAUNCH_CHECKLIST, feedback/issue package and this audit. |
| Definition of done | All six GitHub jobs passed on code commit `bbcf7e1`: both complete database suites, frontend production build, development desktop/mobile browser, exact generated Docker independence/recovery, and HTTPS alpha hosted recovery/browser workflows. |
| Scope | No unrelated product modules, paid calls, public launch, destructive live restore or merge. |
| Delivery | M4 branch committed/pushed; tested application commit `bbcf7e1dd1382276c50ddf6dfe21392690c2924c`. Final documentation/evidence commit also corrects QA environment wording without changing application/runtime components. Main is not merged. |

## Final verification status

[GitHub Actions run 45022119636](https://github.com/AtharvaSamant4/RagForge/actions/runs/45022119636) completed successfully with **six successful jobs**. PostgreSQL: **91 passed**. Linux SQLite: **89 passed, 2 PostgreSQL-only skips**. The [CI receipt](qa/m4-ci-results.json) records the exact code SHA and JUnit counts.

Final development desktop/mobile workflows and HTTPS alpha desktop/mobile workflows passed with the streaming API proxy. The final monotonic rate-counter change passed both the regression suite and exact generated Docker acceptance. CI evidence includes [independence/restart](qa/m4-standalone-ci.json), [standalone encrypted recovery](qa/m4-standalone-recovery-ci.json) and [hosted encrypted recovery](qa/m4-hosted-recovery-ci.json). The final delivered application/runtime files match the tested code commit; finalization adds documentation/evidence and clarifies the QA report's host-context wording.

Local reports retain actual [worker interruption/ingestion](qa/m4-worker-recovery-ingestion.json), [deployed query load](qa/m4-query-load-final.json), [alpha desktop/mobile](qa/m4-alpha-browser-results.json), [development/widget desktop/mobile](qa/m4-development-browser-results.json), [upstream failure containment](qa/m4-api-proxy.json), and [deployment safeguards](qa/m4-deployment-checks.json). Screenshots were inspected; citation text remains above the composer with no horizontal overflow. Existing MVP/M2/M3 and both old standalone health endpoints returned 200 in the final preservation check, and M4 HTTPS readiness returned 200.

Engineering readiness is complete for a controlled private alpha. Target-host network/TLS/firewall verification, real-secret rotation, off-host backup/alert activation, participant authorization and actual consenting pilot measurement remain operator gates in [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md). All 120 candidate questions remain unverified; human-approved/holdout scores and pilot feedback remain empty. No production certification or public launch is claimed.
