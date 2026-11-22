"use client";

import { useEffect, useState } from "react";
import { api, download } from "./api";

type Stage = { stage: string; completed: boolean; observed_at: number | null };
type Funnel = {
  stages: Stage[];
  time_to_first_cited_answer_seconds: number | null;
  time_to_observed_standalone_deployment_seconds: number | null;
};
type Member = {
  enrolled: boolean;
  participant_id?: string;
  cohort?: string;
  consented_at?: number | null;
  expires_at?: number;
  notice: string;
  funnel?: Funnel;
  tasks?: Task[];
};
type Task = {
  task_number: number;
  status: string;
  duration_seconds: number;
  errors: number;
  assistance: number;
  difficulty: number;
  feedback?: string;
};
type Report = {
  cohort: string;
  activated_participants: number;
  operator_attested_real_trials: number;
  technical_events: Record<string, number>;
  query_latency_ms: {
    count: number;
    median: number | null;
    p95: number | null;
  };
  participants: ({ participant_id: string; reported_tasks: Task[] } & Funnel)[];
  issues: { id: string; category: string; severity: string; status: string }[];
};
type PrivateFeedback = {
  participant_id: string;
  tasks: Task[];
  issues: {
    id: string;
    description: string;
    category: string;
    severity: string;
    status: string;
    sanitized_reproduction: string;
    engineering_reference: string;
    export_approved: boolean;
  }[];
};
const tasks = [
  "Create a project and upload a document",
  "Ask questions and inspect citations",
  "Integrate using Python or JavaScript",
  "Export a standalone application",
  "Run independently and obtain a cited answer",
];
const checks = [
  "permitted_data_explained",
  "retention_and_deletion",
  "private_network",
  "trusted_tls",
  "firewall_verified",
  "backup_restore_verified",
  "alerts_verified",
  "credentials_rotated",
  "paid_providers_disabled",
];
const label = (text: string) => text.replaceAll("_", " ");
const initialTask = {
  status: "not_started",
  duration_seconds: 0,
  errors: 0,
  assistance: 0,
  difficulty: 0,
  feedback: "",
};

