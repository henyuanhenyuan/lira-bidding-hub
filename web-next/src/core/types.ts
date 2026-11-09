export interface Me {
  auth: boolean;
  username: string;
  display_name?: string | null;
  role: string;
  role_text?: string;
  actor?: string;
}

export interface Account {
  username: string;
  role: string;
  role_text?: string;
  display_name?: string | null;
  created_at?: string;
}

export interface CompareRow {
  id: string;
  platform: string;
  external_id?: string | null;
  title: string;
  my_sku: string | null;
  my_price: number | null;
  active: number | boolean;
  point: number | null;
  price_low: number | null;
  price_high: number | null;
  delta: number | null;
  severity: string | null;
  last_ts: string | null;
  mapping_status?: string | null;
  holdout?: number;
}

export interface Dashboard {
  compare: CompareRow[];
  trend: { date: string; count: number }[];
  severity: Record<string, number>;
  status: Record<string, number>;
  generated_at: string;
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
  margin_floor?: number | null;
  created_at: string;
  agent_run_id?: string | null;
  target_title?: string | null;
  event_type?: string | null;
  case_ids?: string[];
  executed_price?: number | null;
  submitted_by?: string | null;
  approved_by?: string | null;
}

export interface SuggestionDetail extends Suggestion {
  event?: (EventRow & { my_price?: number | null }) | null;
  evidence_docs: {
    id: string;
    doc_id: string;
    doc_title?: string | null;
    chunk_no: number;
    content: string;
  }[];
}

export interface TimelineRow {
  id: string;
  action: string;
  actor: string;
  from_status?: string | null;
  to_status?: string | null;
  note?: string | null;
  at: string;
}

export interface ExecutionRow {
  id: string;
  status?: string;
  to_price?: number | null;
  executed_price?: number | null;
  created_at?: string;
}

export interface RiskView {
  level: string;
  reason: string;
  roles: string[];
}

export interface AgentRun {
  id: string;
  event_id: string;
  suggestion_id?: string | null;
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
  event_type?: string | null;
  severity?: string | null;
  target_title?: string | null;
  plan?: string[];
  error?: string | null;
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
  latency_ms: number;
  created_at: string;
}

