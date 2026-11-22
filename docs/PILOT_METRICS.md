# Pilot metric and evaluation contract

## Activation funnel

Collection requires operator enrollment plus unexpired participant consent. Events are server-generated and transactionally deduplicated; clients cannot submit arbitrary funnel events. The participant has a 10,000-event cap, visibly marked when reached; capped records cannot support complete activity statistics. Retries and duplicate evidence imports do not count the same operation twice.

Each participant can retain five task outcomes, 50 private problem reports and 50 unexpired deployment tickets. These limits supplement the unchanged M4 request/storage/job/export quotas. Public-widget visitor activity is excluded from participant telemetry, and ONNX Runtime vendor telemetry is explicitly disabled before model sessions.

| Stage | What is actually observed |
|---|---|
| Account activation | An authenticated enrolled account opts in. This is study activation, not the earlier signup/install timestamp. |
| Project creation | A project commits after consent. |
| First document upload | Validated upload/source/job commits. Acceptance is not successful indexing. |
| Successful indexing | A current worker lease publishes ready chunks. |
| First cited answer | A saved private answer has citations and is not refused. |
| API key creation | A new scoped credential commits; no secret is in the event. |
| External API query | Successful project query using a project-key principal. This identifies programmatic credential use, not a physical remote client or human coding. |
| Standalone export | The archive worker publishes a ready archive, not a browser download or deployment. |
| Independent startup | User imports a valid unexpired export-bound signed runtime observation from an authenticated standalone API with initialized DB. |
| Successful standalone query | Imported runtime observation records a non-refused cited query. |

Primary time-to-first-cited-answer uses server-observed opt-in study activation and first cited answer. The report also provides separately named intervals from the existing account-creation timestamp, only after consent, so signup/consent delays are visible rather than silently excluded. Other pre-consent activity is not backfilled. Time-to-observed-deployment uses server receipt of signed evidence and includes manual import delay. Runtime-supplied boot/query clocks are checked for plausibility, but are not authoritative duration clocks. Package owners can inspect/modify signing code and keys; this is self-hosted evidence, not remote attestation. A ZIP download never completes either deployment stage.

The dashboard separates engineering QA from human participants, technical events from self-reported outcomes, and operator-attested real participation from both. Query latency there is answer-service time; use controlled HTTP measurements for end-to-end/P95 transport costs. Counts include accepted/rejected uploads, processing/query/export failures and resource/quota rejections, with no error bodies. Operational safety logs/aggregate metrics remain separate from opt-in study analytics.

## Independent quality evaluation

Four distinct result groups: synthetic development fixtures; explicitly human-approved existing candidates; independent holdout labels; actual pilot queries separately approved for evaluation. The 120 proposed labels remain unverified until a real authorized human reviews them. No human/holdout/pilot score exists for an empty split.

The frozen MiniLM/hybrid configuration is unchanged. Use `review.py list --pending --limit 10` and `review.py next` to inspect the complete source and proposed answer; correct/reopen/approve/reject retain reviewer/timestamp/checksum history. Never batch-approve labels through automation.

For permitted unfamiliar Markdown/TXT sources (TXT is normalized to Markdown), prepare proposed case JSON using the existing `source_refs`, exact `expected_quotes`, `question`, `id` and `expect_refusal` contract. Source filenames must be simple and unique. Use a private/ignored output directory:

PDF, DOCX and textual CSV can first use the existing isolated parser through `python benchmarks/normalize_source.py --file /private/handbook.pdf --output artifacts/private-inputs/handbook.md --permitted-data`. TXT/Markdown are also supported. Inspect the normalized text to choose exact evidence, and retain the permitted original for human inspection. The original/normalized checksum sidecar is carried into the dataset review view; normalization is extraction, not label approval or semantic verification.

```sh
python benchmarks/datasets.py --source-dir /private/unfamiliar-docs --labels /private/proposed-cases.json --output artifacts/private-holdout --kind independent_holdout --provenance 'Actual source/permission provenance' --permitted-data --not-used-for-tuning
python benchmarks/review.py next --dataset-dir artifacts/private-holdout
# A real reviewer inspects/corrects labels and records individual approvals:
python benchmarks/review.py approve --dataset-dir artifacts/private-holdout --id CASE_ID --reviewer 'Actual reviewer' --notes 'Original sources and expected evidence checked'
python benchmarks/evaluate.py --split holdout --dataset-dir artifacts/private-holdout --output artifacts/private-holdout-results.json
```

For pilot queries use `--kind pilot_queries`, per-case `participant_approved_for_evaluation: true` plus a private `participant_approval_reference`, then the same review process and `--split pilot-approved`. General telemetry consent does not grant permission to copy private questions/documents into evaluation. Obtain explicit permission and sanitize the chosen material separately. These evaluation files/results contain questions/source excerpts by design and are private study artifacts, not analytics exports; do not commit them publicly. Delete them under the agreed policy or participant request.

Import creates **unverified proposals only**. Source checksums, frozen configuration and latest review history are validated before evaluation. Holdouts cannot reuse development documents/questions or tune parameters through the evaluation CLI. The unused-for-tuning attestation remains a human responsibility; file tooling cannot prove an operator never saw or tuned against labels. Source changes require a new dataset/version and renewed review.

Report retrieval hit/recall/MRR, exact citation provenance, expected-quote coverage, refusal contracts and cold/warm latency separately. Exact provenance is not semantic entailment or product-wide accuracy. See BENCHMARKS.md for the preserved M2/M4 evidence and M5 controlled performance results after execution.
