# Standalone application export

Milestone 3 is built on the verified Milestone 2 commit `f574709`, on `feat/standalone-rag-export`. It adds an application compiler. The exported application contains its own source and dependencies; it never imports this repository or calls a RAGForge server at runtime.

## Export a project

In **Deployment → Export standalone application**, review the active model and pipeline. Configuration-only is the default: no uploaded documents are included. It produces a complete empty API with documented import/rebuild commands.

For a knowledge snapshot, select specific ready documents and explicitly approve copying them. Anyone who receives the ZIP can read those files. Deleting a source, account or project in RAGForge cannot revoke already downloaded copies. Review sources for sensitive content before approving them. Conversation history, sessions, existing API credentials, provider secrets, unrelated documents and hosted vectors are excluded. The generated app builds a new index from the selected source bytes.

Click **Export standalone application**. A durable worker validates and packages trusted components while the API continues serving requests. The panel shows queued/generating/ready/failed/expired states, included-source/configuration summaries, instructions, archive size and checksum. Download the ZIP when ready. Reloading Deployment recovers the most recent job.

## Run the downloaded project

Extract into its own directory. Requires Docker/Compose v2.24+ with Linux containers and Python 3.12+. From the extracted directory:

```sh
python scripts/init.py
docker compose up --build -d
docker compose exec -T api python -m app.model_cache
```

Initialization writes a fresh random API key to `.standalone-key` and its hash plus an independent random database password to `.env`. Both are ignored by Git and Docker build context. No fixed production credentials ship. POSIX secret files have mode 0600; restrict directory ACLs yourself on Windows. Each initialization chooses a unique Compose project name. For another copy use `python scripts/init.py --port 8021`; do not reuse another deployment's `.env`.

The API binds to loopback at http://localhost:8020. `/health` is public; all `/v1/*` endpoints require `Authorization: Bearer <new standalone key>`. PostgreSQL has no published port. The API, worker, database and persistent volumes belong to this new Compose project. `docker compose down` preserves its data; do not remove volumes unless intentionally deleting it.

First builds/downloads require internet access for base images, pinned Python packages and about 91 MB of pinned MiniLM artifacts. The README does not claim a fully offline fresh installation. After prefetch, `MODEL_LOCAL_FILES_ONLY=true` disables model downloads and missing/corrupt files produce clear errors. API and worker share the persistent model cache but each has its own in-memory inference session.

## Contents and versioning

The ZIP contains `app/main.py`, retrieval/embeddings/generation/models/security packages, a frozen `app/engine` component bundle, `config/manifest.json`, selected `data/knowledge` files, initialization/client scripts, functional tests, a pinned dependency lock, Dockerfile, Compose, environment example, ignore files and a generated README. It includes unused ORM definitions from the reviewed component bundle but no hosted rows or account APIs.

Current generator `1.1.0` uses data-only validated configuration and an approved template catalog. No LLM generates executable code. The manifest records schema/generator version, template SHA-256, model identity/revision/dimensions/pooling, retrieval settings, import capability and selected-source checksums. Archive order, timestamps, modes and configuration serialization are deterministic; repeated exports of the same inputs/templates are byte-identical. New template versions do not silently modify previously downloaded applications. A template change while a job is queued fails visibly and requires a new export.

## API and import

| Endpoint | Behavior |
| --- | --- |
| `GET /health` | Public minimal process health; startup waits for schema initialization |
| `GET /v1/status` | Authenticated model/index state and document processing/error/timing metadata |
| `GET /v1/config` | Sanitized active model, pipeline, generator identity and import capability |
| `POST /v1/query` | `{"question":"..."}` → grounded excerpts, exact citations/source locators, retrieved passages, refusal/qualification and timing |
| `GET/POST /v1/documents` | List/import supported files; imports can be disabled at export |
| `DELETE /v1/documents/{id}` | Remove an unwanted/failed source; removed snapshots stay removed after restart |
| `GET /v1/jobs` | Durable ingestion jobs with status, attempts and safe errors |
| `POST /v1/jobs/{id}/retry` | Explicitly retry failed work after repairing its cause |
| `POST /v1/reindex` | Controlled full rebuild with compatibility gates and cancellation of stale work |

The generated README includes Python, JavaScript, cURL and PowerShell examples. With its pinned dependencies installed in a local venv:

```sh
python scripts/manage.py status
python scripts/manage.py import /path/to/document.pdf
python scripts/manage.py query "What is the refund period?"
python scripts/manage.py reindex
node scripts/example.mjs
```

