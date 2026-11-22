# Implementation progress

## Current milestone

Milestone 3 is implemented on `feat/standalone-rag-export`, based on verified Milestone 2 commit `f574709`. It is not merged into main. The original MVP and Milestone 2 services/data remain separate. The export QA source stack is `ragforge-m3`, dashboard 3030/API 8030; generated applications use independent Compose projects and ports 8020/8021.

## Completed functionality

* Preserved semantic/lexical/hosted adapters, retrieval/evaluation framework, accounts, project isolation, keys, uploads/jobs, citations, widgets and existing regression coverage.
* Versioned deterministic application compiler, approved trusted-template catalog, frozen self-contained retrieval components, validated manifests, pinned dependencies/base images and model revision. No LLM-generated executable code.
* Configuration-only default and explicitly approved selected-source snapshots. No hosted account/session/key/history/vector data or provider secrets are copied. Generated apps initialize their own database/index and fresh credentials.
* Owner-only durable export jobs, progress/status/download, source/hash/symlink/path protections, secret-pattern checks, archive/source/storage/concurrency bounds, retention and interrupted-job/orphan cleanup.
* Deployment UI with mode/selection/disclosure/configuration summaries, job recovery, progress, download/checksum and startup instructions; desktop/mobile screenshots inspected.
* Independent PostgreSQL/pgvector API/worker runtime, loopback binding, health checks, persistent volumes, resource limits, authenticated query/config/status/import/reindex/retry/delete, durable ingestion and restart-safe snapshot import/deletion.
* Generated README plus Python, JavaScript, cURL and PowerShell examples; setup/security/architecture/export documentation and independent startup CI coverage.

## Executed verification

* Hosted backend on Docker PostgreSQL: **72 passed**. Windows SQLite: **70 passed, 2 expected PostgreSQL-only skips**.
* Export/compiler/compiled-runtime cases cover deterministic bytes, selection/tenant/credential boundaries, malformed input, malicious filenames/paths/symlinks, missing/changed source/cache, size/retention/reservation limits, lease recovery, model incompatibility, new credential initialization/rotation, disabled imports and persistent snapshot deletion.
* Frontend TypeScript and optimized production builds passed, including real Docker images.
* Real Chromium desktop/mobile full workflows both passed, including both export modes and actual ZIP downloads: `qa/export-browser-results.json`. Four archives passed CRC checks and matched the current template fingerprint.
* The initial real snapshot Docker acceptance passed: valid sample-PDF citations with the isolated source stack stopped, wrong/missing credential rejection, three known before/after cases, persistent citations after restart, separate database/vector index and Python/JavaScript/cURL clients. The final browser-downloaded snapshot also passed against the current template: `qa/standalone-runtime.json`.
* The browser-downloaded configuration-only app starts empty, refuses unsupported questions, removes failed PDFs, imports/queries a new source, preserves its index/citations after restart and owns its own PostgreSQL database. Evidence: `qa/standalone-imports.json`.
* Initial browser/PostgreSQL attempts overlapping an image replacement were discarded and rerun after startup. Docker test discovery was corrected to include repository pytest configuration. One upstream Starlette TestClient deprecation remains; ONNX may emit a nonfatal device-ID persistence warning in read-only containers.
* No public deployment, paid model calls or merge into main occurred. The requirement audit is in MILESTONE3_AUDIT.md. Delivery is restricted to the feature branch.

## Limits and next priority

Generated deployments are single-collection APIs, without hosted accounts/dashboard/history/widget/evaluation UI. Source copies cannot be revoked after download. Initial dependencies/images/model downloads require network access; no fully offline fresh installation is claimed. Credential scans are not general DLP; review source content. Exact quotes and a three-question regression do not establish entailment, general semantic equivalence or customer-data accuracy. Hosted adapters have no live paid-provider verification.

Public exposure still needs HTTPS, parser isolation, monitoring, backups/restore drills, stronger quotas and managed secrets. No Kubernetes/cloud provisioning, billing, OCR, multimedia, analytics, fine-tuning or agent framework was added. Existing Milestone 2 benchmark evidence remains at its verified baseline, with unverified candidate labels explicitly separate. Next priorities are human benchmark review, production hardening and explicit reviewed template/dependency upgrades.
