export type Severity = "L1" | "L2" | "L3";
export type Role = "admin" | "manager" | "member" | "viewer";

export interface Me {
  auth: boolean;
  username: string;
  display_name: string;
  role: Role;
  role_text: string;
}

export interface CompareRow {
  id: string;
  title: string;
  platform: string;
  my_price: number | null;
  my_sku: string | null;
  region: string;
  pricing_strategy: string;
  active: number;
  point: number | null;
  price_low: number | null;
  price_high: number | null;
  delta: number | null;
  severity: Severity | null;
  last_ts: string | null;
}

export interface TargetRow {
  id: string;
  platform: string;
  title: string;
  my_sku: string | null;
  my_price: number | null;
  active: number;
  mapping_status: string;
  holdout: number;
  region?: string;
  pricing_strategy?: string;
  url?: string | null;
  price_selector?: string | null;
}

export interface LedgerItem {
  id: string;
  ts: string;
  target_id: string;
  region: string | null;
  action: string;
  mode: string;
  status: string;
  from_price: number | null;
  to_price: number | null;
  delta_pct: number | null;
  margin_at_target: number | null;
  guardrail: string | null;
  suggestion_id: string | null;
  execution_id: string | null;
  run_id: string | null;
  strategy: string | null;
  reason: string | null;
  created_at: string;
}

export interface ExceptionItem {
  id: string;
  event_id: string;
  action: string;
  confidence: number;
  gate_level: string;
  narrative: string;
  status: string;
  created_at: string;
  target_price: number | null;
  margin_at_target: number | null;
  margin_floor: number | null;
  guardrail: string;
  guardrail_note: string | null;
  exception_reason: string | null;
  exception: number;
  mode: string;
  target_id: string;
  event_type: string;
  target_title: string;
  region: string;
  my_price: number | null;
}

export interface Dashboard {
  compare: CompareRow[];
  trend: { date: string; count: number }[];
  severity: Record<string, number>;
  status: Record<string, number>;
  region: string | null;
  regions: { region: string; targets: number; avg_price?: number | null }[];
  autopilot: { auto_executed: number; exceptions: number; ledger: LedgerItem[] };
  generated_at: string;
}

export interface AgentRun {
  id: string;
  event_id: string;
  suggestion_id: string | null;
  trigger: string;
  status: string;
  model: string | null;
  plan: { tool: string; args: Record<string, unknown>; reason: string }[];
  step_count: number;
  latency_ms: number | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
  skill_id?: string | null;
  event_type?: string;
  severity?: string;
  target_title?: string;
}

export interface Channel {
  channel: string;
  available: boolean;
  configured: boolean;
  detail: Record<string, unknown> & { base_url?: string; has_token?: boolean };
}

export interface Skill {
  id: string;
  name: string;
  description: string;
  event_types: string[];
  min_severity: string | null;
  playbook: string;
  allowed_tools: string[];
  stages: string[];
  version: number;
  enabled: number;
}

export interface ToolDef {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  risk: string;
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

export interface BadCase {
  id: string;
  run_key: string;
  case_name: string;
  segment?: string;
  difficulty?: string;
  reason?: string;
  detail?: string;
  created_at: string;
}

export interface ModelSettings {
  backend: string;
  route: string;
  local: { model: string; url: string };
  api: { base_url: string; model: string; has_key: boolean };
  active_provider: string;
  providers: {
    id: string;
    name: string;
    base_url: string;
    model: string;
    enabled: boolean;
    has_key: boolean;
  }[];
  judge_model: string;
  sources: Record<string, Record<string, unknown>>;
  autopilot: {
    enabled: boolean;
    strategy: string;
    undercut_pct: number;
    max_delta_pct: number;
    min_confidence: number;
  };
}

export interface TraceSummary {
  trace_id: string;
  spans: number;
  started_at: string;
}

export interface SpanNode {
  id: string;
  name: string;
  kind: string;
  status: string;
  duration_ms: number | null;
  attributes?: Record<string, unknown> | null;
  children: SpanNode[];
}

export interface OpsState {
  scheduler: {
    enabled: boolean;
    mode: string;
    started_at: string;
    last: Record<string, string>;
    recent: { kind: string; status: string; started_at: string; detail: string }[];
  };
  auth_enabled: boolean;
  metrics: Metrics;
  freshness: Freshness;
  backups: string[];
}

export interface Metrics {
  window_hours: number;
  calls: number;
  ok: number;
  fallback: number;
  fallback_rate: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  tokens: number;
  cost: number;
  daily_budget_tokens: number;
}

export interface Freshness {
  latest_ts: string | null;
  lag_hours: number;
  stale: boolean;
  sla_hours: number;
}

export interface AppUser {
  username: string;
  role: Role;
  display_name: string;
  created_at: string;
  role_text: string;
}

export interface StaticEvent {
  id: string;
  target_id: string;
  ts: string;
  type: string;
  severity: Severity;
}

export interface Suggestion {
  id: string;
  event_id: string;
  action: string;
  confidence: number;
  gate_level: string;
  narrative: string;
  status: string;
  created_at: string;
  target_id?: string;
  target_title?: string;
  target_price?: number | null;
  guardrail?: string;
  agent_run_id?: string | null;
}
