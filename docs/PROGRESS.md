# Implementation progress

## Completed

* Isolated accounts/projects; project CRUD; scoped, hashed and revocable API credentials.
* Selectable-text PDF, DOCX, UTF-8 TXT/Markdown and textual CSV; metadata, offsets, validation and random storage paths.
* Durable leased jobs, bounded retries, explicit failure recovery and transactional chunk publication; deletion and index cleanup.
* Vector/keyword/hybrid retrieval, documented automatic defaults, chunk controls, conservative refusals, exact source citations, persisted conversations and SSE delivery endpoint.
* Responsive Next.js dashboard: uploads, processing/error states, chunk inspection, pipeline edits/reindex, playground, measured evaluation, API keys/examples, widget controls, manifests and settings.
* Explicit public query capabilities, origin-constrained iframe CSP, revocation and appearance controls. Private management keys never appear in widgets.
* Verified vs synthetic evaluation cases, real document recall, citation provenance, lexical overlap, refusal agreement and latency; semantic faithfulness explicitly unassessed.
* Environment configuration, frozen initial Alembic migration, Docker Compose, PostgreSQL vector/FTS indexes, local Windows helper, sample documents, API/security/architecture docs and CI matrix.

## Executed verification

* Windows/Python 3.12 + SQLite: 33 automated tests passed; the PostgreSQL-only multi-worker test was correctly skipped. Coverage includes real PDF/DOCX extraction, all three retrieval modes, tenant boundaries, API key scopes/revocation, retries, expired lease recovery, deletion, evaluation and widget permissions. One upstream Starlette TestClient deprecation warning remains; it does not fail tests.
* Real local HTTP API + independent durable worker: full `scripts/smoke.py` workflow passed (PDF upload, indexing, cited answer, external Bearer API, refusal, evaluation and deletion).
* TypeScript check and Next.js production build passed. Local dashboard HTTP response: 200.
* Browser QA attempted, but the browser access host was unavailable. Visual rendering, interactive clicks and responsive layout have **not** been browser-verified.
* PostgreSQL 17 + pgvector: the frozen migration applied and all 34 tests passed against an isolated disposable PostgreSQL database (including vector, keyword and hybrid query paths, concurrent job claims and deletion during processing).
* `scripts/check-web.py` passed against the running Next.js proxy: web routes/assets, real PDF processing, JavaScript and cURL API clients, widget CSP/configuration escaping, public queries and revocation.
* SQLite migration upgrade, downgrade and re-upgrade passed. The updated TypeScript check and production build passed.
* Docker Compose: API, worker and production Next.js images built successfully. All four services started with the documented default ports; database and API health checks passed.
* Linux/Python 3.12 inside the actual API image: the frozen migration applied to a new disposable PostgreSQL database and all 34 tests passed (14 seconds).
* Both `scripts/smoke.py` and `scripts/check-web.py` passed against the final containerized stack on ports 8000/3000, including Python/JavaScript/cURL clients, cited answers, measured evaluation, proxy OpenAPI, widget CSP/public query/revocation and deletion cleanup.
* The implementation and verification records are committed and pushed to `https://github.com/AtharvaSamant4/RagForge`, branch `main`. No public deployment or paid model calls were performed.

## Known limitations

Local embeddings are lexical feature hashing; local answers extract source sentences. Synonyms and conversational follow-ups are limited. Hosted adapters have contract tests but no paid live API verification. Exact quote validation does not establish semantic entailment. Evaluations run synchronously with at most 50 cases. No OCR, multimodal data, numerical CSV analytics, standalone source export, password recovery/SSO or public deployment. Production security work is enumerated in SECURITY.md.

## Next priority

The local MVP foundation is implemented and verified. Next: browser visual/interaction QA when browser access is available, parser isolation and storage/spend quotas before internet exposure, broader manually labeled retrieval benchmarks, provider-native streaming and standalone Docker source export. Hosted adapters still need an explicitly authorized live provider test.