export function PilotPanel({ isAdmin }: { isAdmin: boolean }) {
  const [member, setMember] = useState<Member | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  const [accepted, setAccepted] = useState(false),
    [number, setNumber] = useState(1),
    [task, setTask] = useState(initialTask),
    [started, setStarted] = useState<number | null>(null),
    [proof, setProof] = useState<File | null>(null);
  const [cohort, setCohort] = useState("human"),
    [report, setReport] = useState<Report | null>(null),
    [feedback, setFeedback] = useState<PrivateFeedback | null>(null);
  const [enrollEmail, setEnrollEmail] = useState(""),
    [reference, setReference] = useState(""),
    [authorized, setAuthorized] = useState(false),
    [trialAttested, setTrialAttested] = useState(false);
  const [operatorChecks, setOperatorChecks] = useState<Record<string, boolean>>(
      Object.fromEntries(checks.map((k) => [k, false])),
    ),
    [incidentOwner, setIncidentOwner] = useState(""),
    [externalReference, setExternalReference] = useState(""),
    [readiness, setReadiness] = useState<unknown>(null);
  const [reviewId, setReviewId] = useState(""),
    [severity, setSeverity] = useState("medium"),
    [issueStatus, setIssueStatus] = useState("investigating"),
    [sanitized, setSanitized] = useState(""),
    [engineeringReference, setEngineeringReference] = useState(""),
    [exportApproved, setExportApproved] = useState(false);
  const [category, setCategory] = useState("ux"),
    [problem, setProblem] = useState("");
  async function refresh() {
    setMember(await api<Member>("/v1/pilot/me"));
    if (isAdmin) {
      setReport(await api<Report>(`/v1/admin/pilot/report?cohort=${cohort}`));
      setReadiness(await api("/v1/admin/pilot/readiness"));
    }
  }
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const m = await api<Member>("/v1/pilot/me");
        if (active) setMember(m);
        if (isAdmin) {
          const r = await api<Report>(
            `/v1/admin/pilot/report?cohort=${cohort}`,
          );
          const ready = await api("/v1/admin/pilot/readiness");
          const state = await api<{
            checklist: Record<string, boolean>;
            incident_owner: string;
            user_authorization_reference: string;
          }>("/v1/admin/pilot/operator-state");
          if (active) {
            setReport(r);
            setReadiness(ready);
            setOperatorChecks(state.checklist);
            setIncidentOwner(state.incident_owner);
            setExternalReference(state.user_authorization_reference);
          }
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      }
    })();
    return () => {
      active = false;
    };
  }, [isAdmin, cohort]);
  async function perform(action: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      await refresh();
      setNotice(message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function chooseTask(value: number) {
    setNumber(value);
    setStarted(null);
    const stored = member?.tasks?.find((t) => t.task_number === value);
    setTask(
      stored
        ? {
            status: stored.status,
            duration_seconds: stored.duration_seconds,
            errors: stored.errors,
            assistance: stored.assistance,
            difficulty: stored.difficulty,
            feedback: stored.feedback || "",
          }
        : initialTask,
    );
  }
  function clearLocalStudy() {
    setTask(initialTask);
    setStarted(null);
    setProof(null);
    setProblem("");
    setFeedback(null);
    setReviewId("");
    setSanitized("");
    setTrialAttested(false);
  }
  return (
    <div className="pilot-panel">
      <div className="page-heading">
        <div>
          <span className="eyebrow">CONTROLLED DEVELOPER STUDY</span>
          <h1>Pilot study</h1>
          <p>
            Optional participation. Technical activity and human feedback are
            reported separately.
          </p>
        </div>
        <button
          disabled={busy}
          onClick={() => perform(refresh, "Pilot records refreshed.")}
        >
          Refresh pilot
        </button>
      </div>
      {error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}
      {notice && (
        <div className="alert success" role="status">
          {notice}
        </div>
      )}
      <section className="panel form-panel">
        <h2>Your privacy and consent</h2>
        <p>{member?.notice || "Loading pilot status…"}</p>
        <p>
          Records expire after 30 days. Use permitted non-sensitive documents.
          Do not submit passwords, keys or confidential content in feedback.
          Default report downloads omit free text. Backup copies expire under
          the operator’s retention policy.
        </p>
        {!member ? (
          <p>Loading pilot enrollment…</p>
        ) : !member.enrolled ? (
          <p>
            You are not enrolled. Normal application use continues without pilot
            analytics. Contact your operator through the approved private
            channel.
          </p>
        ) : (
          <>
            <p>
              Cohort: <strong>{label(member.cohort || "")}</strong>
              {member.expires_at
                ? ` · Records expire ${new Date(member.expires_at * 1000).toLocaleString()}`
                : ""}
            </p>
            {!member.consented_at ? (
              <>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={accepted}
                    onChange={(e) => setAccepted(e.target.checked)}
                  />
                  I consent to optional pilot technical telemetry and the
                  feedback I choose to submit.
                </label>
                <button
                  className="primary"
                  disabled={!accepted || busy}
                  onClick={() =>
                    perform(async () => {
                      await api("/v1/pilot/consent", {
                        method: "PUT",
                        body: JSON.stringify({
                          accepted: true,
                          version: "pilot-v1",
                        }),
                      });
                      clearLocalStudy();
                    }, "Consent saved. Prior activity was not collected or backfilled.")
                  }
                >
                  Start optional pilot collection
                </button>
              </>
            ) : (
              <>
                <p>
                  Collection is enabled from your opt-in activation. Earlier
                  activity is not backfilled.
                </p>
                <button
                  disabled={busy}
                  onClick={() =>
                    perform(async () => {
                      await api("/v1/pilot/consent", {
                        method: "PUT",
                        body: JSON.stringify({
                          accepted: false,
                          version: "pilot-v1",
                        }),
                      });
                      clearLocalStudy();
                    }, "Collection stopped and prior pilot activity/feedback deleted.")
                  }
                >
                  Withdraw consent and erase pilot records
                </button>
              </>
            )}
            <button
              disabled={busy}
              onClick={() =>
                perform(async () => {
                  await api("/v1/pilot/me", { method: "DELETE" });
                  clearLocalStudy();
                }, "Pilot enrollment and live records deleted. Projects remain available.")
              }
            >
              Delete pilot enrollment and data
            </button>
          </>
        )}
      </section>
      {!!member?.consented_at && (
        <>
          <section className="panel form-panel">
            <h2>Observed technical progress</h2>
            <ol>
              {member.funnel?.stages.map((s) => (
                <li key={s.stage}>
                  {label(s.stage)}:{" "}
                  {s.completed
                    ? `observed ${new Date(s.observed_at! * 1000).toLocaleString()}`
                    : "not observed"}
                </li>
              ))}
            </ol>
            <p>
              First cited answer:{" "}
              {member.funnel?.time_to_first_cited_answer_seconds ?? "pending"}{" "}
              seconds. Observed independent startup:{" "}
              {member.funnel?.time_to_observed_standalone_deployment_seconds ??
                "pending"}{" "}
              seconds. Offline evidence-import delay is included; these events
              do not establish human task completion.
            </p>
          </section>
          <form
            className="panel form-panel"
            onSubmit={(e) => {
              e.preventDefault();
              perform(
                () =>
                  api(`/v1/pilot/tasks/${number}`, {
                    method: "PUT",
                    body: JSON.stringify({
                      ...task,
                      duration_seconds:
                        started === null
                          ? task.duration_seconds
                          : Math.max(
                              0,
                              Math.round((Date.now() - started) / 1000),
                            ),
                    }),
                  }),
                "Self-reported task outcome saved.",
              );
              setStarted(null);
            }}
          >
            <h2>Participant task feedback</h2>
            <label>
              Study task
              <select
                value={number}
                onChange={(e) => chooseTask(Number(e.target.value))}
              >
                {tasks.map((t, i) => (
                  <option key={t} value={i + 1}>
                    {i + 1}. {t}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              disabled={started !== null}
              onClick={() => setStarted(Date.now())}
            >
              {started === null ? "Start task timer" : "Task timer running"}
            </button>
            <label>
              Completion status
              <select
                value={task.status}
                onChange={(e) => setTask({ ...task, status: e.target.value })}
              >
                {["not_started", "completed", "failed", "abandoned"].map(
                  (s) => (
                    <option key={s} value={s}>
                      {label(s)}
                    </option>
                  ),
                )}
              </select>
            </label>
            {(
              [
                ["duration_seconds", "Time taken in seconds", 86400],
                ["errors", "Number of errors", 1000],
                ["assistance", "Times assistance requested", 1000],
              ] as const
            ).map(([key, title, max]) => (
              <label key={key}>
                {title}
                <input
                  type="number"
                  min={0}
                  max={max}
                  required
                  value={task[key]}
                  onChange={(e) =>
                    setTask({ ...task, [key]: Number(e.target.value) })
                  }
                />
              </label>
            ))}
            <label>
              Difficulty (1 easy to 5 hard)
              <select
                value={task.difficulty}
                onChange={(e) =>
                  setTask({ ...task, difficulty: Number(e.target.value) })
                }
              >
                <option value={0}>Not rated — task not started</option>
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>
                    {n}
                    {n === 1 ? " — easy" : n === 5 ? " — hard" : ""}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Optional feedback — what happened, and would you use this again?
              <textarea
                maxLength={2000}
                value={task.feedback}
                onChange={(e) => setTask({ ...task, feedback: e.target.value })}
              />
            </label>
            <button className="primary" disabled={busy}>
              Save task outcome
            </button>
          </form>
          <form
            className="panel form-panel"
            onSubmit={(e) => {
              e.preventDefault();
              perform(
                () =>
                  api("/v1/pilot/issues", {
                    method: "POST",
                    body: JSON.stringify({ category, description: problem }),
                  }),
                "Private problem report submitted. Nothing was published.",
              );
            }}
          >
            <h2>Report a problem privately</h2>
            <p>
              For security incidents or suspected data loss, also contact the
              designated incident owner immediately.
            </p>
            <label>
              Problem category
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              >
                {[
                  "security",
                  "data_loss",
                  "retrieval",
                  "api",
                  "export",
                  "setup",
                  "performance",
                  "ux",
                  "feature",
                ].map((c) => (
                  <option key={c} value={c}>
                    {label(c)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Private reproduction without secrets
              <textarea
                minLength={5}
                maxLength={2000}
                required
                value={problem}
                onChange={(e) => setProblem(e.target.value)}
              />
            </label>
            <button disabled={busy}>Submit private problem</button>
          </form>
          <form
            className="panel form-panel"
            onSubmit={(e) => {
              e.preventDefault();
              perform(async () => {
                if (!proof || proof.size > 65536)
                  throw new Error(
                    "Select a runtime evidence JSON file up to 64 KiB.",
                  );
                await api("/v1/pilot/deployment-evidence", {
                  method: "POST",
                  body: await proof.text(),
                });
              }, "Signed runtime evidence verified and technical progress recorded.");
            }}
          >
            <h2>Independent deployment evidence</h2>
            <p>
              Enable optional offline pilot evidence when exporting. Query the
              independent application, then run its bundled{" "}
              <code>
                python scripts/pilot-evidence.py --url http://localhost:8020
                --output runtime-evidence.json
              </code>
              . Upload that JSON here explicitly. There is no automatic
              callback. Signed self-hosted evidence is not remote attestation or
              human validation.
            </p>
            <label>
              Runtime evidence JSON
              <input
                type="file"
                accept="application/json,.json"
                onChange={(e) => setProof(e.target.files?.[0] || null)}
              />
            </label>
            <button disabled={busy || !proof}>Verify runtime evidence</button>
          </form>
        </>
      )}
      {isAdmin && (
        <>
          <section className="panel form-panel">
            <h2>Pilot operator dashboard</h2>
            <label>
              Report cohort
              <select
                value={cohort}
                disabled={busy}
                onChange={(e) => {
                  setCohort(e.target.value);
                  setFeedback(null);
                  setReport(null);
                  setReviewId("");
                  setTrialAttested(false);
                }}
              >
                <option value="human">Real participants</option>
                <option value="engineering_qa">
                  Engineering QA — excluded from human results
                </option>
              </select>
            </label>
            <p>
              Activated: {report?.activated_participants ?? "loading"} ·
              Operator-attested real trials:{" "}
              {report?.operator_attested_real_trials ?? "loading"}
            </p>
            <p>
              Answer-service latency: median{" "}
              {report?.query_latency_ms.median ?? "pending"} ms / P95{" "}
              {report?.query_latency_ms.p95 ?? "pending"} ms. Transport overhead
              is excluded.
            </p>
            <div className="pilot-table">
              <table>
                <thead>
                  <tr>
                    <th>Technical event</th>
                    <th>Observed count</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(report?.technical_events || {}).map(
                    ([k, v]) => (
                      <tr key={k}>
                        <td>{label(k)}</td>
                        <td>{v}</td>
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            </div>
            <button
              disabled={!report}
              onClick={() => download(report, "sanitized-pilot-report.json")}
            >
              Download sanitized pilot report
            </button>
            <ul>
              {report?.participants.map((p) => (
                <li key={p.participant_id}>
                  Participant {p.participant_id.slice(0, 8)} ·{" "}
                  {p.reported_tasks.length}/5 reported outcomes{" "}
                  <button
                    onClick={() =>
                      perform(async () => {
                        setFeedback(
                          await api<PrivateFeedback>(
                            `/v1/admin/pilot/participants/${p.participant_id}/feedback`,
                          ),
                        );
                        setReviewId("");
                        setTrialAttested(false);
                      }, "Private feedback opened for operator review.")
                    }
                  >
                    Review feedback {p.participant_id.slice(0, 8)}
                  </button>
                </li>
              ))}
            </ul>
            <p>
              Reported problems: {report?.issues.length ?? 0}. Free text and
              identities are excluded from the report download.
            </p>
          </section>
          <form
            className="panel form-panel"
            onSubmit={(e) => {
              e.preventDefault();
              perform(
                () =>
                  api("/v1/admin/pilot/participants", {
                    method: "POST",
                    body: JSON.stringify({
                      email: enrollEmail,
                      cohort,
                      authorization_obtained: authorized,
                      authorization_reference: reference,
                    }),
                  }),
                "Enrollment recorded; participant consent is still required. No invitation was sent.",
              );
            }}
          >
            <h2>Record authorized enrollment</h2>
            <p>
              This records prior authorization for an existing account. It does
              not authorize contact, create an account or send an invitation.
            </p>
            <label>
              Existing account email
              <input
                type="email"
                required
                value={enrollEmail}
                onChange={(e) => setEnrollEmail(e.target.value)}
              />
            </label>
            <label>
              Private authorization reference
              <input
                minLength={3}
                maxLength={100}
                required
                value={reference}
                onChange={(e) => setReference(e.target.value)}
              />
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={authorized}
                onChange={(e) => setAuthorized(e.target.checked)}
              />
              I have explicit authorization for this participant and selected
              the correct cohort.
            </label>
            <button disabled={busy || !authorized}>Record enrollment</button>
          </form>
          {feedback && (
            <section className="panel form-panel">
              <h2>Private operator review</h2>
              {feedback.tasks.map((t) => (
                <article key={t.task_number}>
                  <h3>
                    Task {t.task_number}: {t.status}
                  </h3>
                  <p>
                    {t.duration_seconds}s · {t.errors} errors · {t.assistance}{" "}
                    assistance requests · difficulty{" "}
                    {t.difficulty ? `${t.difficulty}/5` : "not rated"}
                  </p>
                  <p>{t.feedback || "No optional feedback."}</p>
                </article>
              ))}
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={trialAttested}
                  onChange={(e) => setTrialAttested(e.target.checked)}
                />
                I verified actual participation by a real authorized human,
                including incomplete/failed tasks.
              </label>
              <button
                disabled={busy || !trialAttested || cohort !== "human"}
                onClick={() =>
                  perform(
                    () =>
                      api(
                        `/v1/admin/pilot/participants/${feedback.participant_id}/review-trial`,
                        {
                          method: "POST",
                          body: JSON.stringify({
                            actual_participation_attested: true,
                          }),
                        },
                      ),
                    "Human trial review recorded from operator attestation.",
                  )
                }
              >
                Record reviewed human trial
              </button>
              <h3>Private reports</h3>
              {feedback.issues.map((i) => (
                <article key={i.id}>
                  <p>
                    {label(i.category)} · {i.description}
                  </p>
                  <button
                    onClick={() => {
                      setReviewId(i.id);
                      setSeverity(
                        i.severity === "untriaged" ? "medium" : i.severity,
                      );
                      setIssueStatus(i.status);
                      setSanitized(i.sanitized_reproduction);
                      setEngineeringReference(i.engineering_reference);
                      setExportApproved(i.export_approved);
                    }}
                  >
                    Triage report {i.id.slice(0, 8)}
                  </button>
                </article>
              ))}
            </section>
          )}
          {reviewId && (
            <form
              className="panel form-panel"
              onSubmit={(e) => {
                e.preventDefault();
                perform(
                  () =>
                    api(`/v1/admin/pilot/issues/${reviewId}`, {
                      method: "PUT",
                      body: JSON.stringify({
                        severity,
                        status: issueStatus,
                        sanitized_reproduction: sanitized,
                        engineering_reference: engineeringReference,
                        export_approved: exportApproved,
                      }),
                    }),
                  "Private triage saved. No GitHub issue was created.",
                );
              }}
            >
              <h2>Issue triage</h2>
              <label>
                Severity
                <select
                  value={severity}
                  onChange={(e) => setSeverity(e.target.value)}
                >
                  {["critical", "high", "medium", "low"].map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
              <label>
                Issue status
                <select
                  value={issueStatus}
                  onChange={(e) => setIssueStatus(e.target.value)}
                >
                  {[
                    "new",
                    "investigating",
                    "scheduled",
                    "resolved",
                    "closed",
                  ].map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
              <label>
                Engineering work reference
                <input
                  maxLength={150}
                  value={engineeringReference}
                  onChange={(e) => setEngineeringReference(e.target.value)}
                  placeholder="ENG-123"
                />
              </label>
              <label>
                Manually sanitized reproduction
                <textarea
                  maxLength={2000}
                  value={sanitized}
                  onChange={(e) => setSanitized(e.target.value)}
                />
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={exportApproved}
                  onChange={(e) => setExportApproved(e.target.checked)}
                />
                I reviewed this text for confidential material and approve
                downloading it.
              </label>
              <button disabled={busy}>Save issue triage</button>
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  perform(
                    async () =>
                      download(
                        await api(`/v1/admin/pilot/issues/${reviewId}/export`),
                        "operator-reviewed-issue.json",
                      ),
                    "Reviewed issue downloaded; publication still requires authorization.",
                  )
                }
              >
                Download reviewed issue
              </button>
            </form>
          )}
          <form
            className="panel form-panel"
            onSubmit={(e) => {
              e.preventDefault();
              perform(
                () =>
                  api("/v1/admin/pilot/operator-state", {
                    method: "PUT",
                    body: JSON.stringify({
                      checklist: operatorChecks,
                      incident_owner: incidentOwner,
                      user_authorization_reference: externalReference,
                    }),
                  }),
                "Operator attestation saved. No access or network changes performed.",
              );
            }}
          >
            <h2>Operator readiness attestation</h2>
            <p>
              Only check controls actually verified on the approved target host.
              Empty fields remain pending.
            </p>
            {checks.map((k) => (
              <label className="checkbox" key={k}>
                <input
                  type="checkbox"
                  checked={operatorChecks[k]}
                  onChange={(e) =>
                    setOperatorChecks({
                      ...operatorChecks,
                      [k]: e.target.checked,
                    })
                  }
                />
                {label(k)}
              </label>
            ))}
            <label>
              Incident owner (private)
              <input
                maxLength={100}
                value={incidentOwner}
                onChange={(e) => setIncidentOwner(e.target.value)}
              />
            </label>
            <label>
              User authorization reference for external access (private)
              <input
                maxLength={100}
                value={externalReference}
                onChange={(e) => setExternalReference(e.target.value)}
              />
            </label>
            <button disabled={busy}>Save operator attestation</button>
            <button
              type="button"
              onClick={() =>
                download(readiness, "pilot-runtime-readiness.json")
              }
            >
              Download runtime readiness
            </button>
            <pre className="pilot-readiness">
              {JSON.stringify(readiness, null, 2)}
            </pre>
          </form>
        </>
      )}
    </div>
  );
}