export interface AgentRunDetail extends AgentRun {
  steps: AgentStep[];
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

export interface DocHit {
  id: string;
  doc_id: string;
  doc_title?: string;
  chunk_no: number;
  content: string;
  score: number;
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
  ts: string;
  embed_provider?: string;
}

export interface Skill {
  id: string;
  name: string;
  description?: string | null;
  event_types: string[];
  min_severity?: string | null;
  playbook: string;
  allowed_tools: string[];
  stages: string[];
  output_schema?: Record<string, unknown> | null;
  version: number;
  enabled: number | boolean;
  created_at: string;
  updated_at: string;
}

export interface ToolSpec {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  risk: string;
}

export interface Metrics {
  window_hours: number;
  calls: number;
  ok: number;
  fallback: number;
  fallback_rate: number;
  avg_latency_ms: number | null;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  p99_latency_ms: number | null;
  prompt_tokens: number;
  completion_tokens: number;
  tokens: number;
  cost: number;
  daily_budget_tokens: number;
  budget_used_ratio: number | null;
  by_kind: { kind: string; n: number; fallback: number }[];
  by_model: {
    model: string;
    calls: number;
    fallback: number;
    tokens: number;
    cost: number;
  }[];
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

export interface EvalRun {
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

export interface GateStatus {
  ok: boolean;
  enforced: boolean;
  thresholds: { min_accuracy: number; max_fallback_rate: number };
  reasons: string[];
  warnings: string[];
  latest_eval: EvalRun | null;
  usage: {
    calls: number;
    tokens: number;
    cost: number;
    fallback_rate: number;
    budget_used_ratio: number | null;
  };
}

export interface HoldoutReport {
  window_days: number;
  treatment: { results: Record<string, number>; improvement_rate: number | null };
  control: { results: Record<string, number>; improvement_rate: number | null };
  holdout_targets: { id: string; title: string }[];
  note: string;
}

export interface Health {
  ok: boolean;
  counts: Record<string, number>;
  last_ingest?: { received_at?: string; rows_ok?: number } | null;
  collectors: { collector: string; c: number; last_ts: string }[];
  freshness: { stale?: boolean; lag_hours?: number; sla_hours?: number };
  vector_index: { indexed: number; cases: number; stale: boolean };
  llm_available: boolean;
}

export interface OpsState {
  scheduler: { enabled: boolean; mode: string };
  collection: { collector: string; c: number; last_ts: string }[];
  freshness: { stale?: boolean; lag_hours?: number; sla_hours?: number };
  auth_enabled: boolean;
  metrics: Metrics;
  backups: string[];
}

export interface ProviderView {
  id: string;
  name: string;
  base_url: string;
  model: string;
  enabled: boolean;
  has_key: boolean;
}

export interface ModelsView {
  backend: string;
  route: string;
  local: { model: string; url: string };
  api: { base_url: string; model: string; has_key: boolean };
  active_provider?: string;
  providers: ProviderView[];
  judge_model: string;
  sources: {
    taobao: { app_key: string; has_secret: boolean };
    octoparse: { base_url: string; has_token: boolean };
  };
}

export interface SourcesView {
  taobao: { app_key: string; has_secret: boolean };
  octoparse: { base_url: string; has_token: boolean };
  ingest: { url: string; has_token: boolean };
  file: { formats: string[]; endpoint: string };
}

export interface PriceRow {
  ts: string;
  price_low: number;
  price_high: number;
  confidence: number;
  missing_fields: string[];
}

export interface IntegrationEndpoint {
  name: string;
  method: string;
  path: string;
  auth: string;
  description: string;
}

export interface IntegrationOverview {
  endpoints: IntegrationEndpoint[];
  tokens: { active: number; total: number };
  counts: { targets: number; snapshots: number; events: number };
  ingest: {
    last: Record<string, unknown> | null;
    sources: {
      source: string;
      batches: number;
      rows_ok: number;
      rows_dup: number;
      last_at: string;
    }[];
  };
  model: { core: string; core_ready: boolean; test: string; route: string };
  sample: { snapshots: Record<string, unknown>[] };
}

export interface ApiToken {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  created_by?: string | null;
  created_at: string;
  last_used_at?: string | null;
  call_count: number;
  revoked_at?: string | null;
}

export interface IngestLogRow {
  id: string;
  source: string;
  file_name?: string | null;
  rows_in: number;
  rows_ok: number;
  rows_dup: number;
  rows_rejected: number;
  errors: { line?: number; target_id?: string; error: string }[];
  received_at: string;
}

export interface CollectSummary {
  hours: number;
  outcomes: Record<string, number>;
  errors: Record<string, number>;
}

export interface ChatReply {
  answer: string;
  citations: { id: string; title?: string; index?: number; score?: number }[];
  mode: string;
}

export interface FinetuneStack {
  framework: { trainer: string; peft: string };
  modules: Record<string, boolean>;
  installed: boolean;
  note: string;
  latest_dataset: FinetuneDataset | null;
  teacher: string;
  student: string;
  local_test: string;
}

export interface FinetuneDataset {
  path: string;
  name: string;
  samples: number;
  from_suggestions?: number;
  from_golden?: number;
  chars?: number;
  estimated_tokens?: number;
  bytes?: number;
}

export interface FinetuneJob {
  id: string;
  name: string;
  base_model: string;
  method: string;
  teacher?: string | null;
  samples: number;
  status: string;
  detail?: string | null;
  created_by?: string | null;
  created_at: string;
  updated_at: string;
  config?: {
    method: string;
    base_model: string;
    dataset: string;
    lora: Record<string, unknown>;
    train: Record<string, unknown>;
  } | null;
}

export interface FinetuneValidation {
  id: string;
  ok: boolean;
  checks: { name: string; ok: boolean; detail?: string }[];
  errors: string[];
  deps_ready: boolean;
  train_command: string;
  status: string;
}
