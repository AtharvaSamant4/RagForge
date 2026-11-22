# Milestone 3 plan

Base: verified `f574709`, branch `feat/standalone-rag-export`. Preserve the running original and Milestone 2 stacks and all volumes.

1. Freeze trusted, self-contained retrieval components and a versioned standalone template. Generate a deterministic ZIP with a validated manifest and selected source bytes; no hosted credentials, history or index is copied.
2. Prove the vertical slice in an isolated Compose project: initialize fresh credentials, build, independently ingest the sample PDF, query citations, stop only the isolated source RAGForge stack, query again, and restore it.
3. Add owner-only asynchronous export jobs, source selection/confirmation, resource reservations, retention/cleanup and a Deployment UI with progress and download.
4. Exercise configuration-only imports, multiple apps, untrusted paths, secrets/tenant boundaries, failures, restart/persistence, model incompatibility and artifact integrity. Measure actual export/build/startup/index/query/memory behavior.
5. Run existing SQLite/PostgreSQL suites, frontend checks/builds, real desktop/mobile export workflows and CI. Document authoritative evidence, commit and push this feature branch only.

Standalone contract: loopback API, its own PostgreSQL/pgvector and persistent storage, pinned CPU MiniLM, durable worker, API-key authentication, status/config/query/document import/reindex/retry endpoints. It has no dependency on the hosted server and no hosted dashboard/accounts/history/widget. Internet is needed for initial dependency/image/model downloads; offline operation is not claimed without a network-isolated test.