Use the venv's Python executable, or activate it first. Set `--url` on the Python client and `STANDALONE_URL` for JavaScript if changing the port. Default supported formats/limits match the hosted parsers: selectable-text PDF, DOCX, UTF-8 text/Markdown and textual FAQ CSV; 20 MB/file, 100 files, 2 million extracted characters/file. Numeric CSV analytics, OCR and multimedia are outside scope.

Edit pipeline configuration in `config/manifest.json`, rebuild/restart the image, then explicitly rebuild the index. Models default to the exported profile; deployment environment overrides may select the existing semantic/local/hosted adapters. Restart **both** API and worker after a provider change and rebuild the full index. Model identity and dimension checks block mixed/incompatible vectors. Semantic artifacts are pinned; changing them requires a reviewed new component/template version. Schema v1 uses 384-dimensional pgvector storage; another dimension needs an explicit operator migration or separate database. Hosted adapters need new operator-supplied credentials, may bill usage and send supplied text externally; live paid calls are not part of verification.

Restart-safe initialization imports snapshots by checksum without duplicating them. Ingestion uses leases, retries, generation/profile checks and transactional index publication. Schema version is persisted; unrecognized future schema versions fail rather than guessing an upgrade. Runtime/API-key rotation instructions preserve the database password and data.

## Hosted export API and bounds

Owner session only: `POST /v1/projects/{id}/exports`, list `GET .../exports`, status `GET .../exports/{job}`, download `GET .../exports/{job}/download`. Project API keys cannot export, even with document scope. Snapshot requests require `mode=snapshot`, selected `document_ids` and `acknowledge_copy=true`; configuration-only forbids selected documents. `allow_imports` controls generated import endpoints. Downloads include an archive SHA-256 header.

Defaults: 100 MB selected-source bytes, 80 MB archive, 512 MB reserved/retained artifact budget, four active export jobs globally, one active job/project, at most two retained archives/project and one-hour retention. Archives may expire sooner under new exports/storage pressure. Temporary build files are also accounted for; interrupted leftovers are swept after ten minutes, and orphan archives after project deletion are removed by cleanup. Export records expire from storage, with failed/expired metadata removed after a day. The API and worker share the export volume. Tune `EXPORT_DIR`, `EXPORT_MAX_SOURCE_MB`, `EXPORT_MAX_ARCHIVE_MB`, `EXPORT_STORAGE_MB` and `EXPORT_RETENTION_SECONDS` for local operations. Ordinary database/storage backups must protect this volume too.

## Security and production operation

Archive paths are compiler-assigned, never derived from display filenames. Entries are regular files, without absolute paths, `..`, backslashes or drive prefixes. Source reads reject symlinks/reparse points, require safe storage identifiers and verify size/hash/open-file identity. Project metadata goes into JSON, not executable templates, shell commands or Compose interpolation. Known server provider credentials, private-key markers and high-confidence API-key patterns are checked. This is not general DLP or source-document redaction; approve source content deliberately.

Standalone services run as non-root users with read-only application filesystems, bounded request/upload sizes, worker leases, CPU/memory/PID settings and persistent writable runtime volumes. Default memory limits are API 768 MiB, worker 1 GiB and PostgreSQL 512 MiB; inference uses two threads/process. Operators can tune resources through `.env`. Multiple workers require PostgreSQL. A single deployment key grants all documented API capabilities; distribute it only to trusted clients.

For HTTPS hosting, put a maintained reverse proxy in front of loopback, configure TLS/certificate renewal, bounded bodies/timeouts and firewall access, and keep PostgreSQL private. Generator 1.1 adds tested isolated/resource-limited parsing, collection limits, provider budgets and operational counters. Consistent encrypted standalone recovery is supported by the repository backup tool. Managed secrets, stronger isolation/malware controls and independent security review remain operator/future work before broader exposure. No public infrastructure is provisioned by export. Exact citation provenance does not prove entailment, eligibility or general contradiction resolution. The English encoder and small regression comparison do not establish general semantic equivalence or customer-data accuracy.

## Verification and measurements

The implementation plan and acceptance protocol are in MILESTONE3_PLAN.md. The mandatory acceptance test exports `samples/acme-handbook.pdf`, starts the generated project from an isolated directory, verifies its own PostgreSQL vector index, compares three known question/refusal/citation results, stops only the isolated source RAGForge stack without deleting volumes, queries successfully again, restores the source stack and tests standalone restart/persistent citations.

Reproduce against an isolated source deployment on ports 8030/3030:

```sh
python scripts/verify-standalone.py --stop-source ragforge-m3 --output artifacts/standalone-acceptance.json
```

