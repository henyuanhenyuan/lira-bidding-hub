export interface Me {
  auth: boolean;
  username: string;
  role: string;
  actor?: string;
}

export interface EventRow {
  id: string;
  target_id: string;
  target_title?: string | null;
  ts: string;
  type: string;
  severity: "L1" | "L2" | "L3";
  gate_level: string;
  note?: string | null;
  evidence: string[];
  suppressed: number;
  my_price?: number | null;
}

export interface Suggestion {
  id: string;
  event_id: string;
  action: string;
  confidence: number;
  gate_level: string;
  narrative: string;
  generated_by: string;
  status: string;
  guardrail: string;
  guardrail_note?: string | null;
  target_price?: number | null;
  margin_at_target?: number | null;
  created_at: string;
  agent_run_id?: string | null;
  target_title?: string | null;
  event_type?: string | null;
  case_ids?: string[];
}

export interface EventDetail extends EventRow {
  price_low?: number;
  price_high?: number;
  point?: number;
  confidence?: number;
  missing_fields?: string[];
  suggestion: Suggestion | null;
  similar_cases: { id: string; summary: string; attribution: string; outcome_7d?: string }[];
}

export interface AgentRun {
  id: string;
  event_id: string;
  trigger: string;
  status: string;
  model: string;
  started_at: string;
  finished_at?: string | null;
  latency_ms?: number | null;
  step_count?: number;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  cost?: number | null;
  skill_id?: string | null;
}

export interface AgentStep {
  id: string;
  run_id: string;
  seq: number;
  kind: string;
  name: string;
  status: string;
  input: string | null;
  output: string | null;
  latency_ms: number;
  created_at: string;
}

export interface AgentRunDetail extends AgentRun {
  steps: AgentStep[];
  suggestion?: Suggestion | null;
}

export interface DocItem {
  id: string;
  title: string;
  source?: string | null;
  category?: string | null;
  version?: string | null;
  created_at: string;
  chunk_count: number;
}

export interface DocChunkHit {
  id: string;
  doc_id: string;
  doc_title?: string;
  chunk_no: number;
  content: string;
  score: number;
}

export interface EvalRunSummary {
  run_key: string;
  total: number;
  passed: number;
  accuracy: number;
  tier?: string | null;
  metrics?: Record<string, unknown> | null;
  created_at: string;
}

export interface EvalBadcase {
  case_name: string;
  segment: string;
  difficulty: string;
  reason: string;
  created_at: string;
}

export interface TraceSummary {
  trace_id: string;
  spans: number;
  started_at: string;
}

export interface TraceNode {
  id: string;
  name: string;
  kind: string;
  status: string;
  duration_ms: number;
  parent_id?: string | null;
  children: TraceNode[];
}

export interface Metrics {
  calls: number;
  fallback_rate: number;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  p99_latency_ms: number | null;
  tokens: number;
  cost: number;
  by_model: { model: string; calls: number; fallback: number; tokens: number; cost: number }[];
  by_kind: { kind: string; n: number; fallback: number }[];
}

export interface Health {
  ok: boolean;
  counts: Record<string, number>;
  last_ingest?: { received_at?: string } | null;
  collectors: { collector: string; c: number; last_ts: string }[];
  freshness: { stale?: boolean; lag_hours?: number; sla_hours?: number };
  vector_index: { indexed: number; cases: number; stale: boolean };
  llm_available: boolean;
}

export interface ToolSpec {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}
