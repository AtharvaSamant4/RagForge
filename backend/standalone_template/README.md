# Standalone knowledge application

This generated application is an independent copy. It never calls the original RAGForge server. Its PostgreSQL database, document storage, model cache and deployment credentials are new. `config/manifest.json` records the generator/template/model identities, pipeline and included source checksums. No hosted accounts, conversation history, existing keys, cookies or provider secrets are included. Source documents in this archive are readable by anyone who receives it. Deleting the original document does not revoke exported copies.

## Start

Requires Docker with Compose v2.24+ (Linux containers), Python 3.12+ for credential initialization, and approximately 2–3 GB available memory for the configured limits. From this extracted directory:

```sh
python scripts/init.py
docker compose up --build -d
docker compose exec -T api python -m app.model_cache
```

The first build downloads images and Python dependencies. Semantic mode downloads approximately 91 MB of pinned MiniLM files from Hugging Face. The model is Apache-2.0, revision `d13954661f83248295ba75c1ed411eef3b7b936e`; checksums are verified by the bundled engine. A shared persistent model volume avoids repeated downloads. Do not claim offline operation until you have prefetched files and verified your deployment with external networking disabled. `MODEL_LOCAL_FILES_ONLY=true` prevents model downloads and reports missing/corrupt cache errors without fallback.

The API binds only to `127.0.0.1:8020`. API docs: http://localhost:8020/docs. `/health` is public; all `/v1/*` endpoints require a fresh Bearer key stored in `.standalone-key`. Initialization creates a random database password and unique Compose project in `.env`. Do not commit either secret file. Windows uses inherited filesystem ACLs; restrict access to your extracted directory. For another independent copy, initialize with `python scripts/init.py --port 8021` before startup. Do not reuse another deployment's `.env` or Compose project name.

`docker compose ps` checks service health. `docker compose logs worker` shows safe job status. Snapshot imports are queued on startup; wait for ready documents before expecting evidence. Restarting does not duplicate imports, discard state or create new credentials. `docker compose down` preserves volumes; do not use `down -v` unless you intend to destroy that deployment's data.

## Query and inspect

Python (install the pinned dependencies in a local venv first):

```sh
python -m venv .venv
# POSIX: .venv/bin/python; Windows: .venv\Scripts\python.exe
.venv/bin/python -m pip install -r requirements.lock.txt
.venv/bin/python scripts/manage.py status
.venv/bin/python scripts/manage.py query "What is the refund period?"
node scripts/example.mjs
```

cURL, POSIX shell:

```sh
curl http://localhost:8020/v1/query -H "Authorization: Bearer $(cat .standalone-key)" -H 'Content-Type: application/json' -d '{"question":"What is the refund period?"}'
```

PowerShell:

```powershell
$standaloneKey=(Get-Content .standalone-key -Raw).Trim()
Invoke-RestMethod http://localhost:8020/v1/query -Method Post -Headers @{Authorization="Bearer $standaloneKey"} -ContentType application/json -Body '{"question":"What is the refund period?"}'
```

Results include exact quotes, source names/page locators, retrieved passages, refusal/qualification and measured latency. Empty collections and unsupported questions refuse honestly. Quote provenance is not proof of semantic truth or entailment.

## Import, rebuild and recover

Configuration-only exports start empty. If imports were enabled at export:

```sh
.venv/bin/python scripts/manage.py import /path/to/document.pdf
.venv/bin/python scripts/manage.py status
.venv/bin/python scripts/manage.py reindex
```

Supported: selectable-text PDF, DOCX, UTF-8 TXT/Markdown, textual FAQ CSV. Default limits: 20 MB/file, 100 documents, 2 million extracted characters/file. No OCR or arbitrary CSV analytics. `/v1/jobs` reports durable ingestion, retries and errors; POST `/v1/jobs/{id}/retry` retries a failed job after its cause is repaired. DELETE `/v1/documents/{id}` removes an invalid or unwanted source and its index; a removed snapshot is not automatically re-imported on restart. Explicitly uploading its bytes again restores it. Failed parsing is never reported as ready. Workers renew leases and replace index rows transactionally.

Pipeline settings live in `config/manifest.json`. After editing them, rebuild the image (`docker compose up --build -d`), then explicitly POST `/v1/reindex`. Provider settings default to the exported profile; operator overrides in `.env` can select `semantic`, `local` or configured `openai`. Restart both API and worker, then rebuild the entire index. Incompatible/mixed vectors are blocked with HTTP 409. Vector schema v1 is fixed at 384 dimensions; a different dimension requires an explicit reviewed database migration or a separate generated deployment. Semantic revision and pooling are pinned in the engine; changing model artifacts requires a new reviewed template version. Hosted providers require your own server-side credentials, may incur charges, and transmit supplied text. They are not tested through paid calls.

New deployment keys expire after 90 days. Rotate the API key with `python scripts/init.py --rotate`, then `docker compose up -d --force-recreate api worker`; the database password is preserved. Resource limits and threads are configurable through `.env` (`API_MEMORY`, `WORKER_MEMORY`, `DB_MEMORY`, `*_CPUS`, `EMBEDDING_THREADS`, `EMBEDDING_BATCH_SIZE`, `EMBEDDING_CACHE_SIZE`). Defaults allocate 768 MiB API, 1 GiB worker and 512 MiB database, with two inference threads/process. Large documents and competing load can require tuning.

Run the functional test against the active deployment with `.venv/bin/python -m pytest tests`. It checks authentication and quote provenance; it does not claim a general accuracy score.

## Deployment and limitations

The generated app is a single-collection API, not the hosted multi-user dashboard. It has no account management, conversations, widget, evaluation UI or public hosting. All holders of its deployment key can query and, if enabled, import documents/rebuild. Keep that key private. Put a maintained reverse proxy with HTTPS, authentication controls and bounded request bodies/timeouts in front of the loopback API when deploying; configure firewall/network access and trusted certificate renewal yourself. Never expose PostgreSQL. This milestone does not provision public infrastructure.

Content is untrusted. Generator `1.1.0` adds a private parser subprocess with Linux Landlock filesystem restrictions, seccomp network/process restrictions, 15-second wall time, 10-second CPU time and 512 MiB address-space limits. The generated Compose configuration requires these Linux controls and fails parsing closed if unavailable. Read-only roots, non-root processes, four simultaneous uploads/process, 20 MB files, 512 MB source storage, 100 documents and 20 active ingestion jobs are additional defaults; the worker claims at most four jobs globally. Limits are operator configurable. Hosted calls default to disabled (`HOSTED_DAILY_REQUESTS=0`); enabling them requires explicit provider credentials and budget review. Credentials expire and can be rotated; no account signup exists.

These controls are tested failure containment, not malware scanning, an independently certified sandbox, general prompt-injection protection or production certification. Use an approved Linux kernel/runtime and review dependencies. Schema state version 2 adds operational counters and provider-budget tables without dropping existing source/index tables. Retain this exact package/manifest, image identities and separate environment secrets with your encrypted backups. The repository's `scripts/backup.py --kind standalone` supports a consistent database/source backup and refuses restores except into another empty deployment of this package; see `docs/BACKUP_RESTORE.md` in RAGForge. Backup tools and encryption dependencies belong on the operator host. Generated apps do not require a running RAGForge server.

Previously downloaded generator `1.0.0` packages remain independent and are not silently upgraded. Review template/dependency/model upgrades explicitly. This ZIP freezes its template hash and model revision; editing the manifest does not upgrade trusted engine code.
