# Implementation progress

## Current milestone

Milestone 2 is implemented on `feat/semantic-benchmarks-qa`; it is not merged into main. The original MVP stack and its data remain separate. The semantic QA stack uses Docker Compose project `ragforge-m2`, dashboard port 3010 and API port 8010.

## Completed functionality

* Preserved accounts/projects, scoped API keys, document formats, background ingestion, citations/history, evaluation, widgets, deletion and local deployment.
* Pinned CPU MiniLM ONNX inference: real semantic vectors, verified model/tokenizer checksums, persistent shared model cache, batched/deduplicated computation and bounded process-memory caching. Original lexical hashing remains selectable.
* Model profiles and index generations, preserved-data migration, descriptive compatibility gates, fixed PostgreSQL dimension checks, controlled reindexing and stale-job cancellation. Existing default lexical jobs survive migration.
* Semantic/keyword/hybrid retrieval, measured backend-specific defaults, explicit thresholds, weighted fusion, token-budget-aware chunks, qualified evidence and stronger exact-source grounding.
* 18 synthetic benchmark sources, 30 deterministic fixture contracts, 120 explicitly unverified candidates, a separate human review/approval workflow, frozen original lexical baseline, actual database comparisons and resource/load measurements.
* Active model/index diagnostics, three-strategy passage comparison and retrieval latency in the developer UI.
* Real desktop/mobile Playwright workflows and inspected screenshots. Fixed mobile navigation, hidden document actions, small text, widget-settings loading races, stale rebuild messages and partial PDF line excerpts.
* Updated setup/model/benchmark/browser/API/architecture/security documentation and CI coverage.

## Executed checks

* Docker PostgreSQL/pgvector: 56 backend tests passed, including actual model inference and original regressions.
* SQLite/Windows: 54 tests passed; 2 PostgreSQL-only concurrency/fixed-dimension cases were intentionally skipped.
* Frontend TypeScript checking and optimized production builds passed, including the actual Docker web image.
* Desktop and mobile browser workflows both passed, with zero unexpected/flaky/skipped browser cases. Exact durations are in `qa/browser-results.json`.
* Real semantic Docker HTTP smoke and web-proxy/widget checks passed, including Python/JavaScript/cURL clients and document deletion cleanup.
* PostgreSQL and SQLite benchmarks executed on the same sources and questions; current JSON reports retain model/configuration/source/dataset fingerprints and individual outcomes. See BENCHMARKS.md.
* HTTP load: 24 successful queries at concurrency 8; all 16 health requests returned 200. Latency, indexing/embedding time, memory and CPU observations are recorded without capacity guarantees.
* One upstream Starlette TestClient deprecation warning remains; tests pass. No public deployment, paid model calls or merge into main occurred.

## Known limitations

The English semantic model and small authored corpus do not establish general customer-data accuracy. Fixtures were inspected during tuning; no blind holdout or independently human-verified candidate accuracy is claimed. Human candidate review remains a supported workflow, not an invented completed review. Semantic similarity and exact quotes do not prove answerability or entailment. Numeric conflicts and instruction-request filtering cover narrow patterns. Hosted adapters have no live paid-provider verification. Model memory is per process; cache state and competing load affect latency, and concurrent tail latency is noticeable.

No OCR, multimodal ingestion, arbitrary CSV analytics, standalone code-package export, SSO/password recovery or public hosting was added. Production parsing isolation, storage/spend quotas, broader monitoring and other launch requirements remain in SECURITY.md.

## Next priority

Human review of the candidate queue, independently labeled developer-document benchmarks, broader multilingual/contradiction coverage and measured tail-latency/memory tuning before production hardening or standalone source export. The requirement-by-requirement completion evidence is in MILESTONE2_AUDIT.md.
