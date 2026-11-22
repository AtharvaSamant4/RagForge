# RAGForge

A working foundation for turning documents into private, tested knowledge APIs: FastAPI, Next.js/TypeScript, PostgreSQL/pgvector, durable ingestion, cited answers and an embeddable assistant.

The default runs a real pretrained **all-MiniLM-L6-v2** model on CPU through ONNX Runtime: 384 dimensions, pinned weights/tokenizer, Apache-2.0 model license, and persistent model caching. Answers quote supporting source text. Lexical feature hashing remains available for baseline comparisons; OpenAI adapters are opt-in. No paid calls are needed for the demo, benchmarks or tests.

Milestone 3 builds on verified Milestone 2 commit `f574709`, on `feat/standalone-rag-export`; neither feature branch is merged into `main`. **Deployment → Export standalone application** generates a complete independent Dockerized knowledge API. See [standalone export](docs/STANDALONE_EXPORT.md), [measured Milestone 2 benchmarks](docs/BENCHMARKS.md), [browser QA](docs/BROWSER_QA.md), and [model/index compatibility](docs/SEMANTIC_MODELS.md).

## Current developer-pilot milestone

Engineering preparation is verified; external participation remains pending. See [the M5 audit](docs/MILESTONE5_AUDIT.md), [machine readiness](pilot/readiness.json) and [stacked draft PR #3](https://github.com/AtharvaSamant4/RagForge/pull/3).

Milestone 5 on `feat/developer-pilot-validation` builds on verified M4 `04f6ef2`. It adds optional consent-aware activation telemetry, a restricted pilot dashboard, private task feedback/triage, offline signed standalone evidence and independent dataset review/import tooling. Engineering QA is separate from human results. Real participants, human label approvals and external trials remain pending explicit authorization and operator gates. See [pilot plan](docs/PILOT_PLAN.md), [tasks](docs/PILOT_TASKS.md), [metric definitions](docs/PILOT_METRICS.md), [results/readiness](docs/PILOT_RESULTS.md) and [the M5 plan](docs/MILESTONE5_PLAN.md). New exports use generator 1.2.0; downloaded older packages remain unchanged.

For Windows Docker Desktop local HTTP API clients, use `127.0.0.1` rather than `localhost` when connecting to the explicitly IPv4-only published ports. The measured unpublished `::1` fallback added about two seconds per new connection. HTTPS clients must retain and validate the approved certificate hostname; see [the latency investigation](docs/BENCHMARKS.md). No quotas or TLS checks were relaxed.

## Verified private-alpha baseline

Milestone 4 on `feat/private-alpha-hardening` builds on verified M3 `c73d99f`. It adds tested parser containment, invitation controls, atomic quotas/budgets, credential rotation, diagnostics, encrypted recovery and an HTTPS/resource-limited private-alpha overlay. It is not production-certified or publicly launched. Existing downloaded standalone apps remain independent; new exports use reviewed template version 1.1.0.

Start with [private-alpha onboarding](docs/PRIVATE_ALPHA.md), [operator setup](docs/OPERATIONS.md), [backup/restore](docs/BACKUP_RESTORE.md), [security limits](docs/SECURITY.md) and [the launch checklist](docs/LAUNCH_CHECKLIST.md). No real pilot participation, human benchmark approvals, independent holdout score or external invitations are claimed. M3's draft PR is [#1](https://github.com/AtharvaSamant4/RagForge/pull/1); it is not merged.

For M4 development QA beside existing stacks, use a separate project with `API_PORT=8031`, `WEB_PORT=3031`, `APP_ORIGINS=http://localhost:3031`, then `docker compose -p ragforge-m4 up --build -d`. The older M2/M3 port examples below describe their historical isolated verification stacks; preserve those volumes rather than reusing their names for a new deployment.

## Start with Docker

Requires Docker Engine/Desktop with Compose v2.24+ and Linux containers.

```sh
git clone --branch feat/developer-pilot-validation https://github.com/AtharvaSamant4/RagForge.git
cd RagForge
cp .env.example .env
docker compose up --build
```

These commands select the current unmerged milestone; omit cloning when already in that checkout. On Windows PowerShell replace `cp .env.example .env` with `Copy-Item .env.example .env`. Open **http://localhost:3000**. API documentation: **http://localhost:8000/docs**. The API applies Alembic migrations before startup; the worker starts after the API is healthy. PostgreSQL uses pgvector HNSW and GIN full-text indexes. Data and uploads persist in named volumes. `docker compose down` stops services and keeps data. Do not remove volumes unless you intend to delete data.

Change the example PostgreSQL password and review [security requirements](docs/SECURITY.md) before changing loopback bindings or exposing this system to the internet. This repository has not been publicly deployed.

The first semantic startup downloads about 91 MB of pinned model/tokenizer files. The worker initializes the model before claiming jobs; initial uploads may remain queued during this download. The shared `model_cache` named volume survives restarts. For explicit prefetch after startup:

```sh
docker compose exec api python -m app.model_cache
```

After prefetch, set `MODEL_LOCAL_FILES_ONLY=true` for offline operation. A missing or corrupt cache produces a visible provider error; there is no silent lexical fallback.

To run the feature branch beside the existing MVP without changing its data, use a separate Compose project and ports (PowerShell):

```powershell
$env:API_PORT='8010'
$env:WEB_PORT='3010'
$env:APP_ORIGINS='http://localhost:3010'
docker compose -p ragforge-m2 up --build -d
```

Open http://localhost:3010. This is the isolated stack used for milestone verification. Its volumes are separate from `ragforge`.

Milestone 3 export verification uses a further isolated source stack, leaving both existing stacks/data in place:

```powershell
$env:API_PORT='8030'
$env:WEB_PORT='3030'
$env:APP_ORIGINS='http://localhost:3030'
docker compose -p ragforge-m3 up --build -d
```

Open http://localhost:3030, upload the sample, then use **Deployment → Export standalone application**. Choose configuration-only or explicitly select/approve sources. Extract the ZIP elsewhere, run `python scripts/init.py`, then `docker compose up --build -d` from that directory (use a fresh terminal without the source stack's port overrides). It binds to port 8020 and uses new credentials/volumes. See [the complete export workflow and security limits](docs/STANDALONE_EXPORT.md).

## Start locally without Docker

Requires Python **3.12** and Node.js **24**. Run every backend command from the repository root so database/upload paths and `.env` resolve consistently.

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock.txt
Copy-Item .env.example .env
cd frontend
npm.cmd ci
cd ..
.\scripts\start-local.ps1
```

Open http://localhost:3000. To stop the recorded processes: `.\scripts\stop-local.ps1`. Logs are under `data/`. Run the start script only once per session; stop existing services before restarting.

Alternatively use three terminals (all from repository root; on Windows replace `.venv/bin/python` with `.venv\Scripts\python.exe` and set `$env:PYTHONPATH='backend'`):

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock.txt
cp .env.example .env
npm --prefix frontend ci
.venv/bin/python -m alembic -c backend/alembic.ini upgrade head
```

```sh
# Terminal 1
PYTHONPATH=backend .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
# Terminal 2
PYTHONPATH=backend .venv/bin/python -m app.worker
# Terminal 3
npm --prefix frontend run dev
```

SQLite is configured by default and supports one worker. PostgreSQL is required for multiple workers. There is no Redis dependency: the durable database queue commits jobs and document state together. See [architecture and decisions](docs/ARCHITECTURE.md).

Optional local prefetch from the repository root: set `PYTHONPATH=backend` (PowerShell: `$env:PYTHONPATH='backend'`) and run `.venv/bin/python -m app.model_cache` with the platform-appropriate Python path. `MODEL_CACHE_DIR` defaults to `data/models`. Limit CPU inference with `EMBEDDING_THREADS` (default 2) and `EMBEDDING_BATCH_SIZE` (default 32).

To retain the original lexical behavior, set `EMBEDDING_PROVIDER=local` before starting both API and worker. Semantic mode is the default for new deployments. Existing source files, users, keys and projects are preserved by migration `0002`.

## Demonstrate the complete workflow

1. Create an account with a password of at least 12 characters, then create **Acme Knowledge**.
2. Open **Documents** and upload `samples/acme-handbook.pdf`. Wait for **ready**. If it stays queued, start the worker and inspect its logs. Click the document to inspect extracted page-labeled chunks.
3. Open **Playground** and ask **What is the refund period?** Expect an answer quoting the **30 day** period with citations. Expand a source and enable **Show retrieval** to inspect the evidence.
4. Ask **Who won the Martian election in 2050?** Expect a refusal without citations.
5. In **API & Integration**, create a key. Copy it immediately, set `RAGFORGE_API_KEY`, and run the Python, JavaScript or cURL example from [API documentation](docs/API.md). Keys can be revoked and are project scoped.
6. In **Evaluation**, add a verified question with the PDF selected as its relevant source, then run evaluation. It computes actual document recall, quote provenance, refusal agreement and latency. Generated candidate questions are explicitly unverified and excluded by default. No semantic faithfulness score is claimed.
7. In **Deployment**, optionally enable a public widget, add your embedding website's exact origin, and copy the new embed script. Every ready source becomes queryable through this capability. Saving rotates the token; disabling revokes it. Localhost URLs work only for local testing; external hosting requires an operator deployment and HTTPS.
8. Delete the PDF, then ask the refund question again. The source is gone from retrieval and the answer is refused. Deletion also clears cached project history and evaluation run outputs so they do not retain deleted passages.
9. To demonstrate failure handling, upload a malformed file starting with `%PDF-1.7`. It is accepted for processing but visibly fails parsing. **Retry** reruns the stored file; a corrupt source should be deleted and re-uploaded after repair. Retry also recovers transient provider failures after server configuration or connectivity is fixed. Genuine failures never appear as ready.

For a semantic example, upload `benchmarks/corpus/returns.md` and ask **“Can I send something back after two weeks?”** The assistant retrieves the 30-calendar-day return policy and gives a qualified source-based response. It does not assert that an individual return is eligible. **Pipeline** shows the pinned active model, dimensions, index generation, compatibility, CPU/cache settings and a comparison of all three retrieval strategies.

Sample PDF/DOCX files can be recreated with `.venv/bin/python scripts/create_samples.py`.

## Verification

Prefetch the real model before backend tests. The first command below uses POSIX environment syntax; on PowerShell set `$env:PYTHONPATH='backend'` and `$env:EMBEDDING_PROVIDER='semantic'`, then run the same module with `.\.venv\Scripts\python.exe`.

```sh
PYTHONPATH=backend EMBEDDING_PROVIDER=semantic .venv/bin/python -m app.model_cache
.venv/bin/python -m pytest
npm --prefix frontend run typecheck
npm --prefix frontend run build
# With the app and worker running:
.venv/bin/python scripts/smoke.py
# Real desktop + mobile browser workflows; start the app first:
npm --prefix frontend exec playwright -- install chromium
npm --prefix frontend run test:e2e
# Fixture contracts and all 120 unverified benchmark candidates:
.venv/bin/python benchmarks/run.py --candidates --output benchmarks/results/local.json
```

Browser tests default to the Milestone 4 isolated development stack at port 3031. Set `QA_BASE_URL=http://localhost:3000` to test the default stack instead. The Playwright external-widget fixture opens port 4020 on loopback for the duration of each test. Test accounts and their data are disposable; successful workflows remove their projects. Browser failures may leave only their own fixture projects in the QA database.

Real-model backend tests require the pinned local cache; prefetch with `python -m app.model_cache` first. These tests use local inference, not mocked semantic vectors. The test suite continues to exercise the original lexical path as a regression baseline.

The tests run real parsers, embedding, retrieval, authentication, evaluation and index deletion against an isolated temporary database. They also cover tenant/project boundaries, scoped keys, revocation, unsafe uploads, numeric CSV rejection, job retries and lease recovery, pipeline changes, widget publication, SSE and persisted rate limits. Provider HTTP mocks are confined to adapter tests; no external API calls are made.

For PostgreSQL tests set `TEST_DATABASE_URL` to a **disposable** database before pytest. The test fixture clears tables in that database. Never use a live application's database. [Progress and executed verification](docs/PROGRESS.md) records which checks actually ran.

## Optional hosted models

Set these environment values and restart both API and worker:

```dotenv
EMBEDDING_PROVIDER=openai
GENERATION_PROVIDER=openai
OPENAI_API_KEY=your-server-side-key
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_MODEL=your-responses-compatible-model
EMBEDDING_DIMENSIONS=384
```

Choose a Responses-compatible model available to your account. The [embedding API](https://developers.openai.com/api/reference/resources/embeddings/methods/create) supports dimensions for third-generation embeddings; the [Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create) supplies structured grounded claims. Adapters use exact source quote validation and never silently downgrade a failed hosted request. Uploaded text is sent to the configured provider in hosted mode; usage may be billable. No provider credentials are included.

When switching embedding providers or model identity at the same dimension, restart **both API and worker**, open each project's **Pipeline**, and click **Rebuild index**. Incompatible projects return HTTP 409 for every retrieval mode, including keyword search, until the controlled rebuild finishes. Old source files are retained and chunks are replaced transactionally. Superseded jobs cannot publish stale output. Failed rebuilds remain blocked until repaired/retried or the failing source is removed.

pgvector's column dimension is fixed by the initial migration. A different dimension requires a separate database or an explicit operator-managed vector-column/index migration; the app rejects the mismatch and does not delete data. MiniLM specifically requires 384 dimensions. Generation provider changes do not require reindexing. Chunk setting changes require **Rebuild index**.

## Scope and limitations

Supported: selectable-text PDF (up to 500 pages), DOCX paragraphs/tables, UTF-8 TXT/Markdown and textual/FAQ CSV. Default file limit: 20 MB; extracted text limit: 2 million characters; 100 projects/user, 100 files/project, 50 eval cases/project. Standalone exports generate a single-collection API with its own database, worker, API credentials and optional selected source snapshot; they do not clone the hosted dashboard/accounts/history/widget. There is no OCR, multimodal ingestion, arbitrary CSV analytics, reranker, semantic optimization claim, public cloud deployment, SSO or billing. Conversation history is persistent but questions retrieve independently. SSE sends validated answer deltas after generation rather than native model token streaming. Evaluation is synchronous and bounded.

This is a foundation for production work, not a claim of production readiness. Semantic similarity is not proof of answerability. Exact citations establish provenance, not truth or entailment; local responses remain source extracts with conservative qualifications. A narrow numeric-conflict check and instruction-request filter do not solve general contradiction detection or prompt injection. See [benchmark limitations](docs/BENCHMARKS.md), [security limits](docs/SECURITY.md), [API contracts](docs/API.md) and [design decisions](docs/ARCHITECTURE.md). Branding is configurable with `BRAND_NAME`; the dashboard reads it from the backend.
