export type Pipeline = {
  strategy: "vector" | "keyword" | "hybrid";
  chunk_size: number;
  overlap: number;
  top_k: number;
  min_score: number;
  semantic_min_score?: number;
  auto: boolean;
};
export type Project = {
  id: string;
  name: string;
  description: string;
  created_at: number;
  document_count: number;
  ready_count: number;
  chunk_count: number;
  query_count: number;
  pipeline: Pipeline;
  pipeline_version: number;
};
export type Doc = {
  id: string;
  name: string;
  kind: string;
  status: string;
  size_bytes: number;
  chunk_count: number;
  error: string | null;
  metadata_json: Record<string, unknown>;
};
export type Source = {
  chunk_id: string;
  document_id: string;
  document_name: string;
  text: string;
  quote?: string;
  number?: number;
  locator: Record<string, string | number>;
  score: number;
};
export type Result = {
  answer: string;
  citations: Source[];
  retrieved: Source[];
  refused: boolean;
  latency_ms: number;
  retrieval_latency_ms?: number;
  generation_latency_ms?: number;
  answer_kind?: string;
  conversation_id: string | null;
  generation_provider: string;
};
export type Message = { question: string; result: Result };
export type Job = {
  id: string;
  document_id: string;
  status: string;
  attempts: number;
  error: string | null;
};
export type Key = {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  last_used_at: number | null;
};
export type Case = {
  id: string;
  question: string;
  verified: boolean;
  origin: string;
  relevant_document_ids: string[];
  expect_refusal: boolean;
};
export type EvalResult = {
  case_count: number;
  verified_count: number;
  synthetic_count: number;
  metrics: Record<string, number | null>;
  semantic_faithfulness: string;
  notes: string;
  cases: {
    question: string;
    answer: string;
    recall_at_k: number | null;
    refusal_correct: boolean;
    verified: boolean;
    latency_ms: number;
  }[];
};
export type Widget = {
  enabled: boolean;
  title: string;
  welcome: string;
  color: string;
  theme: "light" | "dark";
  allowed_origins: string[];
  has_token?: boolean;
  token?: string | null;
};
