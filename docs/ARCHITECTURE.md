# RAGForge architecture and implementation plan

## Decisions

One FastAPI backend owns authentication, projects, uploads, retrieval, evaluation and public access. A Next.js App Router dashboard uses same-origin `/api` forwarding. The browser never sees provider credentials. Branding comes from server configuration.

PostgreSQL + pgvector is the Docker deployment target. SQLite with exact vector scoring is a deliberately small local development alternative. Default local embeddings now use a pinned MiniLM ONNX model on CPU. Original normalized feature-hashing vectors remain available as `EMBEDDING_PROVIDER=local` for baseline comparisons. Local answers quote supporting sentences. OpenAI embedding and Responses adapters are opt-in and never silently replace a failed provider with local output.

Use a **database-backed durable job queue**, rather than Redis: ingestion state and enqueue are committed together, eliminating the DB/broker dual-write failure. PostgreSQL workers claim with `FOR UPDATE SKIP LOCKED`; SQLite supports one worker. Leases recover interrupted jobs. Extraction runs outside the claim transaction; atomic replacement of chunks occurs only after success. Retry is bounded, errors remain inspectable, and explicit retries are supported. Redis can be introduced when measured throughput justifies it.

The versioned application compiler now creates independent source packages from an approved template catalog and frozen retrieval component bundle. Owner-only export jobs capture validated configuration and explicitly selected ready sources, verify source bytes, publish bounded deterministic ZIPs through a shared export volume, and expire retained artifacts. No vectors, account/session/key records or history are copied. Generated apps initialize their own PostgreSQL schema, API key and durable ingestion pipeline; they never import the hosted repository or contact its services. See STANDALONE_EXPORT.md.

## Data model

Users own projects (tenant boundary); sessions are hashed opaque secrets. Every document, chunk, job, API key, query record, conversation, evaluation case and evaluation run has a project ID. Project APIs resolve authorization before looking up child resources. API credentials carry explicit `query`, `read`, and `documents` scopes. Widget tokens only grant public query access, require explicit publication and allowed embedding origins, and do not grant history or management access.

Documents have validated display names, random storage paths, SHA-256 content hashes, processing state, extracted metadata, chunk count and safe error codes. Chunks preserve page/section/row locators and source offsets. PostgreSQL uses a 384-dimensional vector column, HNSW index and GIN full-text index. Project pipeline configuration is versioned per job. Changes to chunk settings require explicit reindexing; retrieval settings apply immediately. Same-dimension provider changes use controlled project generations with compatibility gates and transactional replacement; source files are preserved. A different storage dimension requires a separate database or an explicit operator migration. See SEMANTIC_MODELS.md.

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

First-upload semantic defaults use hybrid on PostgreSQL and vector on SQLite, based on the authored fixture benchmark; they are not globally optimal claims. Word defaults remain 180/30 (CSV 100/15), with an additional 256-token cap for MiniLM. Hybrid uses weighted reciprocal rank fusion, explicit semantic gates and compatible model identities. Answer evidence uses semantic sentence matching in MiniLM mode and lexical matching in baseline mode. Retrieved content is untrusted data, never executable instructions. Hosted generation must return source IDs and exact supporting quotes; unsupported paraphrases and incorrect attributions are rejected. Quote validation establishes provenance, not truth or entailment.

Evaluation reports document recall@k only for labeled relevant documents, hit@k, lexical relevance, exact-quote support, citation validity, refusal agreement and latency. Semantic faithfulness is **not assessed**; the UI explicitly labels quote support as a proxy. Synthetic questions remain separate from manually verified cases. Evaluations are bounded synchronous requests in this MVP.
