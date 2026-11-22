# Milestone 5 implementation and verification plan

Baseline: `04f6ef26420fe188aba93c30de5b07ac95ca31ad`; branch `feat/developer-pilot-validation`. Preserve M1–M4, existing stacks/data, invite-only alpha, disabled paid providers and standalone independence. Do not merge or contact external participants.

1. Add additive pilot tables/migration and explicit operator enrollment, consent, withdrawal/deletion and retention. Default collection is off. Engineering QA is a separate cohort and never counts as human participation.
2. Record a deduplicated activation funnel from successful server operations, plus bounded technical counters/latency without content, questions or credentials. Distinguish API-key use from verified human integration and signed self-hosted runtime evidence from remote attestation.
3. Add a small participant study form and administrator-only dashboard, triage/review and sanitized exports. Keep technical completion separate from self-reported task outcomes. Private text stays out of default exports and ordinary logs.
4. Require explicit, offline runtime evidence for independent startup/cited query; no automatic callback or telemetry from exports. Preserve authentication and add replay/ownership/consent checks. Document evidence trust limits and observed-time semantics.
5. Extend review/import/evaluation tooling for unfamiliar documents and separately approved pilot query datasets. Freeze configurations and holdout provenance, and retain zero human results until actual review.
6. Profile M4 and M5 with equivalent bounded cold/warm workloads, separate HTTP success/quota/error distributions, resource and model/DB/scheduling observations. Change bottlenecks only with evidence; preserve quotas.
7. Execute installation in a fresh checkout/Compose namespace with no database/model volumes, host virtualenv or inherited secrets required by the application. Exercise sample PDF, external API, export and independent Docker startup/query.
8. Run PostgreSQL/SQLite, frontend and real desktop/mobile browser checks, negative privacy/authorization/deduplication/deletion tests, and generated-app independence. Preserve reproducible sanitized evidence.
9. Publish PILOT_PLAN/TASKS/METRICS/RESULTS, readiness JSON and human report, privacy/retention/incident/triage procedures and stacked review path. Commit/push verified work. External authorization, real label review and real participant outcomes remain separate pending gates.

Completion evidence must map every numbered M5 requirement to code, executed checks, artifacts or explicitly pending human/operator action. Local automation must never mark real trials complete.
