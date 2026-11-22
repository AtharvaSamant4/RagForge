# Private-alpha operations

The supplied configuration is a local/private-network starting point. It does not publish the service or buy infrastructure. Keep development and alpha Compose project names/volumes separate.

## Initialize and start

```sh
python scripts/init-alpha.py --file .env.alpha --origin https://localhost:8443
docker compose --env-file .env.alpha -p ragforge-alpha -f compose.yaml -f compose.alpha.yaml up --build -d
docker compose --env-file .env.alpha -p ragforge-alpha -f compose.yaml -f compose.alpha.yaml exec -it api python -m app.ops bootstrap-admin --email operator@example.com
```

The first command creates ignored settings with a random database password. The generated `RAGFORGE_ENV_FILE` points Compose API/worker to this private settings file, separating them from development `.env` provider credentials. Preserve that password; changing interpolation does not rotate an initialized PostgreSQL volume's password. The administrator command reads a password interactively, initializes at most one first administrator under a database lock, and never prints credentials. Operator CLI authority requires access to the application container/database. Restrict Docker membership and host access. Windows permissions inherit host ACLs; restrict `.env.alpha`, backup staging and operator secret directories explicitly.

Private alpha forces secure cookies, HTTPS trusted origins, invite registration, no public widgets, a 24-hour session and 30-day project keys. It rejects insecure origins/cookie settings at startup. Development's easy local registration is preserved in base Compose. `REGISTRATION_MODE=disabled` closes signup completely; change the alpha overlay and recreate API/worker to apply operator settings.

Sign in as the administrator and POST `{ "ttl_hours": 48 }` to `/api/v1/admin/invites` with the trusted Origin/session. Deliver the returned one-time code privately (maximum lifetime seven days); never place codes in URLs. DELETE `/api/v1/admin/invites/{id}` revokes unused codes. Project keys cannot administer invitations. No email-sending or external invitations are automatic.

## HTTPS and network boundaries

