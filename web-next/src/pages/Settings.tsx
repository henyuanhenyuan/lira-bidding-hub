import { useEffect, useState, type FormEvent } from "react";

import { api, ApiError } from "../core/api";
import { canManage, useAuth } from "../core/auth";
import { num, pct, ts } from "../core/format";
import { useAsync } from "../core/hooks";
import type {
  Account,
  ApiToken,
  CollectSummary,
  GateStatus,
  Health,
  IngestLogRow,
  IntegrationOverview,
  Metrics,
  ModelsView,
  OpsState,
  SourcesView,
} from "../core/types";
import { CopyButton, Empty, ErrorBox, Loading, Panel, Seg, StatusBadge } from "../ui/kit";

interface CollectTaskRow {
  id: string;
  target_id: string;
  channel: string;
  status: string;
  attempts: number;
  max_attempts: number;
  interval_s: number;
  next_run_at?: string | null;
}

interface ReviewRow {
  id: string;
  task_id: string;
  channel: string;
  target_id?: string | null;
  reason: string;
  created_at: string;
}

interface CollectLogRow {
  id: number;
  ts: string;
  channel: string;
  outcome: string;
  latency_ms?: number | null;
  detail?: string | null;
}

interface TargetRow {
  id: string;
  title: string;
}

interface ProbeResult {
  ok: boolean;
  model: string;
  latency_ms: number;
  reply?: string;
  error?: string;
}

interface Bundle {
  models: ModelsView | null;
  sources: SourcesView | null;
  users: Account[];
  ops: OpsState | null;
  integration: IntegrationOverview | null;
  tokens: ApiToken[];
  logs: IngestLogRow[];
  health: Health | null;
  gates: GateStatus | null;
  collect: CollectSummary | null;
  metrics: Metrics | null;
  tasks: CollectTaskRow[];
  reviews: ReviewRow[];
  collectLogs: CollectLogRow[];
  targets: TargetRow[];
}

