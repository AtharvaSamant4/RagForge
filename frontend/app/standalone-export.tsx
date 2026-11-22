"use client";

import { useEffect, useState } from "react";
import { Download, Package, RefreshCw } from "lucide-react";
import { api } from "./api";
import type { Doc, Pipeline } from "./types";

type ExportJob = {
  id: string;
  status: "queued" | "generating" | "ready" | "failed" | "expired";
  error: string | null;
  expires_at: number;
  size_bytes: number;
  sha256: string | null;
  manifest: {
    generator_version: string;
    template_sha256: string;
    sources: { name: string; size_bytes: number }[];
    embedding: { model: string; dimensions: number };
    pipeline: Pipeline;
  };
  instructions: string;
};

export function StandaloneExport({
  base,
  documents,
}: {
  base: string;
  documents: Doc[];
}) {
  const [mode, setMode] = useState("configuration"),
    [selected, setSelected] = useState<string[]>([]),
    [consent, setConsent] = useState(false),
    [imports, setImports] = useState(true),
    [pilotAllowed, setPilotAllowed] = useState(false),
    [pilotEvidence, setPilotEvidence] = useState(false),
    [job, setJob] = useState<ExportJob | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [configuration, setConfiguration] = useState<{
      config: Pipeline;
      embedding_profile: { model: string; dimensions: number };
      generation_provider: string;
    } | null>(null);
  useEffect(() => {
    let active = true;
    Promise.all([
      api<typeof configuration>(base + "/pipeline"),
      api<ExportJob[]>(base + "/exports"),
      api<{ consented_at?: number | null }>("/v1/pilot/me"),
    ])
      .then(([configuration, jobs, pilot]) => {
        if (active) {
          setConfiguration(configuration);
          setJob(jobs[0] || null);
          setPilotAllowed(!!pilot.consented_at);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [base]);
  useEffect(() => {
    if (!job || !["queued", "generating"].includes(job.status)) return;
    let active = true;
    const timer = setInterval(() => {
      api<ExportJob>(`${base}/exports/${job.id}`)
        .then((data) => {
          if (active) {
            setJob(data);
            setError("");
          }
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    }, 3000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [base, job?.id, job?.status]);

  async function generate() {
    setBusy(true);
    setError("");
    setJob(null);
    try {
      setJob(
        await api<ExportJob>(base + "/exports", {
          method: "POST",
          body: JSON.stringify({
            mode,
            document_ids: mode === "snapshot" ? selected : [],
            acknowledge_copy: consent,
            allow_imports: imports,
            include_pilot_evidence: pilotEvidence,
          }),
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function download() {
    if (!job) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api${base}/exports/${job.id}/download`, {
        credentials: "same-origin",
      });
      if (!response.ok) {
        const body = await response.json();
        throw new Error(body.detail || "Download failed");
      }
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "standalone-knowledge.zip";
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const active =
    busy || (!!job && ["queued", "generating"].includes(job.status));
  const included = documents.filter((d) => selected.includes(d.id));
  return (
    <section
      className="panel form-panel standalone-export"
      aria-label="Standalone application export"
    >
      <div className="panel-heading">
        <h2>
          <Package size={19} /> Export standalone application
        </h2>
        <span className="badge">Docker + API</span>
      </div>
      <p>
        Download an independently runnable knowledge API with its own PostgreSQL
        database, worker, model cache and fresh credentials. It continues
        working after this workspace is stopped.
      </p>
      {error && (
        <div className="export-error" role="alert">
          {error}
        </div>
      )}
      <fieldset disabled={active}>
        {pilotAllowed && (
          <label className="checkbox">
            <input
              type="checkbox"
              checked={pilotEvidence}
              onChange={(e) => setPilotEvidence(e.target.checked)}
            />
            Include optional offline pilot evidence. No automatic callback;
            explicitly import signed runtime proof after deployment.
          </label>
        )}
        <legend>Export mode</legend>
        <label className="checkbox">
          <input
            type="radio"
            name="export-mode"
            value="configuration"
            checked={mode === "configuration"}
            onChange={() => {
              setMode("configuration");
              setConsent(false);
            }}
          />{" "}
          Configuration only · no uploaded documents (default)
        </label>
        <label className="checkbox">
          <input
            type="radio"
            name="export-mode"
            value="snapshot"
            checked={mode === "snapshot"}
            onChange={() => setMode("snapshot")}
          />{" "}
          Include selected knowledge snapshot
        </label>
        {mode === "snapshot" && (
          <div className="export-selection">
            <p>
              <strong>
                Anyone with the ZIP can read the selected documents.
              </strong>{" "}
              Deleting a source here cannot revoke exported copies. History,
              sessions, existing API keys and provider secrets are excluded.
            </p>
            {documents.length === 0 && (
              <p>
                No documents yet. Upload and process a source, or choose
                configuration only.
              </p>
            )}
            {documents.map((doc) => (
              <label className="checkbox" key={doc.id}>
                <input
                  type="checkbox"
                  checked={selected.includes(doc.id)}
                  disabled={doc.status !== "ready"}
                  onChange={(e) =>
                    setSelected(
                      e.target.checked
                        ? [...selected, doc.id]
                        : selected.filter((id) => id !== doc.id),
                    )
                  }
                />{" "}
                <span>
                  {doc.name} · {(doc.size_bytes / 1024).toFixed(1)} KB ·{" "}
                  {doc.status}
                </span>
              </label>
            ))}
            <p>
              {included.length} selected ·{" "}
              {(
                included.reduce((sum, d) => sum + d.size_bytes, 0) / 1024
              ).toFixed(1)}{" "}
              KB of source files
            </p>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />{" "}
              I approve including these documents and understand exported copies
              cannot be revoked.
            </label>
          </div>
        )}
        <label className="checkbox">
          <input
            type="checkbox"
            checked={imports}
            onChange={(e) => setImports(e.target.checked)}
          />{" "}
          Allow document imports in the generated API
        </label>
      </fieldset>
      {configuration && (
        <div className="export-summary">
          <strong>Configuration summary</strong>
          <span>
            {configuration.embedding_profile.model} ·{" "}
            {configuration.embedding_profile.dimensions} dimensions
          </span>
          <span>
            {configuration.config.strategy} retrieval · top{" "}
            {configuration.config.top_k} · {configuration.config.chunk_size}{" "}
            words/chunk · {configuration.config.overlap} overlap
          </span>
          <span>
            Grounded answers with citations. Initial image, dependency and model
            downloads require network access.
          </span>
        </div>
      )}
      <button
        className="primary"
        disabled={
          active ||
          !configuration ||
          (mode === "snapshot" && (!consent || !selected.length))
        }
        onClick={() => void generate()}
      >
        <Package size={16} />{" "}
        {active ? "Generating application…" : "Export standalone application"}
      </button>
      {job && (
        <div className="export-result" aria-live="polite">
          <strong>Export status: {job.status}</strong>
          {["queued", "generating"].includes(job.status) && (
            <>
              <progress
                max={3}
                value={job.status === "queued" ? 1 : 2}
                aria-label="Application generation progress"
              />
              <p>
                {job.status === "queued"
                  ? "Waiting for the durable worker."
                  : "Validating sources and packaging the trusted application template."}
              </p>
            </>
          )}
          {job.error && <p role="alert">{job.error}</p>}
          {job.status === "ready" && (
            <>
              <p>
                {(job.size_bytes / 1024).toFixed(1)} KB ZIP · generator{" "}
                {job.manifest.generator_version} · {job.manifest.sources.length}{" "}
                included documents
              </p>
              <button
                className="secondary"
                disabled={busy}
                onClick={() => void download()}
              >
                <Download size={16} /> Download ZIP
              </button>
              <details>
                <summary>Run instructions and included sources</summary>
                <p>{job.instructions}</p>
                <pre>
                  <code>
                    {
                      "python scripts/init.py\ndocker compose up --build -d\ndocker compose exec -T api python -m app.model_cache"
                    }
                  </code>
                </pre>
                <ul>
                  {job.manifest.sources.map((s, i) => (
                    <li key={i}>
                      {s.name} · {s.size_bytes} bytes
                    </li>
                  ))}
                </ul>
                <p>Archive SHA-256</p>
                <code className="export-hash">{job.sha256}</code>
              </details>
            </>
          )}
          {["failed", "expired"].includes(job.status) && (
            <p>
              <RefreshCw size={14} /> Correct any issue and generate a new
              application.
            </p>
          )}
        </div>
      )}
      <p className="muted">
        Server archives expire after at most one hour and may be removed sooner
        by new exports or storage limits. Downloaded copies are independent. The
        generated README covers import, rebuild, credentials, HTTPS and
        limitations.
      </p>
    </section>
  );
}
