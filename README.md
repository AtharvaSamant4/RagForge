# RAGForge

A working foundation for turning documents into private, tested knowledge APIs: FastAPI, Next.js/TypeScript, PostgreSQL/pgvector, durable ingestion, cited answers and an embeddable assistant.

The default runs without external AI credentials. Local feature-hashing embeddings match vocabulary and extractive generation returns exact supporting sentences. These are real retrieval and grounding implementations with limited semantic capability. OpenAI embedding and Responses adapters are available when explicitly configured. No paid calls are needed for the demo or tests.

## Start with Docker

Requires Docker Engine/Desktop with Compose v2.24+ and Linux containers.

```sh
cp .env.example .env
docker compose up --build
```

On Windows PowerShell use `Copy-Item .env.example .env` for the first command. Open **http://localhost:3000**. API documentation: **http://localhost:8000/docs**. The API applies Alembic migrations before startup; the worker starts after the API is healthy. PostgreSQL uses pgvector HNSW and GIN full-text indexes. Data and uploads persist in named volumes. `docker compose down` stops services and keeps data. Do not remove volumes unless you intend to delete data.

Change the example PostgreSQL password and review [security requirements](docs/SECURITY.md) before changing loopback bindings or exposing this system to the internet. This repository has not been publicly deployed.

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

Sample PDF/DOCX files can be recreated with `.venv/bin/python scripts/create_samples.py`.

## Verification

```sh
.venv/bin/python -m pytest
npm --prefix frontend run typecheck
npm --prefix frontend run build
# With the app and worker running:
.venv/bin/python scripts/smoke.py
```

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

Use a **fresh database and re-upload sources** when changing embedding provider/model/dimensions; vectors from different models are incompatible and the database vector dimension is fixed at migration time. Generation provider changes do not require reindexing. Advanced retrieval and chunk settings are editable per project in **Pipeline**. Changed chunk settings require **Rebuild index**.

## Scope and limitations

Supported: selectable-text PDF (up to 500 pages), DOCX paragraphs/tables, UTF-8 TXT/Markdown and textual/FAQ CSV. Default file limit: 20 MB; extracted text limit: 2 million characters; 100 projects/user, 100 files/project, 50 eval cases/project. There is no OCR, multimodal ingestion, arbitrary CSV analytics, reranker, semantic optimization claim, standalone code-package export, public cloud deployment, SSO or billing. Conversation history is persistent but questions retrieve independently. SSE sends validated answer deltas after generation rather than native model token streaming. Evaluation is synchronous and bounded.

This is a foundation for production work, not a claim of production readiness. See [security limits](docs/SECURITY.md), [API contracts](docs/API.md) and [design decisions](docs/ARCHITECTURE.md). Branding is configurable with `BRAND_NAME`; the dashboard reads it from the backend.
