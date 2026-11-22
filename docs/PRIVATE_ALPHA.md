# Private-alpha onboarding

RAGForge is a tested private-alpha foundation for controlled developer trials. It is not production-certified or publicly launched. No external participants have been invited by this work. An operator must complete [the launch checklist](LAUNCH_CHECKLIST.md) and obtain authorization before inviting anyone.

## Hardware and installation

Use Python 3.12+, Node 24 (for local frontend development), Docker with Compose v2.24+ and Linux containers. Budget at least four CPU threads, 8 GB available RAM and 10 GB free disk for the hosted stack, builds and a standalone deployment; 16 GB host RAM is preferable when running both together. These are practical pilot recommendations, not measured minimum-capacity guarantees. The API/worker use a pinned CPU MiniLM model (about 91 MB); no GPU or paid model key is needed. First installation needs network access for images, packages and model files.

For a local demonstration, follow the root README: copy `.env.example` to `.env`, run `docker compose up --build -d`, then open http://localhost:3000. Development registration stays available. Keep real confidential data out of the development default configuration.

For the controlled HTTPS configuration, follow [OPERATIONS.md](OPERATIONS.md): initialize `.env.alpha`, start the overlay, bootstrap one administrator locally, and deliver an administrator-created invitation privately. The default HTTPS endpoint is **https://localhost:8443** with a local internal certificate. Trust its CA only after the operator verifies the certificate fingerprint. This configuration binds to loopback; reaching external pilot users requires an approved private network, hostname, trusted TLS and firewall change. None is provisioned automatically.

## First cited answer

1. Open the operator-provided HTTPS URL. Create an account using your private invitation code and a unique password of at least 12 characters. Invitations expire and work once. Contact the operator if yours is expired or revoked.
2. Choose **Create project** and give the collection a clear name. Upload `samples/acme-handbook.pdf` from this repository as a public demonstration fixture.
3. Wait for the document to become **ready**. Queued and processing are not success. Open the document to inspect extracted text/page locators. A failed job shows a safe error; repair the format and retry or replace the source.
4. In **Playground**, ask ?What is the refund period?? Expand the citation and confirm that its exact quotation appears in the PDF. Ask ?Who won the Martian election in 2050?? and check that it refuses unsupported claims.
5. In **Evaluation**, add a case with the expected source and answer. Generated cases remain unverified until a person reviews them. A passing sample case is a regression result, not product-wide accuracy.

Supported sources: selectable-text PDF, DOCX, UTF-8 TXT/Markdown and textual FAQ CSV. Default maximum is 20 MB/file and two million extracted characters. No OCR, arbitrary spreadsheet analytics, malware scanning or multimedia ingestion is provided. Remove secrets before upload. Exact quotations establish provenance; they do not establish truth or semantic entailment.

## API integration

In **API & Integration**, create a scoped project key. Copy it once into your application's secret store; it is not recoverable from the dashboard. Alpha keys expire after 30 days. Revoke and replace a lost/compromised key. Owner-only controls such as exporting are deliberately unavailable to project keys.

```python
import os, httpx
response = httpx.post(
    os.environ["RAGFORGE_URL"] + "/api/v1/projects/" + os.environ["RAGFORGE_PROJECT"] + "/query",
    headers={"Authorization": "Bearer " + os.environ["RAGFORGE_KEY"]},
    json={"question": "What is the refund period?"}, timeout=60,
)
response.raise_for_status()
print(response.json()["citations"])
```

Use a normally trusted HTTPS certificate; do not copy the QA scripts' localhost certificate bypass into integrations. The dashboard also supplies JavaScript/cURL examples and OpenAPI. Store keys on the server side, never in a public widget/browser bundle.

## Independent application

In **Deployment**, configuration-only export is the default. To copy knowledge, select **Include selected knowledge snapshot**, choose the intended ready documents, and acknowledge that delivered copies cannot be revoked. Download the ZIP, inspect its README/manifest, extract it into a new directory and run:

```sh
python scripts/init.py --port 8020
docker compose up --build -d
docker compose exec -T api python -m app.model_cache
```

Use its generated `.standalone-key` with `scripts/manage.py` or the bundled examples. The new database, source storage and key are independent of the hosted application. Protect the ZIP, `.env` and key. Rotation preserves the database password: `python scripts/init.py --rotate`, then recreate API/worker. New generator 1.1 keys expire after 90 days; downloaded 1.0 packages retain their original behavior. See [STANDALONE_EXPORT.md](STANDALONE_EXPORT.md) and [BACKUP_RESTORE.md](BACKUP_RESTORE.md).

## Troubleshooting and feedback

| Symptom | Next action |
|---|---|
| Invalid invitation / registration disabled | Request a fresh code from the operator; do not send the code in an issue. |
| HTTP 401 / expired session or key | Sign in again, or rotate the project/standalone credential. |
| HTTP 409 model/index mismatch | Restore the correct model settings or explicitly rebuild the full index. |
| Upload 413 / 429 / document quota | Inspect `/api/v1/account/quotas`; remove unused data or wait for active work. Repeated retries do not enlarge quotas. |
| DOCX/PDF processing fails | Check UTF-8/signature, encryption, archive expansion and selectable text. Extremely complex files may exceed parser CPU/memory/time limits. Split or simplify the source. |
| Model unavailable / readiness 503 | Operator checks diagnostics, cache checksums, storage and worker logs. No lexical fallback is silently used. |
| Refusal or wrong evidence | Inspect retrieval and citation text, record the question and sanitized source example privately, add a reviewed regression case. |
| Export expired / worker busy | Wait or generate a new export. Archives expire after one hour by default. |
| New standalone package fails parser containment | Use supported Linux containers/kernel with Landlock and seccomp; do not disable alpha containment to process untrusted documents. |

Report a sanitized reproduction using [the issue template](../.github/ISSUE_TEMPLATE/private-alpha.md). Include timestamp/timezone, request ID, runtime/version, status code and reproduction steps. Never attach keys, invitation codes, session cookies, passwords, full private files, or unredacted diagnostic/network traces. Use an operator-approved private channel for sensitive evidence.

## Five pilot tasks and measurement

A first-time developer completes these tasks without coaching beyond this guide:

| Task | Observable completion |
|---|---|
| 1. Install/sign in and create a project | Health reachable, authenticated project visible. |
| 2. Upload unfamiliar permitted documentation | Processing reaches ready; developer inspects extraction or diagnoses a real error. |
| 3. Ask two answerable questions and one unsupported question | Exact citations inspected; unsupported response assessed honestly. |
| 4. Create a scoped key and query outside the UI | External client receives the expected cited answer; unauthorized project access fails. |
| 5. Export and run an independent app | App starts on a separate port/database and answers with citations while the hosted API is unavailable. |

Use [PILOT_FEEDBACK.md](PILOT_FEEDBACK.md) per participant. Measure setup start/end, each task start/end/completion, errors, time to first cited answer and independent deployment, and reported difficulty (1 easy?5 hard). Record assistance and abandoned tasks. `pilot/measurements.json` starts empty; automated QA is not pilot participation. Do not prefill real results or infer participant satisfaction from automated tests.