The script deliberately restricts source shutdown to named QA Compose projects. It never stops the existing MVP/Milestone 2 stacks or removes volumes. Exact executed results and performance observations are recorded with the final verification evidence; no cold-build or accuracy claims should be inferred from warm caches.

## Executed final results

The actual desktop browser download was extracted into its own temporary directory and run with the generated instructions. It returned the 30-day refund rule with exact `acme-handbook.pdf` citations while the isolated `ragforge-m3` source API/database/worker/web were stopped. The source API was required to be unreachable. It continued after standalone restart with unchanged citation chunk IDs. Python, JavaScript and cURL clients and missing/wrong credentials were executed. Source services were restored without deleting volumes.

The separately downloaded mobile configuration-only ZIP ran at port 8021, initially had no documents and refused unsupported questions. It removed a failed PDF, imported a new team document, queried its 25-day leave fact and preserved its index/citations after restart. Both deployments have different Compose project names, volumes, documents and keys; each rejects the other's credential and the second refuses the refund question. Raw evidence: [snapshot runtime](qa/standalone-runtime.json), [configuration-only runtime](qa/standalone-imports.json), [cross-app isolation](qa/standalone-isolation.json), [browser results](qa/export-browser-results.json).

| Snapshot measurement | Observed value |
| --- | --- |
| Worker ZIP-generation time | 198.86 ms |
| ZIP size | 40,816 bytes |
| Compose build/start, cached dependency layers | 28.696 s |
| Prefetch/init, new persistent model cache | 28.804 s |
| API cached-file model init after restart | 1848.73 ms |
| PDF indexing / embedding | 233.13 / 201.54 ms |
| Three sequential query latencies | 1134.16, 25.80, 28.99 ms |
| Container memory after restart/queries | API 216.6 MiB; worker 189.3 MiB; PostgreSQL 26.06 MiB |

The first query includes API model initialization; later questions benefit from warm state/cache. Configuration-only Compose build/start took 88.811 s and prefetch/init 57.782 s in its separate run. Docker dependency layers were warm: the first local dependency build was seeded from previously downloaded Linux wheels through an optional build secret after very slow PyPI traffic. The exported Dockerfile still defaults to normal PyPI and CI performs an independent build. Model files were not bundled in either ZIP; each deployment downloaded its own pinned cache. Timings include local host contention, and memory/CPU are point-in-time observations, not peaks or capacity guarantees. There is no fully offline fresh-install claim.

Final regression matrix: **72 PostgreSQL tests passed; 70 SQLite tests passed with 2 expected skips; both desktop/mobile Playwright workflows passed**, plus frontend TypeScript/production Docker builds and restored-host smoke tests. One upstream TestClient deprecation and a nonfatal ONNX read-only device-ID warning remain. See [requirement audit](MILESTONE3_AUDIT.md).

To rerun the exact browser-artifact acceptance after the browser suite:

```sh
python scripts/verify-standalone.py --archive artifacts/browser/desktop-snapshot.zip --comparison artifacts/browser/desktop-export-before.json --stop-source ragforge-m3 --output artifacts/standalone-ui-runtime.json
python scripts/verify-standalone-imports.py --archive artifacts/browser/mobile-configuration.zip --output artifacts/standalone-imports.json
```

These tests leave their own generated deployments/volumes for inspection. Run `docker compose stop` in a generated directory to stop only that copy while preserving its data. Existing unmodified MVP/Milestone 2 stacks are not stopped by the source-shutdown flag.


## Milestone 4 compatibility and recovery

New exports use generator 1.1.0 and standalone schema state version 2 (additive budget/metrics/worker tables). Template hashes remain explicit; old downloaded 1.0 packages are not silently modified. Linux Compose requires Landlock/seccomp parser controls; CPU/memory/wall failures are bounded. New keys expire after 90 days and rotate without changing the DB password. Source storage/document/active-job/request limits are enforced; hosted daily calls default to disabled. Full reindex reserves one job/document, so an operator must raise the queue cap deliberately when a larger collection exceeds it; concurrent processing stays bounded.

The new runtime was executed independently with the M4 source stack stopped and after restart, with matching before/after citations. Encrypted database/source backups were restored into a separate empty deployment using the original package/manifest and a fresh target key. Both old generator 1.0 applications on local QA ports 8020/8021 still authenticate and answer/refuse honestly. See [m4-standalone-acceptance.json](qa/m4-standalone-acceptance.json), [m4-standalone-recovery.json](qa/m4-standalone-recovery.json) and [BACKUP_RESTORE.md](BACKUP_RESTORE.md). No public deployment or paid model call occurred.
