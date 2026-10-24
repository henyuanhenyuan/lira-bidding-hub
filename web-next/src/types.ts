export type Role = "admin" | "manager" | "member";
export type Severity = "L1" | "L2" | "L3";
export type GateLevel = "strong" | "confirm" | "observe";
export type Guardrail = "ok" | "warning" | "blocked" | "unknown";
export type SuggestionStatus =
  | "pending"
  | "submitted"
  | "approved"
  | "executed"
  | "accepted"
  | "rejected"
  | "cancelled"
  | "holdout";

export interface Me {
  auth: boolean;
  username: string;
  actor?: string;
  role: Role;
}

export interface Freshness {
  latest_ts: string | null;
  lag_hours: number | null;
  stale: boolean;
  sla_hours: number;
}

export interface Health {
  ok: boolean;
  counts: {
    targets: number;
    snapshots: number;
    events: number;
    suggestions: number;
    cases: number;
    mappings?: number;
    my_products?: number;
    reviews?: number;
    insights?: number;
  };
  freshness: Freshness;
  collectors: { collector: string; c: number; last_ts: string }[];
  llm_available: boolean;
}

export interface EventItem {
  id: string;
  target_id: string;
  ts: string;
  type: string;
  severity: Severity;
  gate_level: GateLevel;
  suppressed: number;
  note: string | null;
  evidence: string[];
  rule_version: string;
  target_title?: string | null;
  my_price?: number | null;
  snapshot_id?: string | null;
}

export interface Suggestion {
  id: string;
  event_id: string;
  action: string;
  impact_low: number | null;
  impact_high: number | null;
  confidence: number;
  gate_level: GateLevel;
  narrative: string;
  generated_by: string;
  status: SuggestionStatus;
  created_at: string;
  case_ids?: string[];
  target_price?: number | null;
  margin_at_target?: number | null;
  margin_floor?: number | null;
  guardrail?: Guardrail;
  guardrail_note?: string | null;
  executed_price?: number | null;
  submitted_by?: string | null;
  approved_by?: string | null;
  agent_run_id?: string | null;
  executed_at?: string | null;
  execution_id?: string | null;
  target_id?: string;
  event_type?: string;
  target_title?: string | null;
}

export interface ExecutionPlan {
  suggestion_id: string;
  action: string;
  target_id: string | null;
  target_title: string | null;
  sku: string | null;
  from_price: number | null;
  to_price: number;
  margin_at_target: number | null;
  margin_floor: number | null;
  guardrail: Guardrail;
  guardrail_note: string;
  mode: string;
  idempotency_key: string;
}

export interface Execution {
  id: string;
  suggestion_id: string;
  mode: string;
  status: string;
  request?: unknown;
  response?: unknown;
  external_id?: string | null;
  idempotency_key: string;
  actor?: string | null;
  error?: string | null;
  created_at: string;
  rolled_back_at?: string | null;
  plan?: ExecutionPlan;
  idempotent?: boolean;
}

export interface ExecutionPreview {
  plan: ExecutionPlan;
  configured: boolean;
  execution: Execution | null;
}

export interface OutcomeDue {
  id: string;
  event_id: string;
  action: string;
  status: string;
  created_at: string;
  executed_at: string | null;
  executed_price: number | null;
  target_id: string | null;
  event_ts: string | null;
  target_title: string | null;
  due_at: string;
  days_overdue: number;
  due: boolean;
  observed: {
    baseline_ts: string;
    baseline_price: number;
    after_ts: string;
    after_price: number;
    delta_pct: number | null;
  } | null;
}

export interface GateStatus {
  ok: boolean;
  enforced: boolean;
  thresholds: { min_accuracy: number; max_fallback_rate: number };
  reasons: string[];
  warnings: string[];
  latest_eval: {
    run_key: string;
    total: number;
    passed: number;
    accuracy: number;
    created_at: string;
  } | null;
  usage: {
    calls: number;
    tokens: number;
    cost: number;
    fallback_rate: number;
    budget_used_ratio: number | null;
  };
}

export interface AgentStep {
  id: string;
  run_id: string;
  seq: number;
  kind: string;
  name: string;
  status: string;
  input: unknown;
  output: unknown;
  latency_ms: number | null;
  created_at: string;
}

export interface AgentRun {
  id: string;
  event_id: string;
  suggestion_id: string | null;
  trigger: string;
  status: string;
  model: string | null;
  plan: unknown;
  step_count: number;
  latency_ms: number | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  cost?: number | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
  event_type?: string | null;
  severity?: Severity | null;
  target_title?: string | null;
}

export interface AgentRunDetail extends AgentRun {
  steps: AgentStep[];
}

