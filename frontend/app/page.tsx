"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  Activity,
  BookOpen,
  Boxes,
  Braces,
  Check,
  ChevronDown,
  Code2,
  Copy,
  Database,
  FileText,
  FlaskConical,
  Globe,
  Layers3,
  LoaderCircle,
  LogOut,
  MessageSquare,
  Plus,
  RefreshCw,
  Rocket,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
  X,
  Zap,
} from "lucide-react";
import { api, download } from "./api";
import { Modal } from "./modal";
import type {
  Case,
  Doc,
  EvalResult,
  Job,
  Key,
  Message,
  Pipeline,
  Project,
  Result,
  Source,
  Widget,
} from "./types";

const sections = [
  ["Overview", Boxes],
  ["Documents", FileText],
  ["Pipeline", Layers3],
  ["Playground", MessageSquare],
  ["Evaluation", FlaskConical],
  ["API & Integration", Code2],
  ["Deployment", Rocket],
  ["Settings", Settings2],
] as const;
const bytes = (n: number) =>
  n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.ceil(n / 1024)} KB`;
const time = (n: number) => new Date(n * 1000).toLocaleDateString();
function Status({ value }: { value: string }) {
  return (
    <span className={`status ${value}`}>
      <span />
      {value}
    </span>
  );
}
function Empty({
  icon: Icon = BookOpen,
  title,
  children,
}: {
  icon?: typeof BookOpen;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="empty">
      <Icon size={32} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
function SourceCard({ source }: { source: Source }) {
  return (
    <details className="source">
      <summary>
        <FileText size={15} />
        <strong>
          {source.number ? `[${source.number}] ` : ""}
          {source.document_name}
        </strong>
        <span>
          {Object.entries(source.locator)
            .filter(([k]) => !k.startsWith("char"))
            .map(([k, v]) => `${k} ${v}`)
            .join(" · ")}
        </span>
        <ChevronDown size={14} />
      </summary>
      <p>{source.quote || source.text}</p>
      <small>
        Retrieval evidence: {source.score.toFixed(3)} · chunk{" "}
        {source.chunk_id.slice(0, 8)}
      </small>
    </details>
  );
}

export default function Dashboard() {
  const [user, setUser] = useState<{ email: string } | null>(null),
    [boot, setBoot] = useState(true),
    [register, setRegister] = useState(true),
    [email, setEmail] = useState(""),
    [password, setPassword] = useState("");
  const [brand, setBrand] = useState("RAGForge"),
    [provider, setProvider] = useState("local"),
    [generation, setGeneration] = useState("extractive");
  const [projects, setProjects] = useState<Project[]>([]),
    [selected, setSelected] = useState(""),
    [section, setSection] = useState("Overview"),
    [docs, setDocs] = useState<Doc[]>([]),
    [jobs, setJobs] = useState<Job[]>([]);
  const [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [create, setCreate] = useState(false),
    [name, setName] = useState(""),
    [description, setDescription] = useState("");
  const [pipeline, setPipeline] = useState<Pipeline | null>(null),
    [reindex, setReindex] = useState(false),
    [reason, setReason] = useState("");
  const [question, setQuestion] = useState(""),
    [messages, setMessages] = useState<Message[]>([]),
    [conversationId, setConversationId] = useState<string | null>(null),
    [history, setHistory] = useState<{ id: string; title: string }[]>([]),
    [retrieval, setRetrieval] = useState(false);
  const [keys, setKeys] = useState<Key[]>([]),
    [secret, setSecret] = useState(""),
    [keyName, setKeyName] = useState("Application key"),
    [manageDocs, setManageDocs] = useState(false),
    [language, setLanguage] = useState("cURL");
  const [cases, setCases] = useState<Case[]>([]),
    [runs, setRuns] = useState<
      { id: string; created_at: number; result: EvalResult }[]
    >([]),
    [caseQuestion, setCaseQuestion] = useState(""),
    [caseAnswer, setCaseAnswer] = useState(""),
    [caseDoc, setCaseDoc] = useState(""),
    [expectRefusal, setExpectRefusal] = useState(false),
    [includeSynthetic, setIncludeSynthetic] = useState(false);
  const [widget, setWidget] = useState<Widget>({
      enabled: false,
      title: "Knowledge assistant",
      welcome: "Ask about our documentation.",
      color: "#14b8a6",
      theme: "dark",
      allowed_origins: [],
    }),
    [origins, setOrigins] = useState(""),
    [widgetToken, setWidgetToken] = useState("");
  const [usage, setUsage] = useState<{
      queries: number;
      average_latency_ms: number | null;
      refused_queries: number;
      uploaded_bytes: number;
    } | null>(null),
    [preview, setPreview] = useState<{
      name: string;
      chunks: {
        id: string;
        text: string;
        locator: Record<string, string | number>;
      }[];
    } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const chatEnd = useRef<HTMLDivElement>(null);
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const project = projects.find((p) => p.id === selected);
  const base = `/v1/projects/${selected}`;
  const task = async (label: string, fn: () => Promise<void>) => {
    setBusy(label);
    setError("");
    setNotice("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy("");
    }
  };
  const refreshProjects = useCallback(async () => {
    const p = await api<Project[]>("/v1/projects");
    setProjects(p);
    return p;
  }, []);
  const loadDocs = useCallback(async () => {
    if (!selected) return;
    const [d, j] = await Promise.all([
      api<Doc[]>(`/v1/projects/${selected}/documents`),
      api<Job[]>(`/v1/projects/${selected}/jobs`),
    ]);
    if (selectedRef.current !== selected) return;
    setDocs(d);
    setJobs(j);
  }, [selected]);
  useEffect(() => {
    Promise.all([
      api<{ email: string }>("/v1/auth/me")
        .then(setUser)
        .catch(() => {}),
      api<{
        brand: string;
        embedding_provider: string;
        generation_provider: string;
      }>("/health")
        .then((h) => {
          setBrand(h.brand);
          setProvider(h.embedding_provider);
          setGeneration(h.generation_provider);
        })
        .catch(() =>
          setError("The API is unavailable. Start the backend and database."),
        ),
    ]).finally(() => setBoot(false));
  }, []);
  useEffect(() => {
    if (user)
      refreshProjects()
        .then((p) => setSelected(p[0]?.id || ""))
        .catch((e) => setError(e.message));
  }, [user, refreshProjects]);
  useEffect(() => {
    setDocs([]);
    setJobs([]);
    setMessages([]);
    setConversationId(null);
    setSecret("");
    setWidgetToken("");
    setPreview(null);
    setUsage(null);
    setKeys([]);
    setCases([]);
    setRuns([]);
    setHistory([]);
    setPipeline(null);
    if (selected) loadDocs().catch((e) => setError(e.message));
  }, [selected, loadDocs]);
  useEffect(() => {
    if (
      !selected ||
      !docs.some((d) => ["queued", "processing"].includes(d.status))
    )
      return;
    const id = setInterval(() => {
      loadDocs()
        .then(refreshProjects)
        .catch((e) => setError(e.message));
    }, 3000);
    return () => clearInterval(id);
  }, [docs, selected, loadDocs, refreshProjects]);
  useEffect(() => {
    if (!selected) return;
    let active = true;
    const load = async () => {
      if (section === "Pipeline") {
        const p = await api<{
          config: Pipeline;
          reindex_required: boolean;
          selection_reason: string;
        }>(base + "/pipeline");
        if (active) {
          setPipeline(p.config);
          setReindex(p.reindex_required);
          setReason(p.selection_reason);
        }
      }
      if (section === "Overview") {
        const [u, k] = await Promise.all([
          api<typeof usage>(base + "/usage"),
          api<Key[]>(base + "/keys"),
        ]);
        if (active) {
          setUsage(u);
          setKeys(k);
        }
      }
      if (section === "API & Integration") {
        const k = await api<Key[]>(base + "/keys");
        if (active) setKeys(k);
      }
      if (section === "Evaluation") {
        const [c, r] = await Promise.all([
          api<Case[]>(base + "/evaluation/cases"),
          api<typeof runs>(base + "/evaluation/runs"),
        ]);
        if (active) {
          setCases(c);
          setRuns(r);
        }
      }
      if (section === "Deployment") {
        const w = await api<Widget>(base + "/widget");
        if (active) {
          setWidget(w);
          setOrigins(w.allowed_origins.join("\n"));
        }
      }
      if (section === "Settings" && project) {
        setName(project.name);
        setDescription(project.description);
      }
      if (section === "Playground") {
        const h = await api<typeof history>(base + "/conversations");
        if (active) setHistory(h);
      }
    };
    load().catch((e) => setError(e.message));
    return () => {
      active = false;
    };
  }, [section, selected, base]);
  useEffect(() => {
    chatEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);
  const auth = (e: FormEvent) => {
    e.preventDefault();
    void task("Signing in", async () => {
      const u = await api<{ email: string }>(
        `/v1/auth/${register ? "register" : "login"}`,
        { method: "POST", body: JSON.stringify({ email, password }) },
      );
      setUser(u);
      setPassword("");
    });
  };
  const addProject = (e: FormEvent) => {
    e.preventDefault();
    void task("Creating project", async () => {
      const p = await api<Project>("/v1/projects", {
        method: "POST",
        body: JSON.stringify({ name, description }),
      });
      await refreshProjects();
      setSelected(p.id);
      setCreate(false);
      setName("");
      setDescription("");
      setSection("Documents");
    });
  };
  const uploadFiles = (files: FileList | null) => {
    if (!files?.length) return;
    void task("Uploading documents", async () => {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append("file", file);
        await api(base + "/documents", { method: "POST", body: form });
        await loadDocs();
      }
      await refreshProjects();
      setNotice("Upload received. The worker is processing your documents.");
    });
    if (inputRef.current) inputRef.current.value = "";
  };
  const ask = (e?: FormEvent, q?: string) => {
    e?.preventDefault();
    const text = q || question;
    if (!text.trim()) return;
    setQuestion("");
    void task("Finding evidence", async () => {
      const result = await api<Result>(base + "/query", {
        method: "POST",
        body: JSON.stringify({
          question: text,
          conversation_id: conversationId,
        }),
      });
      setMessages((m) => [...m, { question: text, result }]);
      setConversationId(result.conversation_id);
      await refreshProjects();
      setHistory(await api(base + "/conversations"));
    });
  };
  const loadEvaluation = async () => {
    const [c, r] = await Promise.all([
      api<Case[]>(base + "/evaluation/cases"),
      api<typeof runs>(base + "/evaluation/runs"),
    ]);
    setCases(c);
    setRuns(r);
  };
  const copy = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setNotice("Copied to clipboard.");
    } catch {
      setError("Clipboard access failed. Select and copy the text.");
    }
  };
  const signout = () =>
    void task("Signing out", async () => {
      await api("/v1/auth/logout", { method: "POST" });
      setUser(null);
      setSelected("");
      setProjects([]);
    });
  if (boot)
    return (
      <main className="boot">
        <LoaderCircle className="spin" />
        Starting your workspace…
      </main>
    );
  if (!user)
    return (
      <main className="auth-shell">
        <div className="auth-story">
          <div className="brand">
            <div className="brand-mark">
              <Layers3 size={24} />
            </div>
            {brand}
            <span> / workspace</span>
          </div>
          <div>
            <span className="eyebrow">FROM DOCUMENTS TO ANSWERS</span>
            <h1>
              Your knowledge.
              <br />
              Ready to build on.
            </h1>
            <p>
              Turn your documents into grounded answers and usable APIs. One
              workspace to ingest, inspect, and improve.
            </p>
            <div className="auth-flow">
              <FileText />
              <span>Ingest</span>
              <span className="line" />
              <Database />
              <span>Retrieve</span>
              <span className="line" />
              <MessageSquare />
              <span>Answer</span>
            </div>
          </div>
          <small>
            <ShieldCheck size={16} /> Your projects are private until you
            publish an assistant.
          </small>
        </div>
        <div className="auth-form">
          <div className="form-heading">
            <span className="eyebrow">YOUR KNOWLEDGE WORKSPACE</span>
            <h2>{register ? "Build something grounded." : "Welcome back."}</h2>
            <p>
              {register
                ? "Create your account to start your first project."
                : "Sign in to your projects and assistants."}
            </p>
          </div>
          <form onSubmit={auth}>
            <label>
              Email
              <input
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@company.com"
              />
            </label>
            <label>
              Password
              <input
                type="password"
                minLength={12}
                maxLength={200}
                autoComplete={register ? "new-password" : "current-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="At least 12 characters"
              />
            </label>
            {error && (
              <p className="alert error" role="alert">
                {error}
              </p>
            )}
            <button className="primary wide" disabled={!!busy}>
              {busy ? <LoaderCircle className="spin" size={18} /> : null}
              {register ? "Create account" : "Sign in"}
            </button>
          </form>
          <p className="auth-switch">
            {register ? "Already have an account?" : "New here?"}{" "}
            <button
              onClick={() => {
                setRegister(!register);
                setError("");
              }}
            >
              {register ? "Sign in" : "Create account"}
            </button>
          </p>
          <div className="mode-note">
            <Zap size={18} />
            <div>
              <strong>
                {provider === "local"
                  ? "Local mode · no API key needed"
                  : "Hosted embeddings enabled"}
              </strong>
              <p>
                {generation === "extractive"
                  ? "Answers extract exact passages from your sources."
                  : "Model-generated answers with verified source quotes."}
              </p>
            </div>
          </div>
        </div>
      </main>
    );
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="Workspace home">
          <div className="brand-mark">
            <Layers3 size={21} />
          </div>
          {brand}
        </a>
        <div className="workspace-label">WORKSPACE</div>
        <div className="project-picker">
          <label htmlFor="project-select">Active project</label>
          <select
            id="project-select"
            disabled={!!busy}
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            <option value="" disabled>
              Select a project
            </option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <button
            className="icon-button"
            aria-label="Create project"
            onClick={() => {
              setName("");
              setDescription("");
              setCreate(true);
            }}
          >
            <Plus size={17} />
          </button>
        </div>
        <nav>
          {sections.map(([label, Icon]) => (
            <button
              key={label}
              className={section === label ? "active" : ""}
              onClick={() => {
                setSection(label);
                setError("");
                setNotice("");
              }}
            >
              <Icon size={18} />
              {label}
              {label === "Documents" && project ? (
                <span className="nav-count">{project.document_count}</span>
              ) : null}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-badge">
            <span />
            {provider === "local" ? "Local workspace" : "Connected workspace"}
          </div>
          <p>
            {generation === "extractive"
              ? "Extractive answers · lexical embeddings"
              : "Verified source quotes · hosted generation"}
          </p>
          <button className="profile" disabled={!!busy} onClick={signout}>
            <span className="avatar">
              {user.email.slice(0, 2).toUpperCase()}
            </span>
            <span>
              {user.email}
              <small>Sign out</small>
            </span>
            <LogOut size={16} />
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <span className="muted">Workspace</span>
            <span className="slash">/</span>
            <span>{project?.name || "Projects"}</span>
            <span className="slash">/</span>
            <strong>{section}</strong>
          </div>
          <a href="/api/docs" target="_blank" rel="noreferrer">
            <BookOpen size={16} />
            API reference
          </a>
          <button
            className="mobile-logout icon-button"
            aria-label="Sign out"
            disabled={!!busy}
            onClick={signout}
          >
            <LogOut size={17} />
          </button>
        </header>
        <main className="content">
          {error && (
            <div className="alert error" role="alert">
              {error}
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {notice && (
            <div className="alert success" role="status">
              {notice}
              <button aria-label="Dismiss notice" onClick={() => setNotice("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {!selected ? (
            <>
              <div className="page-heading">
                <div>
                  <span className="eyebrow">YOUR WORKSPACE</span>
                  <h1>Make your knowledge useful.</h1>
                  <p>A grounded assistant starts with your first project.</p>
                </div>
                <button
                  className="primary"
                  onClick={() => {
                    setName("");
                    setDescription("");
                    setCreate(true);
                  }}
                >
                  <Plus size={17} />
                  Create project
                </button>
              </div>
              <div className="getting-started">
                <div className="hero-symbol">
                  <Layers3 size={50} />
                </div>
                <h2>From a document to a working API.</h2>
                <p>
                  Create a project, upload your sources, and ask your first
                  question. We’ll take care of processing and indexing.
                </p>
                <div className="steps">
                  {[
                    "Create a project",
                    "Add your documents",
                    "Ask and inspect",
                    "Integrate your API",
                  ].map((s, i) => (
                    <div key={s}>
                      <span>{i + 1}</span>
                      {s}
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">
                    PROJECT WORKSPACE{" "}
                    <span className="tag">
                      {project?.ready_count ? "INDEXED" : "GETTING STARTED"}
                    </span>
                  </div>
                  <h1>{section === "Overview" ? project?.name : section}</h1>
                  <p>
                    {
                      (
                        {
                          Overview:
                            project?.description ||
                            "Your knowledge pipeline, from source to answer.",
                          Documents:
                            "Give your assistant reliable knowledge to work with.",
                          Pipeline:
                            "Inspect and configure how your documents become answers.",
                          Playground:
                            "Ask, inspect the evidence, and understand every answer.",
                          Evaluation:
                            "Measure retrieval and grounding against real test cases.",
                          "API & Integration":
                            "Bring grounded answers into your application.",
                          Deployment:
                            "Share your assistant and export its configuration.",
                          Settings: "Manage the details of this project.",
                        } as Record<string, string>
                      )[section]
                    }
                  </p>
                </div>
                {section === "Documents" ? (
                  <button
                    className="primary"
                    disabled={!!busy}
                    onClick={() => inputRef.current?.click()}
                  >
                    <Upload size={17} />
                    {busy === "Uploading documents"
                      ? "Uploading…"
                      : "Upload documents"}
                  </button>
                ) : section === "Playground" ? (
                  <button
                    className="secondary"
                    disabled={!!busy}
                    onClick={() => {
                      setMessages([]);
                      setConversationId(null);
                    }}
                  >
                    <Plus size={16} />
                    New conversation
                  </button>
                ) : section === "Overview" ? (
                  <button
                    className="primary"
                    onClick={() => setSection("Playground")}
                  >
                    <MessageSquare size={17} />
                    Open playground
                  </button>
                ) : null}
              </div>
              {section === "Overview" && (
                <>
                  <div className="metrics">
                    <Metric
                      label="Documents"
                      value={String(project?.document_count || 0)}
                      detail={`${project?.ready_count || 0} ready to retrieve`}
                      icon={FileText}
                    />
                    <Metric
                      label="Indexed chunks"
                      value={String(project?.chunk_count || 0)}
                      detail="Inspectable source passages"
                      icon={Database}
                    />
                    <Metric
                      label="Queries"
                      value={String(
                        usage?.queries || project?.query_count || 0,
                      )}
                      detail={`${usage?.refused_queries || 0} unsupported questions refused`}
                      icon={MessageSquare}
                    />
                    <Metric
                      label="Average latency"
                      value={
                        usage?.average_latency_ms != null
                          ? `${usage.average_latency_ms.toFixed(0)} ms`
                          : "—"
                      }
                      detail="Measured retrieval + answer time"
                      icon={Activity}
                    />
                  </div>
                  <div className="overview-grid">
                    <section className="panel">
                      <div className="panel-heading">
                        <h2>Your knowledge pipeline</h2>
                        <span className="tag teal">
                          {project?.pipeline.strategy}
                        </span>
                      </div>
                      <div className="pipeline-flow">
                        {[
                          [Upload, "Sources", `${docs.length} documents`],
                          [
                            Layers3,
                            "Processing",
                            `${project?.pipeline.chunk_size} words / chunk`,
                          ],
                          [
                            Database,
                            "Retrieval",
                            `${project?.pipeline.top_k} passages per query`,
                          ],
                          [
                            Sparkles,
                            "Answers",
                            generation === "extractive"
                              ? "Exact source extracts"
                              : "Grounded generation",
                          ],
                        ].map(([Icon, title, detail]) => {
                          const I = Icon as typeof Upload;
                          return (
                            <div key={String(title)}>
                              <div className="flow-icon">
                                <I size={22} />
                              </div>
                              <strong>{String(title)}</strong>
                              <span>{String(detail)}</span>
                            </div>
                          );
                        })}
                      </div>
                      <div className="panel-foot">
                        <ShieldCheck size={16} />
                        Private by default. Every answer has inspectable
                        evidence.
                        <button onClick={() => setSection("Pipeline")}>
                          Configure pipeline
                        </button>
                      </div>
                    </section>
                    <section className="panel">
                      <div className="panel-heading">
                        <h2>Build your first answer</h2>
                      </div>
                      <div className="checklist">
                        {[
                          [
                            true,
                            "Project created",
                            "Your isolated knowledge workspace is ready.",
                          ],
                          [
                            docs.some((d) => d.status === "ready"),
                            "Add your documents",
                            "PDF, DOCX, Markdown, TXT or textual CSV.",
                          ],
                          [
                            !!project?.query_count,
                            "Test in the playground",
                            "Ask a question and inspect its sources.",
                          ],
                          [
                            keys.length > 0,
                            "Connect your application",
                            "Create a scoped API credential.",
                          ],
                        ].map(([done, title, detail], i) => (
                          <button
                            key={String(title)}
                            onClick={() =>
                              setSection(
                                i === 1
                                  ? "Documents"
                                  : i === 2
                                    ? "Playground"
                                    : "API & Integration",
                              )
                            }
                          >
                            <span className={done ? "check done" : "check"}>
                              {done ? <Check size={14} /> : i + 1}
                            </span>
                            <span>
                              <strong>{String(title)}</strong>
                              <small>{String(detail)}</small>
                            </span>
                          </button>
                        ))}
                      </div>
                    </section>
                  </div>
                  <section className="panel">
                    <div className="panel-heading">
                      <h2>Recent sources</h2>
                      <button
                        className="text-button"
                        onClick={() => setSection("Documents")}
                      >
                        View all documents
                      </button>
                    </div>
                    {!docs.length ? (
                      <Empty title="A little knowledge goes a long way">
                        Upload your first document to start building.
                      </Empty>
                    ) : (
                      <div className="source-list">
                        {docs.slice(0, 4).map((d) => (
                          <button
                            key={d.id}
                            onClick={() => setSection("Documents")}
                          >
                            <div className="file-icon">
                              <FileText size={20} />
                            </div>
                            <span>
                              <strong>{d.name}</strong>
                              <small>
                                {bytes(d.size_bytes)} · {d.chunk_count} chunks
                              </small>
                            </span>
                            <Status value={d.status} />
                          </button>
                        ))}
                      </div>
                    )}
                  </section>
                </>
              )}
              {section === "Documents" && (
                <>
                  <input
                    ref={inputRef}
                    type="file"
                    hidden
                    multiple
                    accept=".pdf,.docx,.txt,.md,.csv"
                    onChange={(e) => uploadFiles(e.target.files)}
                  />
                  <div
                    className="upload-zone"
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                      e.preventDefault();
                      if (!busy) uploadFiles(e.dataTransfer.files);
                    }}
                  >
                    <div className="upload-icon">
                      <Upload size={25} />
                    </div>
                    <h2>Give your assistant something to know.</h2>
                    <p>
                      Drop documents here, or{" "}
                      <button
                        disabled={!!busy}
                        onClick={() => inputRef.current?.click()}
                      >
                        browse files
                      </button>
                    </p>
                    <span>
                      PDF · DOCX · TXT · Markdown · Textual CSV &nbsp; / &nbsp;
                      20 MB per file by default
                    </span>
                  </div>
                  <div className="info-line">
                    <ShieldCheck size={17} />
                    <span>
                      Files stay private to this project. PDFs need selectable
                      text. CSV supports text and FAQs; numerical analysis
                      requires a different tool.
                    </span>
                  </div>
                  <section className="panel">
                    <div className="panel-heading">
                      <h2>
                        Documents <span className="count">{docs.length}</span>
                      </h2>
                      <button
                        className="secondary small"
                        disabled={!!busy}
                        onClick={() => void task("Refreshing", loadDocs)}
                      >
                        <RefreshCw size={14} />
                        Refresh
                      </button>
                    </div>
                    {!docs.length ? (
                      <Empty icon={FileText} title="No sources yet">
                        Your uploaded documents and their processing status will
                        appear here.
                      </Empty>
                    ) : (
                      <div className="table-scroll">
                        <table>
                          <thead>
                            <tr>
                              <th>Source</th>
                              <th>Status</th>
                              <th>Chunks</th>
                              <th>Size</th>
                              <th>Actions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {docs.map((d) => (
                              <tr key={d.id}>
                                <td>
                                  <button
                                    className="document-name"
                                    onClick={() =>
                                      void task("Loading source", async () => {
                                        setPreview(
                                          await api(
                                            base + "/documents/" + d.id,
                                          ),
                                        );
                                      })
                                    }
                                  >
                                    <FileText size={19} />
                                    <span>
                                      <strong>{d.name}</strong>
                                      <small>
                                        {d.kind.toUpperCase()}
                                        {d.error ? ` · ${d.error}` : ""}
                                      </small>
                                    </span>
                                  </button>
                                </td>
                                <td>
                                  <Status value={d.status} />
                                </td>
                                <td>{d.chunk_count}</td>
                                <td>{bytes(d.size_bytes)}</td>
                                <td>
                                  <div className="actions">
                                    {d.status === "failed" && (
                                      <button
                                        title="Retry processing"
                                        disabled={!!busy}
                                        onClick={() =>
                                          void task("Retrying", async () => {
                                            const job = jobs.find(
                                              (j) =>
                                                j.document_id === d.id &&
                                                j.status === "failed",
                                            );
                                            if (job)
                                              await api(
                                                base +
                                                  "/jobs/" +
                                                  job.id +
                                                  "/retry",
                                                { method: "POST" },
                                              );
                                            await loadDocs();
                                          })
                                        }
                                      >
                                        <RefreshCw size={16} />
                                        Retry
                                      </button>
                                    )}
                                    <button
                                      aria-label={`Delete ${d.name}`}
                                      disabled={!!busy}
                                      onClick={() => {
                                        if (
                                          window.confirm(
                                            `Delete ${d.name}? Its chunks, project conversation history and stored evaluation results will be removed.`,
                                          )
                                        )
                                          void task(
                                            "Deleting document",
                                            async () => {
                                              await api(
                                                base + "/documents/" + d.id,
                                                { method: "DELETE" },
                                              );
                                              await loadDocs();
                                              await refreshProjects();
                                              setMessages([]);
                                              setConversationId(null);
                                            },
                                          );
                                      }}
                                    >
                                      <Trash2 size={16} />
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </section>
                  {jobs.length > 0 && (
                    <details className="panel jobs">
                      <summary>
                        Processing jobs{" "}
                        <span className="muted">{jobs.length} recorded</span>
                      </summary>
                      {jobs.slice(0, 20).map((j) => (
                        <div className="job" key={j.id}>
                          <code>{j.id.slice(0, 8)}</code>
                          <Status value={j.status} />
                          <span>Attempt {j.attempts}/3</span>
                          <small>{j.error}</small>
                        </div>
                      ))}
                    </details>
                  )}
                </>
              )}
              {section === "Pipeline" && pipeline && (
                <div className="two-col">
                  <form
                    className="panel form-panel"
                    onSubmit={(e) => {
                      e.preventDefault();
                      void task("Saving pipeline", async () => {
                        await api(base + "/pipeline", {
                          method: "PUT",
                          body: JSON.stringify(pipeline),
                        });
                        const p = await api<{ reindex_required: boolean }>(
                          base + "/pipeline",
                        );
                        setReindex(p.reindex_required);
                        await refreshProjects();
                        setNotice(
                          "Pipeline saved. Rebuild the index if chunk settings changed.",
                        );
                      });
                    }}
                  >
                    <div className="panel-heading">
                      <h2>Retrieval configuration</h2>
                      <span className="tag">v{project?.pipeline_version}</span>
                    </div>
                    <label>
                      Retrieval strategy
                      <select
                        value={pipeline.strategy}
                        onChange={(e) =>
                          setPipeline({
                            ...pipeline,
                            strategy: e.target.value as Pipeline["strategy"],
                          })
                        }
                      >
                        <option value="hybrid">
                          Hybrid · vector + keyword
                        </option>
                        <option value="vector">Vector similarity</option>
                        <option value="keyword">Keyword retrieval</option>
                      </select>
                    </label>
                    <div className="form-row">
                      <label>
                        Chunk size (words)
                        <input
                          type="number"
                          min={60}
                          max={1000}
                          value={pipeline.chunk_size}
                          onChange={(e) =>
                            setPipeline({
                              ...pipeline,
                              chunk_size: Number(e.target.value),
                              auto: false,
                            })
                          }
                        />
                      </label>
                      <label>
                        Overlap (words)
                        <input
                          type="number"
                          min={0}
                          max={200}
                          value={pipeline.overlap}
                          onChange={(e) =>
                            setPipeline({
                              ...pipeline,
                              overlap: Number(e.target.value),
                              auto: false,
                            })
                          }
                        />
                      </label>
                    </div>
                    <div className="form-row">
                      <label>
                        Retrieved passages
                        <input
                          type="number"
                          min={1}
                          max={15}
                          value={pipeline.top_k}
                          onChange={(e) =>
                            setPipeline({
                              ...pipeline,
                              top_k: Number(e.target.value),
                            })
                          }
                        />
                      </label>
                      <label>
                        Minimum evidence score
                        <input
                          type="number"
                          min={0.05}
                          max={0.9}
                          step={0.01}
                          value={pipeline.min_score}
                          onChange={(e) =>
                            setPipeline({
                              ...pipeline,
                              min_score: Number(e.target.value),
                            })
                          }
                        />
                      </label>
                    </div>
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={pipeline.auto}
                        onChange={(e) =>
                          setPipeline({ ...pipeline, auto: e.target.checked })
                        }
                      />
                      Select initial defaults from the first document
                    </label>
                    <button className="primary" disabled={!!busy}>
                      Save configuration
                    </button>
                  </form>
                  <div className="stack">
                    <section className="panel form-panel">
                      <div className="panel-heading">
                        <h2>Why this pipeline?</h2>
                        <Sparkles size={18} />
                      </div>
                      <p>{reason}</p>
                      <dl>
                        <dt>Embedding provider</dt>
                        <dd>
                          {provider === "local"
                            ? "Local feature hashing · 384 dimensions"
                            : "OpenAI embeddings"}
                        </dd>
                        <dt>Answer provider</dt>
                        <dd>
                          {generation === "extractive"
                            ? "Extractive · exact supporting sentences"
                            : "OpenAI Responses · quoted evidence"}
                        </dd>
                      </dl>
                      <p className="muted">
                        Provider models are configured by the server operator
                        through environment variables. Local embeddings match
                        vocabulary; they do not understand synonyms.
                      </p>
                    </section>
                    <section className="panel form-panel">
                      <h2>Index lifecycle</h2>
                      <p>
                        {reindex
                          ? "Chunk settings changed. Rebuild to apply them to existing sources."
                          : "Your chunk settings match the indexed sources."}
                      </p>
                      <button
                        className="secondary"
                        disabled={!!busy || !docs.length}
                        onClick={() =>
                          void task("Rebuilding index", async () => {
                            const r = await api<{ queued: number }>(
                              base + "/reindex",
                              { method: "POST" },
                            );
                            await loadDocs();
                            setNotice(
                              `${r.queued} documents queued for reindexing.`,
                            );
                          })
                        }
                      >
                        <RefreshCw size={16} />
                        Rebuild index
                      </button>
                    </section>
                  </div>
                </div>
              )}
              {section === "Playground" && (
                <div className="playground-grid">
                  <section className="panel chat-panel">
                    <div className="chat-top">
                      <span>
                        <span className="assistant-dot" />
                        Knowledge assistant
                      </span>
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          checked={retrieval}
                          onChange={(e) => setRetrieval(e.target.checked)}
                        />
                        Show retrieval
                      </label>
                    </div>
                    <div className="chat-messages">
                      {!messages.length ? (
                        <div className="chat-empty">
                          <div className="hero-symbol">
                            <Sparkles size={30} />
                          </div>
                          <h2>Ask your knowledge.</h2>
                          <p>
                            {docs.some((d) => d.status === "ready")
                              ? "Every answer starts with your sources. Ask a specific question, then inspect the evidence."
                              : "Upload a document and wait for indexing to ask your first question."}
                          </p>
                          {docs.some((d) => d.status === "ready") && (
                            <button
                              className="suggestion"
                              onClick={() =>
                                setQuestion("What do the documents say about ")
                              }
                            >
                              Start with “What do the documents say about…”
                            </button>
                          )}
                        </div>
                      ) : (
                        messages.map((m, i) => (
                          <div key={i} className="chat-turn">
                            <div className="user-question">
                              <span className="avatar">YOU</span>
                              <p>{m.question}</p>
                            </div>
                            <div className="assistant-answer">
                              <span className="answer-icon">
                                <Sparkles size={18} />
                              </span>
                              <div>
                                <div className="answer-label">
                                  {brand}
                                  <span>
                                    {m.result.latency_ms.toFixed(0)} ms ·{" "}
                                    {m.result.generation_provider}
                                  </span>
                                </div>
                                <p className="answer-text">{m.result.answer}</p>
                                {m.result.refused ? (
                                  <span className="tag amber">
                                    Insufficient evidence
                                  </span>
                                ) : (
                                  <div className="citations">
                                    {m.result.citations.map((c, j) => (
                                      <SourceCard source={c} key={j} />
                                    ))}
                                  </div>
                                )}
                                {retrieval && (
                                  <details className="retrieval" open>
                                    <summary>
                                      {m.result.retrieved.length} retrieved
                                      passages
                                    </summary>
                                    {m.result.retrieved.map((c) => (
                                      <SourceCard key={c.chunk_id} source={c} />
                                    ))}
                                  </details>
                                )}
                              </div>
                            </div>
                          </div>
                        ))
                      )}
                      {busy === "Finding evidence" && (
                        <div className="thinking">
                          <LoaderCircle className="spin" size={17} />
                          Retrieving passages and checking evidence…
                        </div>
                      )}
                      <div ref={chatEnd} />
                    </div>
                    <form className="chat-composer" onSubmit={ask}>
                      <textarea
                        rows={2}
                        aria-label="Your question"
                        value={question}
                        onChange={(e) => setQuestion(e.target.value)}
                        placeholder="Ask a question about your documents…"
                        maxLength={2000}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && !e.shiftKey) {
                            e.preventDefault();
                            ask();
                          }
                        }}
                      />
                      <button
                        className="primary icon-only"
                        aria-label="Send question"
                        disabled={
                          !!busy ||
                          !question.trim() ||
                          !docs.some((d) => d.status === "ready")
                        }
                      >
                        <Send size={18} />
                      </button>
                    </form>
                    <div className="chat-disclaimer">
                      {generation === "extractive"
                        ? "Answers quote source text. Retrieved passages may contain errors."
                        : "AI answers can be wrong. Check the cited passages."}{" "}
                      Each question retrieves independently.
                    </div>
                  </section>
                  <aside className="stack">
                    <section className="panel form-panel">
                      <h2>Project context</h2>
                      <div className="context-stat">
                        <FileText size={17} />
                        <span>
                          {docs.filter((d) => d.status === "ready").length}{" "}
                          ready sources
                        </span>
                      </div>
                      <div className="context-stat">
                        <Database size={17} />
                        <span>{project?.chunk_count} indexed chunks</span>
                      </div>
                      <div className="context-stat">
                        <Layers3 size={17} />
                        <span>{project?.pipeline.strategy} retrieval</span>
                      </div>
                      <p className="muted">
                        Answers are grounded in the current index. No supporting
                        evidence means an honest refusal.
                      </p>
                    </section>
                    <section className="panel form-panel">
                      <h2>Conversation history</h2>
                      {history.length ? (
                        history.map((h) => (
                          <button
                            className="history-item"
                            key={h.id}
                            disabled={!!busy}
                            onClick={() =>
                              void task("Loading conversation", async () => {
                                setMessages(
                                  await api<Message[]>(
                                    base + "/conversations/" + h.id,
                                  ),
                                );
                                setConversationId(h.id);
                              })
                            }
                          >
                            <MessageSquare size={14} />
                            {h.title}
                          </button>
                        ))
                      ) : (
                        <p className="muted">
                          Your conversations will appear here.
                        </p>
                      )}
                    </section>
                  </aside>
                </div>
              )}
              {section === "API & Integration" && (
                <>
                  <div className="two-col">
                    <section className="panel form-panel">
                      <div className="panel-heading">
                        <h2>Project credentials</h2>
                        <ShieldCheck size={18} />
                      </div>
                      <p>
                        Create an API key with only the permissions your
                        application needs.
                      </p>
                      <form
                        onSubmit={(e) => {
                          e.preventDefault();
                          void task("Creating API key", async () => {
                            const k = await api<{ secret: string }>(
                              base + "/keys",
                              {
                                method: "POST",
                                body: JSON.stringify({
                                  name: keyName,
                                  scopes: manageDocs
                                    ? ["query", "read", "documents"]
                                    : ["query", "read"],
                                }),
                              },
                            );
                            setSecret(k.secret);
                            setKeys(await api(base + "/keys"));
                          });
                        }}
                      >
                        <label>
                          Key name
                          <input
                            required
                            maxLength={100}
                            value={keyName}
                            onChange={(e) => setKeyName(e.target.value)}
                          />
                        </label>
                        <label className="checkbox">
                          <input
                            type="checkbox"
                            checked={manageDocs}
                            onChange={(e) => setManageDocs(e.target.checked)}
                          />
                          Allow document upload, deletion and retry
                        </label>
                        <button className="primary" disabled={!!busy}>
                          <Plus size={16} />
                          Create API key
                        </button>
                      </form>
                      {secret && (
                        <div className="secret-box">
                          <strong>
                            Copy this key now. It is shown only once.
                          </strong>
                          <code>{secret}</code>
                          <button
                            className="secondary small"
                            onClick={() => copy(secret)}
                          >
                            <Copy size={14} />
                            Copy key
                          </button>
                          <button
                            className="text-button"
                            onClick={() => setSecret("")}
                          >
                            Dismiss secret
                          </button>
                        </div>
                      )}
                      {keys.map((k) => (
                        <div className="key-row" key={k.id}>
                          <div>
                            <strong>{k.name}</strong>
                            <code>{k.prefix}…</code>
                            <small>{k.scopes.join(" · ")}</small>
                          </div>
                          <button
                            className="icon-button danger-text"
                            aria-label={`Revoke ${k.name}`}
                            disabled={!!busy}
                            onClick={() => {
                              if (
                                confirm(
                                  "Revoke this API key? Applications using it will lose access.",
                                )
                              )
                                void task("Revoking key", async () => {
                                  await api(base + "/keys/" + k.id, {
                                    method: "DELETE",
                                  });
                                  setKeys(await api(base + "/keys"));
                                  setSecret("");
                                });
                            }}
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      ))}
                    </section>
                    <section className="panel form-panel">
                      <h2>Quick integration</h2>
                      <p>
                        Use your project key from a trusted server. Keep private
                        keys out of browser code.
                      </p>
                      <div className="tabs">
                        {["cURL", "Python", "JavaScript"].map((l) => (
                          <button
                            className={l === language ? "active" : ""}
                            onClick={() => setLanguage(l)}
                            key={l}
                          >
                            {l}
                          </button>
                        ))}
                      </div>
                      <pre>
                        <code>{integration(language, selected)}</code>
                      </pre>
                      <button
                        className="secondary small"
                        onClick={() => copy(integration(language, selected))}
                      >
                        <Copy size={14} />
                        Copy example
                      </button>
                      <a
                        className="inline-link"
                        href="/api/docs"
                        target="_blank"
                        rel="noreferrer"
                      >
                        Explore the OpenAPI reference
                      </a>
                    </section>
                  </div>
                  <div className="info-line">
                    <ShieldCheck size={18} />
                    <span>
                      Keys are scoped to this project and stored as SHA-256
                      hashes. Requests are limited per credential. Widget
                      publication uses a separate query-only token.
                    </span>
                  </div>
                </>
              )}
              {section === "Evaluation" && (
                <>
                  <div className="two-col">
                    <section className="panel form-panel">
                      <h2>Add a verified test case</h2>
                      <p>
                        Ground truth comes from your review. Label relevant
                        sources and the expected behavior.
                      </p>
                      <form
                        onSubmit={(e) => {
                          e.preventDefault();
                          void task("Adding test case", async () => {
                            await api(base + "/evaluation/cases", {
                              method: "POST",
                              body: JSON.stringify({
                                question: caseQuestion,
                                relevant_document_ids: caseDoc ? [caseDoc] : [],
                                expected_answer: caseAnswer,
                                expect_refusal: expectRefusal,
                                verified: true,
                              }),
                            });
                            setCaseQuestion("");
                            setCaseAnswer("");
                            await loadEvaluation();
                          });
                        }}
                      >
                        <label>
                          Question
                          <input
                            required
                            minLength={2}
                            maxLength={2000}
                            value={caseQuestion}
                            onChange={(e) => setCaseQuestion(e.target.value)}
                            placeholder="What is our refund period?"
                          />
                        </label>
                        <label>
                          Relevant source
                          <select
                            value={caseDoc}
                            onChange={(e) => setCaseDoc(e.target.value)}
                          >
                            <option value="">
                              No relevant source / refusal test
                            </option>
                            {docs.map((d) => (
                              <option key={d.id} value={d.id}>
                                {d.name}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Expected answer (optional)
                          <textarea
                            rows={2}
                            value={caseAnswer}
                            onChange={(e) => setCaseAnswer(e.target.value)}
                            maxLength={3000}
                          />
                        </label>
                        <label className="checkbox">
                          <input
                            type="checkbox"
                            checked={expectRefusal}
                            onChange={(e) => setExpectRefusal(e.target.checked)}
                          />
                          This question should be refused
                        </label>
                        <button className="primary" disabled={!!busy}>
                          <Plus size={16} />
                          Add verified case
                        </button>
                      </form>
                    </section>
                    <section className="panel form-panel">
                      <h2>Test your pipeline</h2>
                      <p>
                        Measure recall@k against labeled documents, citation
                        provenance, refusal behavior and latency.
                      </p>
                      <button
                        className="secondary"
                        disabled={
                          !!busy || !docs.some((d) => d.status === "ready")
                        }
                        onClick={() =>
                          void task("Generating questions", async () => {
                            await api(base + "/evaluation/generate", {
                              method: "POST",
                            });
                            await loadEvaluation();
                          })
                        }
                      >
                        <Sparkles size={16} />
                        Generate candidate questions
                      </button>
                      <p className="muted">
                        Generated questions use source keywords. They are
                        unverified candidates and excluded from runs by default.
                      </p>
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          checked={includeSynthetic}
                          onChange={(e) =>
                            setIncludeSynthetic(e.target.checked)
                          }
                        />
                        Include unverified candidates in this run
                      </label>
                      <button
                        className="primary"
                        disabled={!!busy || !cases.length}
                        onClick={() =>
                          void task("Running evaluation", async () => {
                            await api(base + "/evaluation/runs", {
                              method: "POST",
                              body: JSON.stringify({
                                include_unverified: includeSynthetic,
                              }),
                            });
                            await loadEvaluation();
                          })
                        }
                      >
                        {busy === "Running evaluation" ? (
                          <LoaderCircle size={16} className="spin" />
                        ) : (
                          <FlaskConical size={16} />
                        )}
                        Run evaluation
                      </button>
                      <div className="metric-note">
                        <strong>Semantic faithfulness: not assessed</strong>
                        <p>
                          Exact quote checks verify that evidence exists. They
                          do not establish that generated claims follow from it.
                        </p>
                      </div>
                    </section>
                  </div>
                  <section className="panel">
                    <div className="panel-heading">
                      <h2>
                        Test set <span className="count">{cases.length}</span>
                      </h2>
                      <span className="muted">
                        {cases.filter((c) => c.verified).length} verified
                      </span>
                    </div>
                    {cases.length ? (
                      <div className="eval-cases">
                        {cases.map((c) => (
                          <div key={c.id}>
                            <span>
                              <strong>{c.question}</strong>
                              <small>
                                {c.verified
                                  ? "Manually verified"
                                  : "Synthetic · unverified"}{" "}
                                ·{" "}
                                {c.expect_refusal
                                  ? "Refusal expected"
                                  : `${c.relevant_document_ids.length} labeled sources`}
                              </small>
                            </span>
                            <button
                              className="icon-button"
                              aria-label="Delete case"
                              disabled={!!busy}
                              onClick={() =>
                                void task("Deleting case", async () => {
                                  await api(
                                    base + "/evaluation/cases/" + c.id,
                                    { method: "DELETE" },
                                  );
                                  await loadEvaluation();
                                })
                              }
                            >
                              <Trash2 size={15} />
                            </button>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <Empty icon={FlaskConical} title="No test cases yet">
                        Add a question with known supporting evidence to measure
                        recall.
                      </Empty>
                    )}
                  </section>
                  {runs.map((run, i) => (
                    <details
                      className="panel evaluation-run"
                      key={run.id}
                      open={i === 0}
                    >
                      <summary>
                        <strong>Evaluation · {time(run.created_at)}</strong>
                        <span>
                          {run.result.case_count} cases ·{" "}
                          {run.result.verified_count} verified ·{" "}
                          {run.result.synthetic_count} synthetic
                        </span>
                      </summary>
                      <div className="evaluation-metrics">
                        {[
                          "recall_at_k",
                          "citation_validity",
                          "refusal_correct",
                          "latency_ms",
                        ].map((k) => (
                          <div key={k}>
                            <span>
                              {
                                (
                                  {
                                    recall_at_k: "Document recall@k",
                                    citation_validity: "Citation provenance",
                                    refusal_correct: "Refusal agreement",
                                    latency_ms: "Mean latency",
                                  } as Record<string, string>
                                )[k]
                              }
                            </span>
                            <strong>
                              {run.result.metrics[k] == null
                                ? "Not labeled"
                                : k === "latency_ms"
                                  ? `${run.result.metrics[k]?.toFixed(0)} ms`
                                  : `${(run.result.metrics[k]! * 100).toFixed(0)}%`}
                            </strong>
                          </div>
                        ))}
                      </div>
                      <div className="run-results">
                        {run.result.cases.map((c, j) => (
                          <details key={j}>
                            <summary>
                              <span>{c.question}</span>
                              <span
                                className={
                                  c.refusal_correct
                                    ? "teal-text"
                                    : "danger-text"
                                }
                              >
                                {c.refusal_correct
                                  ? "Expected behavior"
                                  : "Needs review"}
                              </span>
                            </summary>
                            <p>{c.answer}</p>
                            <small>
                              {c.verified ? "Verified case" : "Unverified case"}{" "}
                              · {c.latency_ms.toFixed(0)} ms · recall{" "}
                              {c.recall_at_k ?? "unlabeled"}
                            </small>
                          </details>
                        ))}
                      </div>
                    </details>
                  ))}
                </>
              )}
              {section === "Deployment" && (
                <div className="two-col">
                  <section className="panel form-panel">
                    <h2>Embeddable assistant</h2>
                    <p>
                      Publish a query-only assistant for an external website.
                      Publication makes every indexed source in this project
                      accessible through answers.
                    </p>
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        void task("Saving widget", async () => {
                          const w = await api<Widget>(base + "/widget", {
                            method: "PUT",
                            body: JSON.stringify({
                              ...widget,
                              allowed_origins: origins
                                .split(/[\n,]+/)
                                .map((x) => x.trim())
                                .filter(Boolean),
                            }),
                          });
                          setWidget(w);
                          setWidgetToken(w.token || "");
                          setNotice(
                            w.enabled
                              ? "Widget published locally. Copy the new embed code; previous tokens are invalid."
                              : "Widget access disabled and token revoked.",
                          );
                        });
                      }}
                    >
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          checked={widget.enabled}
                          onChange={(e) =>
                            setWidget({ ...widget, enabled: e.target.checked })
                          }
                        />
                        Enable public query access for this project
                      </label>
                      <label>
                        Assistant title
                        <input
                          value={widget.title}
                          maxLength={80}
                          required
                          onChange={(e) =>
                            setWidget({ ...widget, title: e.target.value })
                          }
                        />
                      </label>
                      <label>
                        Welcome message
                        <textarea
                          value={widget.welcome}
                          maxLength={300}
                          onChange={(e) =>
                            setWidget({ ...widget, welcome: e.target.value })
                          }
                        />
                      </label>
                      <div className="form-row">
                        <label>
                          Accent color
                          <input
                            type="color"
                            value={widget.color}
                            onChange={(e) =>
                              setWidget({ ...widget, color: e.target.value })
                            }
                          />
                        </label>
                        <label>
                          Appearance
                          <select
                            value={widget.theme}
                            onChange={(e) =>
                              setWidget({
                                ...widget,
                                theme: e.target.value as Widget["theme"],
                              })
                            }
                          >
                            <option value="dark">Dark</option>
                            <option value="light">Light</option>
                          </select>
                        </label>
                      </div>
                      <label>
                        Allowed website origins (one per line)
                        <textarea
                          placeholder="https://example.com"
                          value={origins}
                          onChange={(e) => setOrigins(e.target.value)}
                          rows={3}
                        />
                      </label>
                      <button className="primary" disabled={!!busy}>
                        <Globe size={16} />
                        {widget.enabled
                          ? "Save and rotate public token"
                          : "Save private state"}
                      </button>
                    </form>
                    {widgetToken && (
                      <div className="secret-box">
                        <strong>Embed code · save it now</strong>
                        <pre>
                          <code>{`<script src="${typeof window !== "undefined" ? window.location.origin : ""}/widget.js" data-project="${selected}" data-token="${widgetToken}" defer></script>`}</code>
                        </pre>
                        <button
                          className="secondary small"
                          onClick={() =>
                            copy(
                              `<script src="${window.location.origin}/widget.js" data-project="${selected}" data-token="${widgetToken}" defer></script>`,
                            )
                          }
                        >
                          <Copy size={14} />
                          Copy embed code
                        </button>
                      </div>
                    )}
                  </section>
                  <div className="stack">
                    <section className="panel form-panel">
                      <h2>Deployment foundation</h2>
                      <div className="deployment-state">
                        <ShieldCheck size={24} />
                        <div>
                          <strong>Local deployment</strong>
                          <span>Docker Compose + PostgreSQL / pgvector</span>
                        </div>
                      </div>
                      <p>
                        The dashboard, API and durable worker run as separate
                        services. Start them with the repository’s documented
                        configuration.
                      </p>
                      <pre>
                        <code>docker compose up --build</code>
                      </pre>
                      <p className="muted">
                        Internet hosting, HTTPS and provider credentials are
                        operator-managed. This workspace has not been deployed
                        publicly.
                      </p>
                    </section>
                    <section className="panel form-panel">
                      <h2>Project manifest</h2>
                      <p>
                        Download the versioned pipeline configuration and source
                        checksums. Secrets and document contents are excluded.
                      </p>
                      <button
                        className="secondary"
                        disabled={!!busy}
                        onClick={() =>
                          void task("Exporting manifest", async () =>
                            download(
                              await api(base + "/manifest"),
                              "ragforge-manifest.json",
                            ),
                          )
                        }
                      >
                        <Braces size={16} />
                        Download configuration
                      </button>
                      <p className="muted">
                        Standalone source package export is planned for the next
                        milestone.
                      </p>
                    </section>
                  </div>
                </div>
              )}
              {section === "Settings" && (
                <div className="two-col">
                  <form
                    className="panel form-panel"
                    onSubmit={(e) => {
                      e.preventDefault();
                      void task("Updating project", async () => {
                        await api(base, {
                          method: "PATCH",
                          body: JSON.stringify({ name, description }),
                        });
                        await refreshProjects();
                        setNotice("Project updated.");
                      });
                    }}
                  >
                    <h2>Project details</h2>
                    <label>
                      Project name
                      <input
                        required
                        maxLength={100}
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                      />
                    </label>
                    <label>
                      Description
                      <textarea
                        maxLength={500}
                        rows={4}
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                      />
                    </label>
                    <label>
                      Project ID<code className="read-only">{selected}</code>
                    </label>
                    <button className="primary" disabled={!!busy}>
                      Save changes
                    </button>
                  </form>
                  <section className="panel form-panel danger-panel">
                    <h2>Delete project</h2>
                    <p>
                      Permanently delete this project, uploaded files, indexed
                      chunks, API keys, conversations and evaluation history.
                    </p>
                    <button
                      className="danger"
                      disabled={!!busy}
                      onClick={() => {
                        if (
                          confirm(
                            `Permanently delete ${project?.name} and all its data?`,
                          )
                        )
                          void task("Deleting project", async () => {
                            await api(base, { method: "DELETE" });
                            const p = await refreshProjects();
                            setSelected(p[0]?.id || "");
                            setSection("Overview");
                            setNotice("Project deleted.");
                          });
                      }}
                    >
                      <Trash2 size={16} />
                      Delete project
                    </button>
                  </section>
                </div>
              )}
            </>
          )}
        </main>
        <footer className="footer">
          <span>{brand} / knowledge infrastructure</span>
          <span>Private workspace · v0.1</span>
        </footer>
      </div>
      {create && (
        <Modal label="create-title" onClose={() => setCreate(false)}>
          <section className="modal">
            <button
              className="modal-close"
              aria-label="Close"
              onClick={() => setCreate(false)}
            >
              <X size={19} />
            </button>
            <div className="hero-symbol small-symbol">
              <Boxes size={25} />
            </div>
            <h2 id="create-title">Create a project</h2>
            <p>A private home for your sources, pipeline and assistant.</p>
            <form onSubmit={addProject}>
              <label>
                Project name
                <input
                  autoFocus
                  required
                  maxLength={100}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Developer documentation"
                />
              </label>
              <label>
                Description (optional)
                <textarea
                  maxLength={500}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="What should this assistant know?"
                />
              </label>
              {error && <p className="alert error">{error}</p>}
              <button className="primary wide" disabled={!!busy}>
                {busy || "Create project"}
              </button>
            </form>
          </section>
        </Modal>
      )}
      {preview && (
        <Modal label="source-title" onClose={() => setPreview(null)}>
          <section className="modal wide-modal">
            <button
              className="modal-close"
              aria-label="Close source preview"
              onClick={() => setPreview(null)}
            >
              <X size={19} />
            </button>
            <h2 id="source-title">{preview.name}</h2>
            <p>Extracted passages · first 100 chunks</p>
            <div className="chunk-preview">
              {preview.chunks.length ? (
                preview.chunks.map((c, i) => (
                  <div key={c.id}>
                    <span className="eyebrow">
                      CHUNK {i + 1} ·{" "}
                      {Object.entries(c.locator)
                        .map(([k, v]) => `${k}: ${v}`)
                        .join(" · ")}
                    </span>
                    <p>{c.text}</p>
                  </div>
                ))
              ) : (
                <p>No indexed passages yet. Check processing status.</p>
              )}
            </div>
          </section>
        </Modal>
      )}
    </div>
  );
}

function Metric({
  label,
  value,
  detail,
  icon: Icon,
}: {
  label: string;
  value: string;
  detail: string;
  icon: typeof FileText;
}) {
  return (
    <div className="metric">
      <div>
        <span>{label}</span>
        <Icon size={18} />
      </div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}
function integration(language: string, project: string) {
  const url = `http://localhost:8000/v1/projects/${project}/query`;
  if (language === "Python")
    return `import os\nimport httpx\n\nresponse = httpx.post(\n    "${url}",\n    headers={"Authorization": "Bearer " + os.environ["RAGFORGE_API_KEY"]},\n    json={"question": "What is our refund policy?"},\n    timeout=120,\n)\nresponse.raise_for_status()\nprint(response.json())`;
  if (language === "JavaScript")
    return `// Run server-side with Node.js\nconst response = await fetch(\n  "${url}",\n  {\n    method: "POST",\n    headers: {\n      Authorization: \`Bearer \${process.env.RAGFORGE_API_KEY}\`,\n      "Content-Type": "application/json"\n    },\n    body: JSON.stringify({\n      question: "What is our refund policy?"\n    })\n  }\n);\nif (!response.ok) throw new Error(await response.text());\nconsole.log(await response.json());`;
  return `curl "${url}" \\\n  -H "Authorization: Bearer $RAGFORGE_API_KEY" \\\n  -H "Content-Type: application/json" \\\n  -d '{"question":"What is our refund policy?"}'`;
}
