# Encrypted backup and isolated restore

`scripts/backup.py` creates a consistent PostgreSQL/source snapshot while pausing only the explicitly named application's running API and worker. It resumes those services in `finally`. Expect a short maintenance outage; it does not stop other Compose projects or delete volumes. Run from the repository venv with the pinned dependencies and Docker-host authority.

## Contents and encryption

The bundle contains `database.dump` (`pg_dump -Fc`, no owners/ACLs), regular source files with their original storage identities and validated size/SHA-256, and a versioned manifest with component hashes, runtime configuration and Compose image identities. The database contains projects/pipelines, source metadata, vectors, evaluation/history state, password/key hashes and provider-budget state. Session credentials, rate buckets and transient worker-heartbeat data are excluded. Interrupted ingestion is queued on restore; hosted export jobs are expired because archives are not backed up.

The outer file uses streaming AES-256-GCM with authenticated header, random salt/nonce and a passphrase-derived Scrypt key (`N=32768,r=8,p=1`). Use a random secret with at least 20 characters, store it separately in the operator secret manager, and test its recovery. Authentication finishes before any archive entries are parsed or target services/data are touched. Wrong passphrases and tampering fail. A backup is limited to a 1 GiB plaintext bundle; encrypted input is bounded at 2 GiB. This is a private-alpha operational bound, not a large-scale backup system.

Not included: `.env`/database/provider passwords, raw API keys, backup/TLS private keys, model caches, exported ZIPs, application source/images, or host configuration. Keep the exact code/image identities and standalone ZIP/manifest separately. Restore environment/provider/database/TLS secrets from a separate vault; rotate exposed keys. Models must be prefetched and checksum-verified again. Source/database data is plaintext in runtime volumes and temporary backup staging; use host disk encryption, restrictive ACLs and a protected staging host. Temporary files are removed, but secure disk erasure is not claimed.

## Hosted backup

```sh
python scripts/backup.py create --project ragforge-alpha --env-file .env.alpha --compose-file compose.yaml --compose-file compose.alpha.yaml --file /private-backups/alpha-2026-11-22.ragforge --allow-downtime
```

The passphrase is requested securely. Automation can use `--passphrase-stdin`; never put it in a command argument, source file or ordinary log. The output reports only encrypted artifact size/hash and project identity. The destination must not exist. Transfer encrypted artifacts off-host, retain a documented number of copies, and keep decryption material separately. No remote storage or schedule is automatically created. See OPERATIONS.md for scheduling.

## Separate empty hosted restore

Create an explicit new Compose project with fresh DB credentials, distinct ports and empty volumes. Use the verified matching application images. Start **only its database** with `docker compose ... up -d --wait db`; do not start the API (which would migrate/create tables). Supply the new deployment's own interpolation environment/overlays to every command:

```sh
python scripts/backup.py restore --project ragforge-recovery --env-file .env.recovery --compose-file compose.yaml --compose-file compose.alpha.yaml --file /private-backups/alpha-2026-11-22.ragforge --allow-downtime --confirm-empty-restore
# Then start the restored services with the same project/env/overlays:
docker compose --env-file .env.recovery -p ragforge-recovery -f compose.yaml -f compose.alpha.yaml up --no-build -d
```

Choose a separate HTTPS port/hostname in `.env.recovery`; keep hosted model calls and public publication disabled. The tool refuses the source Compose project name, any preexisting public DB tables, nonempty source storage, mismatched backup kind and unsafe archive entries. It never drops a table/volume to make a restore possible. **Never aim restore testing at an active development or production database.** If an otherwise empty target suffers a mid-restore failure, leave it isolated, inspect the error and create another fresh recovery project; do not point at live data to retry.

Sign in again (sessions are not restored), verify owner/project access, compare source IDs/hashes/configuration/document counts, query an answerable and unsupported question, inspect exact citations, check `/ready`/diagnostics, and rotate credentials before any deliberate cutover. Existing project-key hashes/expiry may still validate if the raw key is held separately; restoration is not credential revocation. DNS/traffic cutover and external provider activation require explicit operator review.

## Standalone backup and restore

Use the original generated application's extracted directory and Compose project name from its private `.env`:

```sh
python scripts/backup.py create --kind standalone --directory /private/apps/original --project rag-EXPLICITNAME --file /private-backups/app.ragforge --allow-downtime
python scripts/backup.py restore --kind standalone --directory /private/apps/recovery --project rag-NEWNAME --file /private-backups/app.ragforge --allow-downtime --confirm-empty-restore
```

For the recovery directory, extract the **same original package**, initialize fresh credentials/port/project, build its matching images, and start only its empty database first. The tool checks that target `config/manifest.json` exactly matches the encrypted backup's manifest. Do not initialize/import application tables before restoring. Then start services, authenticate with the new deployment key, verify source/index/citations and test key rotation. Standalone credentials belong to the target environment, not the backed-up hosted accounts. Generator 1.0 and 1.1 runtimes remain independent; never mix a backup with an arbitrary newer template/schema.

## Executed evidence

The mandatory hosted workflow was executed from disposable `ragforge-m4-alpha` into a separate empty recovery deployment, most recently `ragforge-m4-restore-final`: new account/project, real PDF ingestion, cited answer, encrypted backup, source SHA-256 and exact citation identity/quotation comparison, external API-key query, excluded old sessions, wrong-passphrase rejection before writes and nonempty-target refusal. See [m4-hosted-recovery-load.json](qa/m4-hosted-recovery-load.json). Independent standalone recovery preserved matching source hashes and citations with a new target credential; see [m4-standalone-recovery.json](qa/m4-standalone-recovery.json). Both recovery workflows also run in CI. Backups are encrypted local artifacts; no secrets or private backup contents are committed to evidence.


Disposable QA scripts retain recovery passphrases/generated credentials in ignored local `artifacts/*secret*.json` and `artifacts/m4-private-credentials.json` for inspection/reproduction. These are outside the encrypted bundle but are not a production secret vault; Windows uses inherited ACLs. Do not distribute the artifacts directory or copy it wholesale as a backup. Real deployments must use a separate operator secret store. The backup CLI itself never automatically persists a passphrase.

## Milestone 5 pilot privacy

Hosted RAG backups omit the data in all six pilot tables, operator attestations and ephemeral export rows. They preserve RAG users/projects/documents/indexes/configuration/keys, while preventing restored snapshots from reviving old study consent or evidence keys. Re-enroll, obtain fresh consent and reverify target-host operator controls after recovery. Keep separately authorized sanitized study exports privately under the agreed retention/deletion policy; these are not implicitly recovered by the RAG backup. Standalone backups still require the original package/manifest; optional evidence signing configuration remains part of that protected package, not a hosted credential.