export default function Settings() {
  const { me } = useAuth();
  const editable = canManage(me);
  const { data, error, loading, reload } = useAsync<Bundle>(async () => {
    const [models, sources, users, ops, integration, tokens, logs, health, gates, collect, metrics, tasks, reviews, collectLogs, targets] =
      await Promise.all([
        api.get<ModelsView>("/api/settings/models").catch(() => null),
        api.get<SourcesView>("/api/settings/sources").catch(() => null),
        api.get<Account[]>("/api/users").catch(() => []),
        api.get<OpsState>("/api/ops").catch(() => null),
        api.get<IntegrationOverview>("/api/integration/overview").catch(() => null),
        api.get<ApiToken[]>("/api/integration/tokens").catch(() => []),
        api.get<IngestLogRow[]>("/api/integration/logs?limit=12").catch(() => []),
        api.get<Health>("/api/health").catch(() => null),
        api.get<GateStatus>("/api/gates").catch(() => null),
        api.get<CollectSummary>("/api/collect/summary?hours=24").catch(() => null),
        api.get<Metrics>("/api/metrics?hours=24").catch(() => null),
        api.get<{ tasks: CollectTaskRow[] }>("/api/collect/tasks?limit=30").catch(() => ({ tasks: [] })),
        api.get<{ reviews: ReviewRow[] }>("/api/collect/reviews?limit=10").catch(() => ({ reviews: [] })),
        api.get<{ logs: CollectLogRow[] }>("/api/collect/logs?limit=10").catch(() => ({ logs: [] })),
        api.get<TargetRow[]>("/api/targets").catch(() => []),
      ]);
    return {
      models, sources, users, ops, integration, tokens, logs, health, gates, collect, metrics,
      tasks: tasks.tasks, reviews: reviews.reviews, collectLogs: collectLogs.logs, targets,
    };
  }, []);

  const [section, setSection] = useState<"connect" | "model" | "accounts" | "runtime">("connect");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");
  const [apiProviderId, setApiProviderId] = useState("qwen");
  const [route, setRoute] = useState<"api" | "local">("local");
  const [localModel, setLocalModel] = useState("qwen3:4b");
  const [localUrl, setLocalUrl] = useState("http://127.0.0.1:11434");
  const [apiBase, setApiBase] = useState("https://dashscope.aliyuncs.com/compatible-mode/v1");
  const [apiModel, setApiModel] = useState("qwen-plus");
  const [apiKey, setApiKey] = useState("");
  const [probe, setProbe] = useState<ProbeResult | null>(null);
  const [localProbe, setLocalProbe] = useState<ProbeResult | null>(null);
  const [taobaoKey, setTaobaoKey] = useState("");
  const [taobaoSecret, setTaobaoSecret] = useState("");
  const [octoBase, setOctoBase] = useState("https://dataapi.octoparse.com");
  const [octoToken, setOctoToken] = useState("");
  const [fileResult, setFileResult] = useState("");
  const [tokenName, setTokenName] = useState("采集端");
  const [newToken, setNewToken] = useState("");
  const [pushTarget, setPushTarget] = useState("demo-sku-001");
  const [pushTitle, setPushTitle] = useState("演示竞品 · 控油洗发水");
  const [pushPrice, setPushPrice] = useState("259");
  const [pushResult, setPushResult] = useState("");
  const [taskTarget, setTaskTarget] = useState("");
  const [taskChannel, setTaskChannel] = useState("rpa");
  const [taskInterval, setTaskInterval] = useState("3600");
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("member");
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");

  useEffect(() => {
    if (!data?.models) return;
    const view = data.models;
    setRoute(view.route === "openai" ? "api" : "local");
    setLocalModel(view.local.model);
    setLocalUrl(view.local.url);
    setApiBase(view.api.base_url || "https://dashscope.aliyuncs.com/compatible-mode/v1");
    setApiModel(view.api.model);
    setApiProviderId(view.active_provider ?? view.providers?.[0]?.id ?? "qwen");
  }, [data?.models]);

  useEffect(() => {
    if (!data?.sources) return;
    setTaobaoKey(data.sources.taobao.app_key);
    setOctoBase(data.sources.octoparse.base_url);
  }, [data?.sources]);

  function flash(text: string) {
    setMessage(text);
    window.setTimeout(() => setMessage(""), 3000);
  }

  async function saveApi() {
    setBusy("api");
    try {
      await api.post("/api/settings/providers", {
        providers: [{ id: apiProviderId, name: "通义千问", base_url: apiBase, model: apiModel, api_key: apiKey || null, enabled: true }],
        active: apiProviderId,
        route: "openai",
      });
      setApiKey("");
      flash("API 集成已保存并启用");
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "保存失败");
    } finally {
      setBusy("");
    }
  }

  async function testApi() {
    setBusy("test-api");
    setProbe(null);
    try {
      const result = await api.post<ProbeResult>(`/api/settings/providers/${apiProviderId}/probe`);
      setProbe(result);
      flash(result.ok ? `API 连通 · ${result.latency_ms}ms` : `API 不可用：${result.error ?? ""}`);
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "测试失败");
    } finally {
      setBusy("");
    }
  }

  async function saveLocal() {
    setBusy("local");
    try {
      await api.post("/api/settings/models", {
        backend: "gateway", route: "ollama", local_model: localModel, local_url: localUrl,
        api_base_url: apiBase, api_model: apiModel, api_key: apiKey || null,
      });
      setApiKey("");
      flash("本地集成已保存并启用");
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "保存失败");
    } finally {
      setBusy("");
    }
  }

  async function testLocal() {
    setBusy("test-local");
    setLocalProbe(null);
    try {
      const result = await api.post<ProbeResult>("/api/settings/models/probe", { route: "ollama" });
      setLocalProbe(result);
      flash(result.ok ? `本地模型连通 · ${result.latency_ms}ms` : "本地模型不可用");
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "测试失败");
    } finally {
      setBusy("");
    }
  }

  async function saveSources() {
    setBusy("sources");
    try {
      await api.post("/api/settings/sources", {
        taobao_app_key: taobaoKey, taobao_app_secret: taobaoSecret || null,
        octoparse_base_url: octoBase, octoparse_token: octoToken || null,
      });
      setTaobaoSecret(""); setOctoToken("");
      flash("三个接入通道已保存");
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "保存失败");
    } finally {
      setBusy("");
    }
  }

  async function uploadFile(file: File | null) {
    if (!file) return;
    setBusy("file");
    try {
      const result = await api.upload<{ rows_ok?: number; rows_dup?: number; errors?: unknown[] }>("/api/import/file", file);
      setFileResult(`导入 ${result.rows_ok ?? 0} 条，重复 ${result.rows_dup ?? 0} 条${result.errors?.length ? `，错误 ${result.errors.length}` : ""}`);
      await reload();
    } catch (err) {
      setFileResult(err instanceof ApiError ? err.message : "上传失败");
    } finally {
      setBusy("");
    }
  }

  async function createToken(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!tokenName.trim()) return;
    setBusy("token");
    try {
      const result = await api.post<ApiToken & { token: string }>("/api/integration/tokens", { name: tokenName.trim(), scopes: ["ingest"] });
      setNewToken(result.token);
      flash("令牌已创建，只显示一次");
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "创建失败");
    } finally {
      setBusy("");
    }
  }

  async function revokeToken(token: ApiToken) {
    try {
      await api.del(`/api/integration/tokens/${token.id}`);
      flash("令牌已吊销");
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "吊销失败");
    }
  }

  async function testPush(event: FormEvent) {
    event.preventDefault();
    setBusy("push");
    try {
      const result = await api.post<{ rows_ok: number; events_created: number }>("/api/integration/test-push", {
        target_id: pushTarget.trim() || "demo-sku-001",
        title: pushTitle.trim() || "演示竞品",
        price: Number(pushPrice) || 0,
        source_tier: 2,
      });
      setPushResult(`写入 ${result.rows_ok} 条，新增事件 ${result.events_created} 条`);
      await reload();
    } catch (err) {
      setPushResult(err instanceof ApiError ? err.message : "推送失败");
    } finally {
      setBusy("");
    }
  }

  async function createAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!username.trim() || !password) return;
    setBusy("account");
    try {
      await api.post("/api/users", { username: username.trim(), password, role, display_name: displayName.trim() || username.trim() });
      setUsername(""); setDisplayName(""); setPassword("");
      flash("账号已创建");
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "创建失败");
    } finally {
      setBusy("");
    }
  }

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!me?.username || !newPassword) return;
    setBusy("password");
    try {
      await api.post(`/api/users/${encodeURIComponent(me.username)}/password`, { old_password: oldPassword, new_password: newPassword });
      setOldPassword(""); setNewPassword("");
      flash("密码已更新");
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "更新失败");
    } finally {
      setBusy("");
    }
  }

  async function setRoleFor(account: Account, next: string) {
    try {
      await api.patch(`/api/users/${encodeURIComponent(account.username)}`, { role: next });
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "修改失败");
    }
  }

  async function runOps(kind: string) {
    setBusy(kind);
    try {
      const result = await api.post<{ result: string }>(`/api/ops/run?kind=${encodeURIComponent(kind)}`);
      flash(`${kind}：${result.result}`);
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "执行失败");
    } finally {
      setBusy("");
    }
  }

  async function createTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!taskTarget) return;
    setBusy("task");
    try {
      await api.post("/api/collect/tasks", { target_id: taskTarget, channel: taskChannel, interval_s: Number(taskInterval) || 0 });
      flash("采集任务已创建");
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "创建失败");
    } finally {
      setBusy("");
    }
  }

  async function cancelTask(id: string) {
    try {
      await api.del(`/api/collect/tasks/${id}`);
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "取消失败");
    }
  }

  async function resolveReview(id: string, decision: "released" | "discarded") {
    try {
      await api.post(`/api/collect/reviews/${id}/resolve?decision=${decision}`);
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "处理失败");
    }
  }

  if (loading && !data) return <Loading rows={5} />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  const models = data.models;
  const sources = data.sources;
  const integration = data.integration;
  const health = data.health;
  const gates = data.gates;
  const origin = window.location.origin;

  return (
    <div className="stack gap-16 fade-in">
      {message && <div className="badge mint" style={{ whiteSpace: "normal", padding: "9px 12px", alignSelf: "flex-start" }}>{message}</div>}

      <div className="grid g6">
        {[
          ["竞品目标", integration?.counts.targets ?? 0],
          ["事件", integration?.counts.events ?? 0],
          ["建议", health?.counts.suggestions ?? 0],
          ["活跃令牌", integration?.tokens.active ?? 0],
          ["账号", data.users.length],
          ["评测准确率", gates?.latest_eval ? pct(gates.latest_eval.accuracy) : "—"],
        ].map(([label, value]) => (
          <div className="kpi" key={label as string}>
            <span className="kpi-label">{label as string}</span>
            <span className="kpi-value" style={{ fontSize: 22 }}>{value}</span>
          </div>
        ))}
      </div>

      <div className="row between wrap gap-10">
        <Seg
          value={section}
          onChange={setSection}
          items={[
            { key: "connect", label: "接入与通道", sub: "令牌 · 推送" },
            { key: "model", label: "模型路由", sub: "API · 本地" },
            { key: "accounts", label: "账号与权限", sub: "成员 · 密码" },
            { key: "runtime", label: "采集与运行", sub: "队列 · 健康" },
          ]}
        />
        <span className="muted" style={{ fontSize: 11 }}>{editable ? "可编辑" : "只读"}</span>
      </div>

      {section === "connect" && (
        <>
      <Panel
        title="接入模块"
        sub="三个通道 · 令牌 · 测试推送"
        right={<span className="badge cyan">{origin}</span>}
      >
        <div className="stack gap-12">
          <div className="grid g3" style={{ gap: 12 }}>
            <div className="driver" style={{ gridTemplateColumns: "1fr" }}>
              <div className="row between">
                <span style={{ fontSize: 12.5, fontWeight: 600 }}>淘宝开放平台</span>
                <span className={`badge ${sources?.taobao.has_secret ? "mint" : ""}`} style={{ fontSize: 9 }}>{sources?.taobao.has_secret ? "已配置" : "待配置"}</span>
              </div>
              <input className="input mt-8" value={taobaoKey} onChange={(event) => setTaobaoKey(event.target.value)} placeholder="App Key" />
              <input className="input mt-8" type="password" value={taobaoSecret} onChange={(event) => setTaobaoSecret(event.target.value)} placeholder="App Secret" />
            </div>
            <div className="driver" style={{ gridTemplateColumns: "1fr" }}>
              <div className="row between">
                <span style={{ fontSize: 12.5, fontWeight: 600 }}>影刃八爪鱼</span>
                <span className={`badge ${sources?.octoparse.has_token ? "mint" : ""}`} style={{ fontSize: 9 }}>{sources?.octoparse.has_token ? "已配置" : "待配置"}</span>
              </div>
              <input className="input mt-8" value={octoBase} onChange={(event) => setOctoBase(event.target.value)} placeholder="API 地址" />
              <input className="input mt-8" type="password" value={octoToken} onChange={(event) => setOctoToken(event.target.value)} placeholder="Access Token" />
            </div>
            <div className="driver" style={{ gridTemplateColumns: "1fr" }}>
              <div className="row between">
                <span style={{ fontSize: 12.5, fontWeight: 600 }}>文件导入</span>
                <span className="badge cyan" style={{ fontSize: 9 }}>CSV / JSON</span>
              </div>
              <input className="input mt-8" type="file" accept=".csv,.json" disabled={busy === "file"} onChange={(event) => void uploadFile(event.target.files?.[0] ?? null)} />
              {fileResult && <span className="muted" style={{ fontSize: 10 }}>{fileResult}</span>}
            </div>
          </div>
          <div className="row gap-8">
            <button className="btn sm primary" disabled={!editable || busy === "sources"} onClick={() => void saveSources()}>
              {busy === "sources" ? "保存中…" : "保存三个通道"}
            </button>
            <span className="muted" style={{ fontSize: 10.5 }}>推送接口：POST /v1/ingest/snapshots · 干跑：POST /v1/ingest/validate</span>
          </div>

          <div className="divider" />
          <div className="row between">
            <span className="eyebrow">接入令牌</span>
            <span className="muted" style={{ fontSize: 10.5 }}>只存哈希，只显示一次</span>
          </div>
          <form className="row gap-8" onSubmit={(event) => void createToken(event)}>
            <input className="input" style={{ maxWidth: 260 }} value={tokenName} onChange={(event) => setTokenName(event.target.value)} placeholder="令牌名称" />
            <button className="btn sm primary" disabled={!editable || busy === "token"}>生成令牌</button>
          </form>
          {newToken && (
            <div className="driver token-new" style={{ gridTemplateColumns: "1fr auto" }}>
              <code className="mono" style={{ fontSize: 10, wordBreak: "break-all" }}>{newToken}</code>
              <CopyButton text={newToken} />
            </div>
          )}
          <div className="stack gap-4">
            {data.tokens.map((token) => (
              <div className="driver" key={token.id} style={{ gridTemplateColumns: "1fr auto", opacity: token.revoked_at ? 0.5 : 1 }}>
                <span className="stack" style={{ lineHeight: 1.3 }}>
                  <span style={{ fontSize: 11.5 }}>{token.name} <span className="muted mono" style={{ fontSize: 9 }}>{token.prefix}…</span></span>
                  <span className="muted" style={{ fontSize: 9 }}>{token.call_count} 次 · {token.last_used_at ? ts(token.last_used_at) : "未使用"}</span>
                </span>
                {token.revoked_at ? <span className="badge rose" style={{ fontSize: 9 }}>已吊销</span> : (
                  <button className="btn sm ghost" disabled={!editable} onClick={() => void revokeToken(token)}>吊销</button>
                )}
              </div>
            ))}
          </div>

          <div className="divider" />
          <form className="row gap-8 wrap" style={{ alignItems: "flex-end" }} onSubmit={(event) => void testPush(event)}>
            <div className="field" style={{ width: 150 }}><label>target_id</label><input className="input" value={pushTarget} onChange={(event) => setPushTarget(event.target.value)} /></div>
            <div className="field" style={{ flex: 1, minWidth: 160 }}><label>标题</label><input className="input" value={pushTitle} onChange={(event) => setPushTitle(event.target.value)} /></div>
            <div className="field" style={{ width: 90 }}><label>标价</label><input className="input" value={pushPrice} onChange={(event) => setPushPrice(event.target.value)} /></div>
            <button className="btn sm primary" disabled={!editable || busy === "push"}>测试推送</button>
          </form>
          {pushResult && <span className="muted push-result" style={{ fontSize: 10.5 }}>{pushResult}</span>}
        </div>
      </Panel>
        </>
      )}

      {section === "model" && (
        <>
      <Panel
        title="模型路由"
        sub="一个 API 集成 + 一个本地集成；两者都建议 qwen-plus"
        right={<span className={`badge ${route === "api" ? "violet" : "amber"}`}>{route === "api" ? "API 集成" : "本地集成"}</span>}
      >
        <div className="stack gap-12">
          <div className="driver" style={{ gridTemplateColumns: "1fr auto" }}>
            <span className="stack" style={{ lineHeight: 1.4 }}>
              <span style={{ fontSize: 13, fontWeight: 600 }}>{apiModel || "qwen-plus"} <span className="badge cyan" style={{ marginLeft: 6, fontSize: 9 }}>建议生产</span></span>
              <span className="muted mono" style={{ fontSize: 10 }}>{apiBase}</span>
              <span className="muted" style={{ fontSize: 10.5 }}>API Key {models?.api.has_key ? "已配置" : "未配置 · 自动回退本机"}</span>
            </span>
            <div className="row gap-6">
              <button className="btn sm primary" disabled={!editable || busy === "api"} onClick={() => void saveApi()}>保存 API</button>
              <button className="btn sm ghost" disabled={busy === "test-api" || (!models?.api.has_key && !apiKey)} onClick={() => void testApi()}>测试</button>
            </div>
          </div>
          <div className="grid g3" style={{ gap: 8 }}>
            <input className="input" value={apiBase} onChange={(event) => setApiBase(event.target.value)} placeholder="Base URL" />
            <input className="input" value={apiModel} onChange={(event) => setApiModel(event.target.value)} placeholder="模型名" />
            <input className="input" type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={models?.api.has_key ? "API Key（留空沿用）" : "sk-..."} />
          </div>
          {probe && <span className={`badge ${probe.ok ? "mint" : "rose"}`} style={{ alignSelf: "flex-start", fontSize: 10 }}>{probe.ok ? `${probe.model} · ${probe.latency_ms}ms` : probe.error}</span>}

          <div className="divider" />

          <div className="driver" style={{ gridTemplateColumns: "1fr auto" }}>
            <span className="stack" style={{ lineHeight: 1.4 }}>
              <span style={{ fontSize: 13, fontWeight: 600 }}>{localModel} <span className="badge amber" style={{ marginLeft: 6, fontSize: 9 }}>仅测试</span></span>
              <span className="muted mono" style={{ fontSize: 10 }}>{localUrl}</span>
              <span className="muted" style={{ fontSize: 10.5 }}>本机 4B 只做回归；生产建议本地部署或代理 qwen-plus</span>
            </span>
            <div className="row gap-6">
              <button className="btn sm ghost" disabled={!editable || busy === "local"} onClick={() => void saveLocal()}>保存本地</button>
              <button className="btn sm ghost" disabled={busy === "test-local"} onClick={() => void testLocal()}>测试</button>
            </div>
          </div>
          <div className="grid g2" style={{ gap: 8 }}>
            <input className="input" value={localModel} onChange={(event) => setLocalModel(event.target.value)} placeholder="本地模型名" />
            <input className="input" value={localUrl} onChange={(event) => setLocalUrl(event.target.value)} placeholder="Ollama 地址" />
          </div>
          {localProbe && <span className={`badge ${localProbe.ok ? "mint" : "rose"}`} style={{ alignSelf: "flex-start", fontSize: 10 }}>{localProbe.ok ? `${localProbe.model} · ${localProbe.latency_ms}ms` : "不可用"}</span>}
          {route === "api" && <span className="muted" style={{ fontSize: 10 }}>当前路由：API（{apiModel}）</span>}
        </div>
      </Panel>
        </>
      )}

      {section === "accounts" && (
        <>
      <div className="split-2">
        <Panel
          title="账号"
          sub="5 个交付账号 + 管理员创建"
          right={<span className="badge cyan">{data.users.length} / 5</span>}
        >
          <div className="stack gap-6">
            {data.users.map((account) => (
              <div className="driver" key={account.username} style={{ gridTemplateColumns: "1fr auto" }}>
                <span className="stack" style={{ lineHeight: 1.3 }}>
                  <span className="row gap-6">
                    <span style={{ fontSize: 12.5, fontWeight: 600 }}>{account.display_name ?? account.username}</span>
                    <span className="badge" style={{ fontSize: 9 }}>{account.role_text ?? account.role}</span>
                  </span>
                  <span className="muted mono" style={{ fontSize: 10 }}>{account.username}</span>
                </span>
                {editable && me?.role === "admin" ? (
                  <select className="input" style={{ width: 110, padding: "6px 8px", fontSize: 11 }} value={account.role} onChange={(event) => void setRoleFor(account, event.target.value)}>
                    <option value="member">成员</option>
                    <option value="manager">主管</option>
                    <option value="admin">管理员</option>
                  </select>
                ) : <StatusBadge value="ok" />}
              </div>
            ))}
          </div>
          {me?.role === "admin" && (
            <form className="stack gap-8 mt-16" onSubmit={(event) => void createAccount(event)}>
              <div className="divider" />
              <span className="eyebrow">新建账号</span>
              <div className="row gap-8 wrap">
                <input className="input" style={{ width: 130 }} value={username} onChange={(event) => setUsername(event.target.value)} placeholder="账号" required />
                <input className="input" style={{ width: 130 }} value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="显示名" />
                <input className="input" style={{ width: 130 }} type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="初始密码" required />
                <select className="input" style={{ width: 100 }} value={role} onChange={(event) => setRole(event.target.value)}>
                  <option value="member">成员</option>
                  <option value="manager">主管</option>
                  <option value="admin">管理员</option>
                </select>
                <button className="btn sm primary" disabled={busy === "account"}>创建</button>
              </div>
            </form>
          )}
        </Panel>

        <Panel title="我的账号" sub="修改登录密码">
          <form className="stack gap-10" onSubmit={(event) => void changePassword(event)}>
            <div className="field"><label>原密码</label><input className="input" type="password" value={oldPassword} onChange={(event) => setOldPassword(event.target.value)} /></div>
            <div className="field"><label>新密码（至少 6 位）</label><input className="input" type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /></div>
            <button className="btn primary" disabled={busy === "password" || newPassword.length < 6}>{busy === "password" ? "更新中…" : "更新密码"}</button>
          </form>
        </Panel>
      </div>
        </>
      )}

      {section === "runtime" && (
        <>
      <Panel title="采集队列" sub="RPA / API / 人工 · 复核队列">
        <form className="row gap-8 wrap" style={{ alignItems: "flex-end" }} onSubmit={(event) => void createTask(event)}>
          <div className="field" style={{ width: 180 }}><label>目标</label>
            <select className="input" value={taskTarget} onChange={(event) => setTaskTarget(event.target.value)} required>
              <option value="">选择竞品</option>
              {data.targets.map((target) => <option key={target.id} value={target.id}>{target.title}</option>)}
            </select>
          </div>
          <div className="field" style={{ width: 100 }}><label>通道</label>
            <select className="input" value={taskChannel} onChange={(event) => setTaskChannel(event.target.value)}>
              <option value="rpa">RPA</option><option value="api">API</option><option value="manual">人工</option>
            </select>
          </div>
          <div className="field" style={{ width: 110 }}><label>间隔秒</label><input className="input" value={taskInterval} onChange={(event) => setTaskInterval(event.target.value)} /></div>
          <button className="btn sm primary" disabled={!editable || !taskTarget}>创建任务</button>
        </form>
        <div className="stack gap-4 mt-12">
          {data.tasks.slice(0, 6).map((task) => (
            <div className="driver" key={task.id} style={{ gridTemplateColumns: "1fr auto" }}>
              <span className="muted" style={{ fontSize: 10.5 }}>{task.target_id} · {task.channel} · {task.interval_s ? `${task.interval_s}s` : "一次"} · {task.attempts}/{task.max_attempts}</span>
              <button className="btn sm ghost" disabled={!editable} onClick={() => void cancelTask(task.id)}>取消</button>
            </div>
          ))}
          {data.tasks.length === 0 && <Empty text="还没有采集任务" />}
        </div>
        {data.reviews.length > 0 && (
          <>
            <div className="divider mt-12" />
            <div className="stack gap-4 mt-12">
              {data.reviews.map((review) => (
                <div className="driver" key={review.id} style={{ gridTemplateColumns: "1fr auto" }}>
                  <span className="muted" style={{ fontSize: 10.5 }}>{review.target_id ?? review.task_id} · {review.channel} · {review.reason}</span>
                  <span className="row gap-4">
                    <button className="btn sm ghost" onClick={() => void resolveReview(review.id, "released")}>放行</button>
                    <button className="btn sm ghost" onClick={() => void resolveReview(review.id, "discarded")}>丢弃</button>
                  </span>
                </div>
              ))}
            </div>
          </>
        )}
      </Panel>

      <div className="split-2">
        <Panel title="运行环境" sub="调度 · 新鲜度 · 备份">
          {!data.ops ? <Empty text="仅管理员可见" /> : (
            <div className="stack gap-8">
              {[
                ["调度", `${data.ops.scheduler.enabled ? "运行中" : "关闭"} · ${data.ops.scheduler.mode}`],
                ["数据滞后", data.ops.freshness.lag_hours != null ? `${Math.round(data.ops.freshness.lag_hours)}h` : "—"],
                ["鉴权", data.ops.auth_enabled ? "开启" : "关闭"],
                ["备份", String(data.ops.backups.length)],
                ["采集源", String(data.ops.collection.length)],
              ].map(([label, value]) => (
                <div className="row between" key={label}><span className="muted" style={{ fontSize: 12 }}>{label}</span><span className="mono" style={{ fontSize: 12 }}>{value}</span></div>
              ))}
              <div className="row gap-6 wrap mt-8">
                {["mapping_suggest", "outcome_review", "backup"].map((kind) => (
                  <button key={kind} className="btn sm ghost" disabled={busy === kind} onClick={() => void runOps(kind)}>
                    {kind === "mapping_suggest" ? "映射建议" : kind === "outcome_review" ? "结果回收" : "立即备份"}
                  </button>
                ))}
              </div>
            </div>
          )}
        </Panel>

        <Panel title="健康与门禁" sub="统一 PostgreSQL + pgvector">
          <div className="grid g2" style={{ gap: 8 }}>
            {[
              ["目标", health?.counts.targets ?? 0],
              ["快照", health?.counts.snapshots ?? 0],
              ["向量", health?.vector_index.indexed ?? 0],
              ["准确率", gates?.latest_eval ? pct(gates.latest_eval.accuracy) : "—"],
            ].map(([label, value]) => (
              <div className="driver" key={label as string} style={{ gridTemplateColumns: "1fr auto" }}>
                <span className="muted" style={{ fontSize: 10.5 }}>{label}</span>
                <span className="mono" style={{ fontSize: 12 }}>{value}</span>
              </div>
            ))}
          </div>
          <div className={`badge ${gates?.ok ? "mint" : "amber"}`} style={{ marginTop: 10, whiteSpace: "normal", padding: "9px 12px", display: "block" }}>
            {gates?.ok ? "门禁通过" : "门禁未达标"} · {gates?.reasons[0] ?? gates?.warnings[0] ?? "评测与回退率在阈值内"}
          </div>
          <div className="row wrap gap-6 mt-16">
            {["PostgreSQL", "pgvector", "Redis", "FastAPI", "LangGraph", "MCP"].map((tag) => <span className="evidence" key={tag}>{tag}</span>)}
          </div>
        </Panel>
      </div>

      <Panel title="写入日志" sub="最近 12 条摄取记录" right={<span className="badge cyan">{data.collectLogs.length} 条采集日志</span>}>
        {data.logs.length === 0 ? <Empty text="还没有写入记录" /> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>来源</th><th>文件</th><th className="num">写入</th><th className="num">重复</th><th className="num">拒绝</th><th>时间</th></tr></thead>
              <tbody>
                {data.logs.map((log) => (
                  <tr key={log.id}>
                    <td><span className="badge cyan" style={{ fontSize: 9 }}>{log.source}</span></td>
                    <td className="mono" style={{ fontSize: 10.5 }}>{log.file_name ?? "—"}</td>
                    <td className="num mono">{log.rows_ok}</td>
                    <td className="num mono">{log.rows_dup}</td>
                    <td className="num mono">{log.rows_rejected}</td>
                    <td className="muted" style={{ fontSize: 10.5 }}>{ts(log.received_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
        </>
      )}
    </div>
  );
}
