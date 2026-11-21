# RAGForge architecture and implementation plan

## Decisions

One FastAPI backend owns authentication, projects, uploads, retrieval, evaluation and public access. A Next.js App Router dashboard uses same-origin `/api` forwarding. The browser never sees provider credentials. Branding comes from server configuration.

PostgreSQL + pgvector is the Docker deployment target. SQLite with exact vector scoring is a deliberately small local development alternative. Local embeddings are deterministic, normalized feature-hashing vectors (lexical, not pretrained semantic embeddings); local answers quote supporting sentences. OpenAI embedding and Responses adapters are opt-in and never silently replace a failed provider with local output.

Use a **database-backed durable job queue**, rather than Redis: ingestion state and enqueue are committed together, eliminating the DB/broker dual-write failure. PostgreSQL workers claim with `FOR UPDATE SKIP LOCKED`; SQLite supports one worker. Leases recover interrupted jobs. Extraction runs outside the claim transaction; atomic replacement of chunks occurs only after success. Retry is bounded, errors remain inspectable, and explicit retries are supported. Redis can be introduced when measured throughput justifies it.

No independent source-package export is claimed. A versioned JSON manifest is the foundation for that next milestone.

## Data model

Users own projects (tenant boundary); sessions are hashed opaque secrets. Every document, chunk, job, API key, query record, conversation, evaluation case and evaluation run has a project ID. Project APIs resolve authorization before looking up child resources. API credentials carry explicit `query`, `read`, and `documents` scopes. Widget tokens only grant public query access, require explicit publication and allowed embedding origins, and do not grant history or management access.

Documents have validated display names, random storage paths, SHA-256 content hashes, processing state, extracted metadata, chunk count and safe error codes. Chunks preserve page/section/row locators and source offsets. PostgreSQL uses a 384-dimensional vector column, HNSW index and GIN full-text index. Project pipeline configuration is versioned per job. Changes to chunk settings require explicit reindexing; retrieval settings apply immediately. Changing embedding provider requires rebuilding all indexes in a fresh database (fixed dimension).

## API contracts (OpenAPI is available at `/docs`)

* `/v1/auth/register`, `/login`, `/logout`, `/me`: HttpOnly session cookie; POST/PUT/PATCH/DELETE browser requests require a configured Origin.
* `/v1/projects`: create/list; `/v1/projects/{id}`: view/rename/delete.
* `/{id}/documents`: multipart upload/list; `/{id}/documents/{doc}`: inspect extracted chunks/delete.
* `/{id}/jobs`: list; `/{id}/jobs/{job}/retry`: requeue failed ingestion.
* `/{id}/pipeline`: inspect/update validated settings; `/{id}/reindex`: rebuild.
* `/{id}/query`: question, optional conversation_id; returns answer, citations, retrieved chunks, refusal, latency and conversation ID. `/{id}/query/stream` emits sources, answer deltas and done via SSE after validated generation.
* `/{id}/conversations`: dashboard-owned history. API keys cannot read dashboard conversations.
* `/{id}/keys`: create/list/revoke scoped keys (raw secret once).
* `/{id}/usage`, `/status`, `/manifest`: real counters, state and exportable configuration.
* `/{id}/evaluation/cases`, `/generate`, `/runs`: labeled cases, explicitly unverified synthetic cases, measured runs.
* `/{id}/widget`: explicit publication/revocation and appearance; `/v1/public/{id}/config` and `/query`: public query capability only. `/widget.js` embeds an isolated frame.

## Implementation sequence

1. Schema, migrations, auth, isolated project CRUD.
2. Validated upload, extraction, leased jobs, atomic indexing.
3. Retrieval, conservative grounded generation, citations, API key flow.
4. Working dashboard, pipeline controls, integration examples and widget.
5. Evaluation, deployment files, meaningful unit/integration/workflow verification.

## Retrieval and evaluation boundaries

Automatic defaults select hybrid retrieval, 180-word chunks and 30-word overlap; textual CSV uses 100-word chunks. This is a documented heuristic, not measured optimization. Hybrid uses reciprocal rank fusion of vector and full-text results; an evidence gate and sentence-level lexical check protect local refusals. Semantic retrieval with OpenAI is optional. Retrieved content is untrusted data, never instructions or executable code. Hosted generation must return source IDs and exact supporting quotes; unverifiable quotes are rejected. This validates provenance, not semantic entailment.

Evaluation reports document recall@k only for labeled relevant documents, hit@k, lexical relevance, exact-quote support, citation validity, refusal agreement and latency. Semantic faithfulness is **not assessed**; the UI explicitly labels quote support as a proxy. Synthetic questions remain separate from manually verified cases. Evaluations are bounded synchronous requests in this MVP.