Caddy uses internal TLS at the configured hostname, HSTS for dedicated pilot hostnames (localhost is excluded to preserve HTTP development ports), a 21 MB request limit, header/body read deadlines and no access-log body capture. Its image is pinned by digest. The configuration was validated with `caddy validate` and exercised over local HTTPS. See [Caddy timeout options](https://caddyserver.com/docs/caddyfile/options#timeouts). The default proxy port is loopback 8443; API/web are also loopback (8040/3040), and PostgreSQL has no published port. Caddy's admin API is disabled.

For the local certificate, copy only the public CA certificate from `/data/caddy/pki/authorities/local/root.crt`, verify its fingerprint through a trusted operator channel, and trust it explicitly on pilot machines. Never distribute the CA private key. QA bypasses certificate verification for localhost only; real integrations must validate TLS.

Before external access, choose an approved private/VPN hostname, use a certificate trusted by the pilot devices, set the exact `ALPHA_ORIGIN`, and bind only the intended private proxy interface through a reviewed Compose override. Permit only pilot-network HTTPS and required operator SSH/VPN traffic; deny internet access to API/web/database ports. Confirm effective host/cloud/Docker firewall rules from another machine. No firewall or public DNS changes are made by setup. Do not trust arbitrary forwarding headers as client identity; the app uses direct peer IP for its limited auth/public budgets.

## Resources and persistence

| Control | Alpha default |
|---|---|
| User source + retained/reserved export storage | 256 MiB |
| Projects / documents per project | 10 / 50 |
| Active ingestion jobs per user / global processing claims | 4 / 2 |
| Active exports per user / deployment | 1 / 4 |
| File / extracted text / PDF pages | 20 MiB / 2 million characters / 500 |
| Upload requests per API process | 4; excess returns 429 |
| API key / user API budget | 60 requests per fixed minute (auth: 15/IP/minute) |
| Query text | 4000 characters |
| Parser wall / CPU / address space | 15 seconds / 10 seconds / 512 MiB |
| Hosted provider calls | Disabled; daily request ceiling 0 |
| Retained export lifetime / maximum archive | 1 hour / 80 MiB |
| API / worker / DB / web / proxy memory | 1 GiB / 1 GiB / 512 MiB / 512 MiB / 128 MiB |
| API / worker / DB CPU | 2 / 2 / 1 |

Owner-row writes serialize account allocations across projects, including SQLite; PostgreSQL advisory/row locks serialize global worker/export reservations. Export storage reserves the full maximum archive before accepting work. A full rebuild reserves one job per document; if the collection exceeds the configured queued-job cap, the operator must deliberately raise that cap (global processing remains bounded) or use a smaller collection. Ready export bytes replace that reservation; sources are not compressed into an advertised storage quota. `/api/v1/account/quotas` reports allocation. Database/index/model-cache disk overhead is not included in the user's source/archive quota; monitor the entire volume/filesystem separately. API request limiting uses atomic persisted minute buckets and is not a distributed gateway or adaptive fairness system.

Persistent named volumes hold PostgreSQL, sources, model cache, temporary exports and TLS material. API/worker roots are read-only, all capabilities are dropped, no-new-privileges and PID limits apply, and temporary files use a bounded 256 MiB tmpfs. Docker JSON logs rotate at 10 MB ? 3 files/service. Host disk and encrypted backup retention still need operator monitoring. Never use `down -v` for ordinary recovery.

## Diagnostics and safe logs

- `/health`: database liveness and public runtime/registration metadata; not readiness.
- `/ready`: 200 only when database/schema, recent worker heartbeat, model readiness, writable storage and required parser controls are healthy; otherwise 503. Public output is only the boolean.
- `/api/v1/admin/diagnostics`: administrator-session-only aggregate API counts, latency sums/maxima/buckets, query count/mean/max, ingestion success/failure/retry, export success/failure/retry, worker CPU/RSS/model/parser state, queue counts and provider usage. The CLI `python -m app.ops diagnostics` provides the same operator view.
- API responses include `X-Request-ID`; the streaming frontend forwarding route preserves cookies/authorization and returns safe 503/504 JSON with a request ID for upstream failures, with a 110-second deadline and no automatic mutation retry. Framework validation errors omit raw input/context. safe structured events record the request ID, route template, status and latency. No raw URLs/query strings, questions, bodies, credentials or source text are included. Third-party parser messages are discarded in the parser child. Do not enable request-body logging at a gateway.

Poll readiness and alert on sustained failure, stalled queued jobs, retry/failure growth, disk free space, RSS near limits and HTTP 429/5xx growth. The repository provides diagnostics, not a managed alerting service. Metrics are aggregate counters, not an external audit/compliance ledger; API histogram buckets are fixed and noncumulative. Background heartbeats continue while jobs run.

## Rotation and recovery

```sh
# Each command reads the new password interactively; rotation revokes sessions and project keys.
docker compose --env-file .env.alpha -p ragforge-alpha -f compose.yaml -f compose.alpha.yaml exec -it api python -m app.ops rotate-password --email developer@example.com
# Disable a compromised account and revoke its credentials:
docker compose --env-file .env.alpha -p ragforge-alpha -f compose.yaml -f compose.alpha.yaml exec -T api python -m app.ops disable-user --email developer@example.com
```

After a worker crash, restart that worker and inspect its durable job status. Jobs reclaim expired leases; claim tokens prevent stale output from publishing. Provider failures retry up to three attempts; parse/format failures require an explicit corrected-source retry. Alpha's normal lease is 300 seconds, exceeding the parser and individual hosted-call deadlines. Keep paid providers disabled until operator budget/timeout review. Maximum global processing claims prevent uncontrolled worker growth.

For a missing/corrupt model, prefetch the pinned cache with `python -m app.model_cache` in API/worker settings, then restart. It checks SHA-256 and does not silently use another model. `MODEL_LOCAL_FILES_ONLY=true` fails closed on missing files. For disk/full/database problems, stop admitting uploads, preserve volumes, inspect diagnostics and restore to a separate environment using [BACKUP_RESTORE.md](BACKUP_RESTORE.md). Migration `0004` is additive. Back up before upgrading, validate staging, and retain previous images/code; do not attempt a destructive automatic downgrade.

Hosted providers have atomic UTC-day request and input-character reservations and a 512-token response ceiling. Failed requests consume reservations. These are usage safeguards, not a dollar-denominated invoice cap. An operator must authorize keys/costs, set provider-side billing limits and consciously enable `HOSTED_DAILY_REQUESTS`/`HOSTED_DAILY_INPUT_CHARS`. No paid calls were executed for this milestone.

## Scheduled backup operation

Use an operator-owned scheduler on the Docker host to run `scripts/backup.py create` nightly during a documented maintenance window, supplying the passphrase through a protected secret-manager-to-stdin pipe. Require a successful encrypted artifact/checksum, copy it off-host, alert on failure, and test a restore regularly. For Windows Task Scheduler, invoke an operator wrapper with a dedicated service account; keep the passphrase out of task arguments and history. For systemd timers/cron, use the same wrapper and restrictive file permissions. A sample wrapper interface is `python scripts/backup.py create --project ragforge-alpha --env-file .env.alpha --compose-file compose.yaml --compose-file compose.alpha.yaml --file /private-backups/DATE.ragforge --allow-downtime --passphrase-stdin`. The wrapper provides stdin and a unique filename. Scheduling and off-host storage are intentionally not activated on this machine.
