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
| Definition of done | Final complete CI matrix, current development browser and final template acceptance must be green before goal completion. |
| Scope | No unrelated product modules, paid calls, public launch, destructive live restore or merge. |
| Delivery | Commit/push M4 branch; final SHA and GitHub status recorded after verification. |

## Final verification status

Final development desktop/mobile workflows and HTTPS alpha desktop/mobile workflows passed with the streaming API proxy. The final monotonic rate-counter change passed the compiled standalone runtime and targeted regression tests; exact generated Docker acceptance and the complete database suites are also configured in GitHub Actions. Local hosted/standalone recovery, real worker interruption, final deployed load and review workflow have executed JSON evidence. GitHub results will be recorded after the branch run; no pending external human review is represented as completed.
