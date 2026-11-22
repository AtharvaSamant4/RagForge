# Pilot results and readiness

Real authorized participants: **0**. Actual external trials: **0**. Human-approved candidate labels: **0**. Independent human-reviewed holdout/pilot-query cases: **0**. Human quality scores, completion rates, satisfaction, testimonials and adoption conclusions: **not collected / no score**.

No external participant has been contacted or invited by this milestone. The external phase is **blocked pending explicit user authorization, target-host operator checks and real participants**. Engineering QA accounts, scripted feedback and automated browser flows are excluded from these figures.

Engineering preparation is **complete**, with all seven CI jobs passing on code commit `5beded422d0fa9a16f47734297fc395548085332`. PostgreSQL: 118 passed. Linux SQLite: 116 passed, 2 platform-specific skips. Windows SQLite: 115 passed, 3 skips. TypeScript/production build, desktop/mobile workspace/widget, HTTPS alpha and pilot workflows, encrypted hosted/standalone recovery and actual source-offline generated-runtime checks passed. The clean exact-remote installation used uncached builds and fresh configuration/model/DB volumes, with first cited answer at 59.788 seconds and independent deployment/restart/client acceptance at 137.908 seconds on that CI runner.

| Gate | Actual state |
|---|---|
| Engineering checks | Complete; [audit](MILESTONE5_AUDIT.md), [CI receipt](qa/m5-ci-results.json), [controlled profiling](BENCHMARKS.md#milestone-5-latency-investigation). |
| Operator target-host configuration | Pending private network/TLS/firewall, backups/alerts/retention, incident owner and credential signoff. |
| External access authorization | Pending explicit user authorization per participant; no contact/invitation performed. |
| Human evaluation | Zero approved candidate, holdout or pilot-query cases; no human quality score. |
| Actual participant trials | Zero; engineering QA is excluded. |

[Machine readiness](../pilot/readiness.json) preserves these separate states. The repeated M4/M5 comparison is mixed rather than a universal speedup: M5 default-off pooled P95 increased at C1/C4 and decreased at C8. A separate matched transport test isolated Windows localhost fallback and measured P95 2502 → 482 ms with explicit IPv4 while retaining the HTTPS hostname. No quotas, TLS verification or grounding thresholds were relaxed. These small shared-host engineering samples are not participant onboarding or production-capacity estimates.

The proposed five-person success criteria in PILOT_PLAN.md remain subject to user approval. Record actual outcomes, failures, assistance and feedback here only after authorized participants complete or abandon the study. Recommended next action is to review engineering evidence and complete operator/authorization gates, then conduct the small consenting study; do not infer market validation from synthetic QA.
