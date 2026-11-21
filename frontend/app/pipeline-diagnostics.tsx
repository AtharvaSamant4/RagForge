"use client";
import { useEffect, useState } from "react";
import { api } from "./api";
import type { Source } from "./types";

type ModelProfile = {
  id: string;
  model: string;
  provider: string;
  dimensions: number;
  revision?: string;
  max_tokens?: number;
  license?: string;
  semantic: boolean;
};
type Info = {
  reindex_required: boolean;
  embedding_profile: ModelProfile;
  embedding_runtime: {
    loaded: boolean;
    threads: number;
    cached_vectors: number;
  };
  index: {
    state: string;
    message: string;
    compatible: boolean;
    query_ready: boolean;
    index_generation: number;
    indexed_profiles: string[];
    pending_document_ids: string[];
  };
};

export function PipelineDiagnostics({
  base,
  onReindexChange,
}: {
  base: string;
  onReindexChange: (value: boolean) => void;
}) {
  const [info, setInfo] = useState<Info | null>(null),
    [question, setQuestion] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [results, setResults] = useState<
      { strategy: string; retrieval_latency_ms: number; retrieved: Source[] }[]
    >([]);
  useEffect(() => {
    let active = true;
    const load = () =>
      api<Info>(base + "/pipeline")
        .then((i) => {
          if (active) {
            setInfo(i);
            onReindexChange(i.reindex_required);
          }
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    void load();
    const timer = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [base, onReindexChange]);
  return (
    <section className="panel form-panel">
      <h2>Active embedding model</h2>
      {info && (
        <>
          <strong className="model-name">{info.embedding_profile.model}</strong>
          <dl>
            <dt>Execution</dt>
            <dd>
              {info.embedding_profile.provider === "semantic"
                ? "Local CPU inference"
                : info.embedding_profile.provider}{" "}
              · {info.embedding_profile.dimensions} dimensions
            </dd>
            {info.embedding_profile.revision && (
              <>
                <dt>Pinned revision</dt>
                <dd>
                  <code className="model-id">
                    {info.embedding_profile.revision}
                  </code>
                </dd>
              </>
            )}
            <dt>Index status</dt>
            <dd>
              <span
                className={`status ${info.index.state === "ready" ? "ready" : info.index.query_ready ? "queued" : "failed"}`}
              >
                {info.index.state}
              </span>{" "}
              · generation {info.index.index_generation}
            </dd>
          </dl>
          <p
            role="status"
            className={info.index.query_ready ? "muted" : "danger-text"}
          >
            {info.index.message}
          </p>
          {info.embedding_profile.max_tokens && (
            <p className="muted">
              Chunks fit the {info.embedding_profile.max_tokens}-token model
              budget. {info.embedding_runtime.threads} CPU threads per process;{" "}
              {info.embedding_runtime.cached_vectors} vectors cached in memory.
            </p>
          )}
          <p className="muted">
            Choose <code>EMBEDDING_PROVIDER=semantic</code>, <code>local</code>{" "}
            (lexical baseline), or <code>openai</code> in the deployment
            environment. Restart API and worker, then rebuild incompatible
            projects.
          </p>
        </>
      )}
      <details className="strategy-compare">
        <summary>Compare retrieval strategies</summary>
        <p>
          Inspect actual passages and latency for the same question. This does
          not generate an answer or assign accuracy scores.
        </p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              const r = await api<{ results: typeof results }>(
                base + "/retrieval/compare",
                { method: "POST", body: JSON.stringify({ question }) },
              );
              setResults(r.results);
            } catch (e) {
              setError(e instanceof Error ? e.message : "Comparison failed");
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Comparison question
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              required
              minLength={2}
              maxLength={2000}
            />
          </label>
          <button className="secondary" disabled={busy}>
            {busy ? "Comparing…" : "Compare strategies"}
          </button>
        </form>
        {results.map((r) => (
          <div key={r.strategy} className="comparison-result">
            <strong>
              {r.strategy} · {r.retrieval_latency_ms.toFixed(1)} ms ·{" "}
              {r.retrieved.length} passages
            </strong>
            {r.retrieved.map((s) => (
              <details key={s.chunk_id}>
                <summary>
                  {s.document_name} · signal {s.score.toFixed(3)}
                </summary>
                <p>{s.text}</p>
              </details>
            ))}
          </div>
        ))}
      </details>
      {error && (
        <p className="danger-text" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
