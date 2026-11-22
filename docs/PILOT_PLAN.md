# Controlled developer pilot plan

Purpose: learn whether an unfamiliar developer can create, test, integrate and independently deploy a useful RAG application without direct assistance. Engineering automation is preparation, not evidence of human usability or adoption. No external participant is authorized or contacted by repository setup.

## Proposed cohort and learning targets

Approximately five authorized developers, subject to user approval. Proposed learning targets: four complete document-to-cited-answer; three integrate an API without direct engineering assistance; three independently run an export; no critical isolation/security incident or unexplained data loss. Record failures/incomplete tasks and whether participants would use the product again. These are proposed learning targets, not approved commitments or statistically significant market validation.

## Before starting

1. Obtain explicit user authorization for each named participant and contact channel; retain the reference privately. Do not treat a GitHub login, signup, technical event or operator checkbox as external authorization by itself.
2. Assign an incident owner and a private reporting channel. Agree permitted non-sensitive documents, consent, retention, deletion and handling of exported copies. Explain the implementation's limitations in SECURITY.md and PRIVATE_ALPHA.md.
3. Verify private/VPN networking, trusted hostname/TLS, firewall restrictions, strict Linux parser readiness, backup/restore, alerts, rotated credentials and disabled paid providers on the actual target host. Record actual checks in the operator panel. The local loopback configuration does not prove a pilot machine can reach a safely configured deployment.
4. Use M4 administrator-controlled invitations only after authorization. Enrollment does not send invitations or create accounts. In Pilot study, an administrator records the existing account, the authorization reference and the **human** cohort. Reserve **engineering QA** for explicit disposable automation; QA cannot be reclassified in place or counted as real trials.
5. Ask each participant to read the notice and opt in themselves. Optional telemetry/feedback is off before consent, with no retrospective backfill. Declining or withdrawing does not prevent normal application use. Do not opt in a real participant on their behalf through automation.

## During the study

Use [the five tasks](PILOT_TASKS.md) in order. Record setup separately, then task status, elapsed seconds, errors, assistance, difficulty and optional feedback in the participant panel. Leave unsuccessful tasks unsuccessful; neither citations nor API calls prove a person finished the task unaided. Operators review private task feedback separately from the technical funnel and manually attest actual participation only after checking all five outcomes, including failed/abandoned/not-started tasks.

Monitor the restricted operator dashboard: accepted/rejected uploads, indexed/failed processing, query service latency/errors, API-key queries, export success/failure, observed runtime evidence and quota errors. The default dashboard/report is the human cohort; QA has a separate selector. Inspect readiness/disk/queues/5xx/429 alerts through OPERATIONS.md. An alerting service is not provisioned automatically.

## Privacy, retention and ending

Pilot analytics contain pseudonymous participant IDs, fixed event kinds, timestamps, hashed operation identities and bounded numeric timings. They exclude document text, filenames, questions, API keys and passwords. Normal RAG document/conversation storage and safe aggregate operational logs are separate existing product functions; opting out of the study does not erase normal project content.

Enrollment and study records expire after 30 days (consent begins a fresh 30-day period). Worker cleanup runs every minute; reads/writes also enforce expiry. A participant can withdraw to erase live events, task feedback, problems and deployment tickets, or delete enrollment as well. Proof-bearing hosted exports are expired and their hosted evidence keys removed. In-flight temporary archives are discarded before publication; files left by a crashed worker age out under the existing ten-minute orphan cleanup. Already delivered packages/copies are not remotely revocable. Delete documents/projects separately for normal RAG data deletion.

Private free-text feedback is available only to administrators and the submitting participant's task view. Default report downloads omit it, email and authorization references. Issue text requires a separate manual sanitation/review step before its download; automatic filters cannot detect all confidential prose. Do not publish reports or create public GitHub issues without authorization.

Default hosted RAG recovery backups omit pilot tables, operator attestations and ephemeral export state so recovery cannot resurrect old consent. Save only separately authorized sanitized study reports in an operator-controlled private location, enforce the same retention, and delete downloaded copies when requested. Existing older encrypted backups age out under the operator policy; no secure-erasure claim is made. Windows file ACLs need explicit operator review. A recovered deployment requires fresh enrollment/consent and target-host attestations.

At study end, review every reported issue, record failures and assistance, export the sanitized report if authorized, close or disable pilot access as agreed, erase/expire study and approved evaluation copies, and retain only the authorized aggregate learning record. No automatic email, publication or participant contact occurs.

An administrator can honor an authorized deletion request for an unavailable/disabled participant with `DELETE /api/v1/admin/pilot/participants/{participant_id}` using the trusted administrator session/Origin. This erases study data and evidence, including hosted proof-bearing archives, while preserving normal projects/account access. Account disabling/revocation is a separate M4 operator action; record the request privately and never post participant identifiers in a public issue.

## Issue triage

| Severity | Examples and response |
|---|---|
| Critical | Cross-tenant exposure, credential leak, active security incident or unrecoverable data loss: stop affected trials, preserve minimal private evidence, involve incident owner immediately. |
| High | Setup/API/export blocked, reproducible incorrect retrieval affecting the task, major degradation: investigate before expanding the pilot. |
| Medium | Workaround exists; repeated UX confusion or intermittent performance: schedule and link engineering work. |
| Low | Minor usability problem or feature request: retain evidence and prioritize from actual needs. |

Use categories security, data loss, retrieval, API, export, setup, performance, UX and feature. Operator status progresses new → investigating → scheduled/resolved/closed, with an internal engineering reference. Severity is operator-reviewed, not assigned from participant sentiment. The private feedback form and [issue template](../.github/ISSUE_TEMPLATE/private-alpha.md) capture reproductions. Download the separately operator-reviewed JSON before any authorized issue creation; never automatically post confidential input to the public repository.

## Review path

Preserve the stack: main → [M2/M3 draft PR #1](https://github.com/AtharvaSamant4/RagForge/pull/1) → [M4 draft PR #2](https://github.com/AtharvaSamant4/RagForge/pull/2) → [M5 draft PR #3](https://github.com/AtharvaSamant4/RagForge/pull/3). Review each delta against its immediate parent; do not merge automatically. Verified code, execution receipts and the remaining human gates are recorded in [the M5 audit](MILESTONE5_AUDIT.md).