export interface CaseItem {
  id: string;
  category: string;
  event_type: string;
  price_band: string;
  delta_pct?: number | null;
  summary: string;
  attribution: string;
  decision?: string | null;
  outcome_7d?: string | null;
  ts?: string;
  embed_provider?: string;
  score?: number;
}

export interface EventDetail extends EventItem {
  suggestion: Suggestion | null;
  similar_cases: CaseItem[];
}

export interface SuggestionDetail extends Suggestion {
  event: EventItem | null;
  evidence_docs?: DocChunk[];
}

export interface DocChunk {
  id: string;
  doc_id: string;
  chunk_no: number;
  content: string;
  doc_title?: string;
}

export interface Doc {
  id: string;
  title: string;
  source: string | null;
  category: string | null;
  version: string | null;
  created_at: string;
  chunk_count: number;
  chunks?: { id: string; chunk_no: number; content: string }[];
}

export interface Skill {
  id: string;
  name: string;
  description: string | null;
  event_types: string[];
  min_severity: string;
  playbook: string;
  allowed_tools: string[];
  version: number;
  enabled: number;
  created_at: string;
  updated_at: string;
}

export interface EvalCase {
  id: string;
  name: string;
  expected_action: string;
  expected_event_type: string | null;
  notes: string | null;
  created_at: string;
}

export interface EvalResultRow {
  case: string;
  passed: boolean;
  event_type?: string;
  expected_event_type?: string | null;
  expected_action: string;
  actual_action?: string | null;
  evidence_count?: number;
  guardrail?: string | null;
  latency_ms?: number | null;
  error?: string | null;
}

export interface EvalRun {
  run_key: string;
  total: number;
  passed: number;
  accuracy: number;
  results: EvalResultRow[];
}

export interface TimelineRow {
  id: string;
  suggestion_id: string;
  actor: string;
  action: string;
  from_status: string | null;
  to_status: string | null;
  note: string | null;
  at: string;
}

export interface Target {
  id: string;
  platform: string;
  external_id: string | null;
  title: string;
  my_sku: string | null;
  my_price: number | null;
  active: number;
  mapping_status: string;
  holdout: number;
}

export interface PricePoint {
  ts: string;
  price_low: number;
  price_high: number;
  confidence: number;
  missing_fields: string[];
}

export interface Review {
  id: string;
  target_id: string;
  ts: string;
  rating: number | null;
  content: string;
}

export interface InsightTopic {
  name: string;
  count: number;
  share: number;
  negative_share: number;
}

export interface Insight {
  id?: string;
  target_id?: string;
  window_days: number;
  generated_at: string;
  review_count: number;
  summary: string;
  topics: InsightTopic[];
  opportunities: string[];
  generated_by: string;
  event_id?: string;
}

export interface Mapping {
  id: string;
  my_sku: string;
  target_id: string;
  score: number;
  method: string | null;
  status: string;
  created_at: string;
  decided_at: string | null;
  decided_by: string | null;
  target_title?: string | null;
  my_title?: string | null;
  my_price?: number | null;
}

export interface CollectionHealth {
  collector: string;
  snapshots: number;
  last_ts: string;
  lag_hours: number | null;
  stale: boolean;
}

export interface JobRun {
  id: number;
  kind: string;
  started_at: string;
  finished_at?: string | null;
  status: string;
  detail?: string | null;
}

export interface OpsState {
  scheduler: {
    enabled: boolean;
    started_at?: string;
    recent: JobRun[];
    last?: Record<string, string>;
  };
  inbox: {
    pending: number;
    failed: number;
    failed_files: { name: string; size: number; mtime: string }[];
    recent: Record<string, unknown>[];
  };
  collection: CollectionHealth[];
  freshness: Freshness;
  auth_enabled: boolean;
  webhook: boolean;
  connector: { configured: boolean };
  metrics: {
    calls: number;
    ok: number;
    fallback: number;
    fallback_rate: number;
    avg_latency_ms: number | null;
    p95_latency_ms: number | null;
    prompt_tokens?: number;
    completion_tokens?: number;
    tokens?: number;
    cost?: number;
    daily_budget_tokens?: number;
    budget_used_ratio?: number | null;
    by_kind: { kind: string; n: number; fallback: number }[];
  };
  backups: string[];
}

export interface AskTemplate {
  id: string;
  title: string;
  description: string;
  params: string[];
  examples: string[];
}

export interface AskResult {
  ok: boolean;
  answer: string;
  template?: string;
  template_title?: string;
  params?: Record<string, unknown>;
  rows?: Record<string, unknown>[];
  suggestions?: string[];
  matched_by?: string;
}

export interface UserRow {
  username: string;
  role: Role;
  created_at: string;
}
