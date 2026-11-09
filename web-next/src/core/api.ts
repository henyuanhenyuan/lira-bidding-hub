const BASE = "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init.body && !(init.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(BASE + path, {
    credentials: "same-origin",
    ...init,
    headers: { ...headers, ...(init.headers as Record<string, string> | undefined) },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body?.detail || detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(response.status, String(detail));
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<T>(path, { method: "POST", body: form });
  },
};

export const endpoints = {
  me: () => api.get<import("./types").Me>("/api/me"),
  login: (username: string, password: string) =>
    api.post<{ username: string; role: string; display_name: string }>("/api/login", {
      username,
      password,
    }),
  logout: () => api.post<unknown>("/api/logout"),
  dashboard: (days: number, region?: string) =>
    api.get<import("./types").Dashboard>(
      `/api/dashboard?days=${days}${region ? `&region=${encodeURIComponent(region)}` : ""}`,
    ),
  regions: () => api.get<{ items: { region: string; targets: number; avg_price: number }[] }>("/api/regions"),
  runs: (limit = 12) => api.get<import("./types").AgentRun[]>(`/api/agent/runs?limit=${limit}`),
  run: (id: string) => api.get<import("./types").AgentRun>(`/api/agent/runs/${id}`),
  insights: () => api.get<{ mode: string; insights: string[] }>("/api/agent/insights"),
  autopilotStatus: () =>
    api.get<{
      config: { enabled: boolean; strategy: string; undercut_pct: number; max_delta_pct: number; min_confidence: number };
      counts: { auto_executed: number; auto_held: number; exceptions: number; manual_pending: number };
      recent: unknown[];
    }>("/api/autopilot/status"),
  autopilotConfig: (body: Record<string, unknown>) =>
    api.post<unknown>("/api/autopilot/config", body),
  autopilotTick: () => api.post<{ ran?: number }>("/api/autopilot/tick"),
  autopilotRun: (targetId: string) =>
    api.post<unknown>(`/api/autopilot/run/${targetId}`),
  exceptions: () => api.get<{ items: import("./types").ExceptionItem[] }>("/api/autopilot/exceptions"),
  resolveException: (id: string, body: { approve: boolean; note?: string; executed_price?: number }) =>
    api.post<unknown>(`/api/autopilot/exceptions/${id}/resolve`, body),
  ledger: (limit = 30) => api.get<{ items: import("./types").LedgerItem[] }>(`/api/autopilot/ledger?limit=${limit}`),
  channels: () => api.get<{ items: import("./types").Channel[] }>("/api/crawl/channels"),
  crawlConfig: (body: Record<string, unknown>) => api.post<unknown>("/api/crawl/config", body),
  crawlRun: (body: Record<string, unknown>) => api.post<unknown>("/api/crawl/run", body),
  crawlLogs: (limit = 30) => api.get<{ items: Record<string, unknown>[] }>(`/api/crawl/logs?limit=${limit}`),
  importFile: (file: File) =>
    api.upload<{ ok: boolean; rows_ok: number; rows_dup: number; rows_rejected: number; errors: unknown[] }>(
      "/api/import/file",
      file,
    ),
  targets: () => api.get<import("./types").TargetRow[]>("/api/targets"),
  patchTarget: (id: string, body: Record<string, unknown>) => api.patch<unknown>(`/api/targets/${id}`, body),
  prices: (id: string, limit = 60) =>
    api.get<{ ts: string; price_low: number; price_high: number; confidence: number }[]>(
      `/api/targets/${id}/prices?limit=${limit}`,
    ),
  suggestions: (limit = 30) => api.get<import("./types").Suggestion[]>(`/api/suggestions?limit=${limit}`),
  suggestion: (id: string) => api.get<import("./types").Suggestion>(`/api/suggestions/${id}`),
  approve: (id: string, note?: string) => api.post<unknown>(`/api/suggestions/${id}/approve`, { note }),
  reject: (id: string, note?: string) => api.post<unknown>(`/api/suggestions/${id}/reject`, { note }),
  execute: (id: string, price?: number) =>
    api.post<unknown>(`/api/suggestions/${id}/execute`, price ? { executed_price: price } : {}),
  analyzeEvent: (id: string) => api.post<unknown>(`/api/events/${id}/analyze`),
  events: (limit = 40) => api.get<import("./types").StaticEvent[]>(`/api/events?limit=${limit}`),
  skills: () => api.get<import("./types").Skill[]>("/api/skills"),
  tools: () => api.get<import("./types").ToolDef[]>("/api/tools"),
  traces: (limit = 20) => api.get<import("./types").TraceSummary[]>(`/api/observability/traces?limit=${limit}`),
  trace: (id: string) =>
    api.get<{ trace_id: string; count: number; roots: import("./types").SpanNode[] }>(
      `/api/observability/traces/${id}`,
    ),
  evalRuns: (limit = 20) => api.get<import("./types").EvalRun[]>(`/api/eval/runs?limit=${limit}`),
  evalRun: (opts: { limit?: number; tier?: string; retrieval?: boolean }) => {
    const q = new URLSearchParams();
    if (opts.limit) q.set("limit", String(opts.limit));
    if (opts.tier) q.set("tier", opts.tier);
    q.set("retrieval", String(opts.retrieval !== false));
    return api.post<Record<string, unknown>>(`/api/eval/run?${q.toString()}`);
  },
  badcases: (runKey?: string) =>
    api.get<import("./types").BadCase[]>(`/api/eval/badcases${runKey ? `?run_key=${runKey}` : ""}`),
  gates: () =>
    api.get<{
      ok: boolean;
      enforced: boolean;
      thresholds: Record<string, number>;
      reasons: string[];
      warnings: string[];
      latest_eval: import("./types").EvalRun | null;
      usage: Record<string, number>;
    }>("/api/gates"),
  metrics: () => api.get<import("./types").Metrics>("/api/metrics"),
  models: () => api.get<import("./types").ModelSettings>("/api/settings/models"),
  setModels: (body: Record<string, unknown>) =>
    api.post<import("./types").ModelSettings>("/api/settings/models", body),
  probeModels: () =>
    api.post<{ ok: boolean; route: string; latency_ms: number; reply: string }>(
      "/api/settings/models/probe",
      {},
    ),
  setProviders: (body: Record<string, unknown>) =>
    api.post<import("./types").ModelSettings>("/api/settings/providers", body),
  probeProvider: (id: string) =>
    api.post<{ ok: boolean; latency_ms: number; reply: string }>(`/api/settings/providers/${id}/probe`),
  sources: () => api.get<Record<string, Record<string, unknown>>>("/api/settings/sources"),
  setSources: (body: Record<string, unknown>) => api.post<Record<string, unknown>>("/api/settings/sources", body),
  finetuneStack: () =>
    api.get<{
      framework: { trainer: string; peft: string };
      modules: Record<string, boolean>;
      installed: boolean;
      note: string;
      latest_dataset: { path: string; name: string; samples: number; bytes: number } | null;
      teacher: string;
      student: string;
      local_test: string;
    }>("/api/finetune/stack"),
  finetuneDataset: (limit = 400) => api.post<Record<string, unknown>>("/api/finetune/dataset", { limit }),
  finetuneJobs: () => api.get<Record<string, unknown>[]>("/api/finetune/jobs"),
  finetuneCreate: (body: Record<string, unknown>) => api.post<Record<string, unknown>>("/api/finetune/jobs", body),
  ops: () => api.get<import("./types").OpsState>("/api/ops"),
  opsRun: (kind: string) => api.post<{ kind: string; result: string }>(`/api/ops/run?kind=${kind}`),
  users: () => api.get<import("./types").AppUser[]>("/api/users"),
  health: () =>
    api.get<{
      ok: boolean;
      counts: Record<string, number>;
      llm_available: boolean;
      freshness: import("./types").Freshness;
      collectors: { collector: string; c: number; last_ts: string }[];
    }>("/api/health"),
  integration: () =>
    api.get<{
      endpoints: { name: string; method: string; path: string; auth: string; description: string }[];
      tokens: { active: number; total: number };
      counts: Record<string, number>;
      ingest: { last: Record<string, unknown> | null; sources: Record<string, unknown>[] };
      model: { core: string; core_ready: boolean; test: string; route: string };
      sample: Record<string, unknown>;
    }>("/api/integration/overview"),
  approvalsInbox: () => api.get<import("./types").Suggestion[]>("/api/approvals/inbox"),
  collectSummary: () => api.get<{ hours: number; outcomes: Record<string, number>; errors: Record<string, number> }>("/api/collect/summary"),
  collectReviews: () => api.get<{ items: Record<string, unknown>[] }>("/api/collect/reviews"),
  freshness: () => api.get<import("./types").Freshness>("/api/freshness"),
};
