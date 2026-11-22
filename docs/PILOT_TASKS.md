# Five standardized developer tasks

Use permitted unfamiliar documentation for a real authorized trial. Automated verification uses public samples and is labeled engineering QA. Record setup start/end separately; begin the task timer or enter actual elapsed seconds. Every task records completed/failed/abandoned/not-started, seconds, error count, assistance-request count, difficulty 1 easy to 5 hard, and optional feedback. The participant form is Workspace → Pilot study after enrollment and voluntary consent.

Difficulty begins unrated, rather than preselecting a favorable or neutral response. Attempted tasks require an explicit 1–5 choice. Not-started tasks may remain unrated (`difficulty: 0`, `difficulty_recorded: false` in the report). Operators should arrange client-side unavailability of the hosted API for task 5; participants must not stop a shared deployment used by other trials.

| Task | Instructions | Evidence to inspect |
|---|---|---|
| 1. Create and upload | Create a clearly named project; upload one supported document; wait for ready or diagnose the failure. | Participant can explain queued/processing/ready/failed; extraction and index actually exist. |
| 2. Ask and inspect | Ask two answerable questions and an unsupported question; inspect exact source quotations and locators. | Person assesses whether evidence answers the question; refusal is assessed honestly. Quotes alone do not establish truth or entailment. |
| 3. Integrate the API | Create a scoped key and query with the supplied Python or JavaScript example outside the playground. | The external client authenticates and receives the intended response; record any assistance and key errors without copying secrets into feedback. |
| 4. Export | Choose configuration or a permitted knowledge snapshot, acknowledge copied data, generate and download the ZIP. | Export is ready and the manifest/README are inspected. Download is not deployment. |
| 5. Run independently | Initialize a fresh key and Docker project from the ZIP, run it separately and obtain a cited answer while the hosted API is unavailable to that client. | Actual authenticated standalone response and inspected citation; record startup/model-download failures. Optional offline evidence is separate from human assessment. |

For optional deployment telemetry, explicitly enable offline evidence while exporting. Query the independent API, then run the package's `scripts/pilot-evidence.py` and explicitly upload its JSON in Pilot study. No automatic callback occurs. Its export-bound signature demonstrates self-hosted runtime evidence; it is not remote attestation or proof a person performed the work unaided. The measured deployment interval includes evidence-import delay.

Operators should avoid coaching beyond the prepared guide. If help is requested, provide it and record the amount rather than silently counting unaided completion. Review all five submitted outcomes, including failures. Ask what was confusing, what was useful, and whether/why the participant would use the product again. Do not infer satisfaction from technical success or fabricate comments.
