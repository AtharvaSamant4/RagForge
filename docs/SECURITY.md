# Security boundaries and remaining work

RAGForge is a private-alpha foundation with executed security/reliability tests. It is **not production-certified**, a complete malware scanner, or an independently audited sandbox. Use a controlled private network and permitted test documents; complete the launch checklist before external invitations.

## Controls and trust boundaries

| Boundary | Implemented control |
|---|---|
| Accounts / tenants | PBKDF2-SHA256 passwords, HttpOnly/SameSite Strict sessions, trusted-Origin checks, project ownership/scopes before retrieval or file/export access, disabled-user checks. |
| Alpha enrollment | Invite/disabled modes, hashed one-time expiring/revocable tokens, serialized local first-admin setup, administrator-session-only diagnostics/invites. Development registration remains explicit. |
| Credential lifecycle | Alpha 24-hour sessions, 30-day project keys, password rotation/disable revoking sessions and keys; generated 1.1 keys expire after 90 days and rotate independently. No raw keys stored in DB/logs. Legacy nonexpiring keys remain valid until operator rotation. |
| Uploads | 20 MiB limit before extraction, bounded multipart/JSON bodies, four uploads/API process, UTF-8/signature checks, randomized paths, no uploaded code execution. DOCX rejects unsafe entries, excessive central directory/entry count, expansion and compression ratios before XML parsing. |
| Parser | Dedicated isolated Python child, stripped environment, private source/job directory, bounded input/output, CPU/memory/wall/output-file limits, safe error translation and kill-on-timeout. Linux alpha additionally requires tested Landlock filesystem and seccomp network/process restrictions. |
| Allocation | Account-row serialization, source/archive reservations, project/doc/job/export limits, PostgreSQL global claim/export locks, atomic persisted request and hosted-provider counters. |
| Generated applications | Fresh hashed independent credential, no signup/hosted sessions, private DB, loopback API, non-root/read-only services, explicit trusted template version, parser containment and collection limits. |
| Operations | HTTPS overlay/secure cookies, container CPU/memory/PID/tmpfs limits, bounded/rotated logs, IDs and safe metrics, health/readiness/admin diagnostics, encrypted consistent backup and empty-target restore guards. |

Authentication never accepts a project key for owner-only export or admin operations. Snapshots require source selection and explicit copy acknowledgment. Trusted compiler paths/configuration are fixed; source text, filenames and metadata are not interpolated into executable code. Only matching ready sources whose stored bytes pass identity/hash/size/symlink checks can be exported. Archives omit hosted credentials, vectors, accounts and history. Export copies are irrevocable once delivered; review/redact sources before sharing. Pattern-based credential detection is not general DLP.

Public widgets deliberately grant access to every ready source in the published project. The public token is a capability, not a private administrative key; Origin/CSP controls do not stop server-side callers who hold it. Tokens use URL fragments/Authorization headers, not query strings. Rotation/revocation disables previous embeds. **The alpha overlay disables publication and all public query/config/frame-policy access**, including previously published projects and disabled owners. Development keeps the tested opt-in widget.

## Parser containment actually tested

Linux parsing applies `RLIMIT_CPU`, `RLIMIT_AS`, `RLIMIT_FSIZE`, no core dumps and a parent wall deadline. Landlock grants reads only to runtime libraries and the temporary job directory, with writes restricted to that directory. A seccomp syscall deny policy blocks network creation/connect, process creation/exec, namespaces, mounts, ptrace and io_uring escape surfaces. The tested WSL kernel exposes Landlock ABI 1; mutation syscalls not covered by that ABI are also denied. A runtime probe verifies that an unrelated file, socket and process launch are blocked. Required controls fail closed when unavailable. CPU-loop, oversized allocation and timeout probes demonstrate process failure and subsequent valid-source recovery.

Windows development uses Job Objects with kill-on-close, CPU and aggregate memory limits. A two-process allowance is required for the venv Python launcher and interpreter. This is resource containment; Windows filesystem/network sandboxing is not claimed. Private-alpha deployment uses supported Linux containers. See [Linux Landlock](https://docs.kernel.org/userspace-api/landlock.html) and [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) for the underlying OS mechanisms.

This is an application-managed boundary with a shared host kernel, not protection against every kernel/parser vulnerability. Library reads, metadata visibility and allowed syscalls remain attack surfaces. No antivirus, PDF CDR, OCR or security certification is implemented. Use maintained kernels/images, encrypted host storage, dependency review and a private network. Stronger dedicated parser containers/VMs, independent review, fuzzing and malware scanning remain future work. Rejecting a complex but legitimate file at a resource limit is intentional; simplify/split the source.

## Retrieval, model and prompt boundaries

Model files/revision/checksums are pinned; no remote model Python is executed. Missing/corrupt artifacts fail without lexical fallback. Model identity/dimensions/index generation must match in every retrieval strategy; stale workers cannot publish into a newer generation. Embedding caches are bounded, identified by model+text hash, and expose aggregate counters only. Authorization still precedes any retrieval.

Documents are untrusted data. The local extractive provider selects source sentences; hosted generation has no tools, explicit untrusted-source boundaries and exact-quote validation. Quote presence establishes provenance, **not truth or entailment**. Numeric-time qualification, a narrow conflict detector and instruction-request filtering address observed cases, not arbitrary prompt injection or all misleading retrieval. Sensitive uses require human judgment. Development fixtures and AI-proposed candidate labels are not independent proof of product-wide accuracy.

## Logging, retention, secrets and recovery

API validation errors omit submitted input/context, including passwords and sensitive questions. The frontend streams to a fixed configured API and returns safe identified 503/504 responses on transport failure; mutations are not automatically retried. Alpha settings are loaded from their own private env file. Ordinary logs contain controlled event names, error types, request IDs, route templates, statuses and timings; request/response bodies, raw URL/query strings, passwords, keys, invitations, source text and questions are excluded. Parser stdout/stderr and uncontrolled third-party messages are suppressed/redacted. Operator diagnostics are aggregate and administrator protected. Debugging/network traces and generated ZIPs can contain data; restrict them and redact before sharing.

Deleting a document removes source/index/job state and clears retained project query/conversation/evaluation-run content that could contain its excerpts. Backups and already delivered copies require separate operator retention/deletion procedures. A crash between source-file creation and DB commit can leave an orphan file; reconciliation is an operator procedure, not a destructive automatic sweeper. User storage quotas cover source and retained/reserved archive bytes, not all physical DB/index/cache overhead. Monitor host disk and control retention of history, metrics and backups. Full legal/audit retention controls are not implemented.

Backups authenticate encrypted bundles before use and refuse restores to the original/nonempty target. They exclude raw credentials and sessions; separate secret-vault recovery is required. Environment secrets remain in restricted host files/container environment; managed secrets, at-rest volume encryption and automated off-host copies are operator responsibilities. No paid model call or public deployment was performed.

## Before broader exposure

Complete an independent security review/penetration test, dependency and image vulnerability review, stronger parser isolation/malware controls, managed identity/reset/verification/SSO as needed, provider-side spend caps, monitored backup scheduling/off-host retention, private-network firewall/TLS validation and incident-response ownership. There is no managed alerting, high availability, general semantic safety guarantee or public-production approval. See [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md).
