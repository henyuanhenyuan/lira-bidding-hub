import { useEffect, useState } from "react";

import { api } from "../core/api";
import { canManage, useAuth } from "../core/auth";
import { useAsync } from "../core/hooks";
import { Badge, Card, Empty, ErrorBox, Field, Page, Spinner, Table } from "../ui/kit";

interface User {
  username: string;
  role: string;
}

interface Ops {
  scheduler: { enabled: boolean; mode: string };
  auth_enabled: boolean;
  backups: string[];
  freshness: { stale?: boolean; lag_hours?: number };
}

interface SourcesView {
  taobao: { app_key: string; has_secret: boolean };
  octoparse: { base_url: string; has_token: boolean };
  ingest: { url: string; has_token: boolean };
  file: { formats: string[]; endpoint: string };
}

interface ModelsView {
  backend: string;
  route: string;
  local: { model: string; url: string };
  api: { base_url: string; model: string; has_key: boolean };
  judge_model: string;
}

export default function Settings() {
  const { me } = useAuth();
  const editable = canManage(me);
  const { data, error, loading, reload } = useAsync(async () => {
    const [users, ops, models, sources] = await Promise.all([
      api.get<User[]>("/api/users").catch(() => []),
      api.get<Ops>("/api/ops").catch(() => null),
      api.get<ModelsView>("/api/settings/models").catch(() => null),
      api.get<SourcesView>("/api/settings/sources").catch(() => null),
    ]);
    return { users, ops, models, sources };
  }, []);

  const [source, setSource] = useState<"local" | "api">("local");
  const [localModel, setLocalModel] = useState("qwen3:4b");
  const [localUrl, setLocalUrl] = useState("http://127.0.0.1:11434");
  const [apiBase, setApiBase] = useState("");
  const [apiModel, setApiModel] = useState("qwen-plus");
  const [apiKey, setApiKey] = useState("");
  const [message, setMessage] = useState("");
  const [probe, setProbe] = useState<string>("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!data?.models) return;
    const view = data.models;
    setSource(view.route === "openai" ? "api" : "local");
    setLocalModel(view.local.model);
    setLocalUrl(view.local.url);
    setApiBase(view.api.base_url);
    setApiModel(view.api.model);
  }, [data?.models]);

  async function saveModels() {
    setBusy(true);
    setMessage("");
    try {
      await api.post("/api/settings/models", {
        backend: "gateway",
        route: source === "api" ? "openai" : "ollama",
        local_model: localModel,
        local_url: localUrl,
        api_base_url: apiBase,
        api_model: apiModel,
        api_key: apiKey || null,
      });
      setApiKey("");
      setMessage("模型设置已保存，立即生效");
      setProbe("");
      await reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function runProbe() {
    setProbe("检测中…");
    try {
      const result = await api.get<{ llm_available: boolean; backend: string; route: string }>(
        "/api/settings/models/probe",
      );
      setProbe(
        result.llm_available
          ? `可用 · ${result.backend}/${result.route}`
          : `不可用 · ${result.backend}/${result.route}`,
      );
    } catch (err) {
      setProbe(err instanceof Error ? err.message : "检测失败");
    }
  }

  const [sourceTab, setSourceTab] = useState<"taobao" | "octoparse" | "file">("taobao");
  const [taobaoKey, setTaobaoKey] = useState("");
  const [taobaoSecret, setTaobaoSecret] = useState("");
  const [octoBase, setOctoBase] = useState("https://dataapi.octoparse.com");
  const [octoToken, setOctoToken] = useState("");
  const [fileResult, setFileResult] = useState("");

  useEffect(() => {
    if (!data?.sources) return;
    setTaobaoKey(data.sources.taobao.app_key);
    setOctoBase(data.sources.octoparse.base_url);
  }, [data?.sources]);

  async function saveSources() {
    setBusy(true);
    setMessage("");
    try {
      await api.post("/api/settings/sources", {
        taobao_app_key: taobaoKey,
        taobao_app_secret: taobaoSecret || null,
        octoparse_base_url: octoBase,
        octoparse_token: octoToken || null,
      });
      setTaobaoSecret("");
      setOctoToken("");
      setMessage("数据接入已保存");
      await reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function uploadFile(file: File | null) {
    if (!file) return;
    setBusy(true);
    setFileResult("");
    try {
      const result = await api.upload<{ rows_ok?: number; rows_dup?: number; errors?: unknown[] }>(
        "/api/import/file",
        file,
      );
      setFileResult(
        `导入 ${result.rows_ok ?? 0} 条，重复 ${result.rows_dup ?? 0} 条` +
          (result.errors?.length ? `，错误 ${result.errors.length} 条` : ""),
      );
      await reload();
    } catch (err) {
      setFileResult(err instanceof Error ? err.message : "上传失败");
    } finally {
      setBusy(false);
    }
  }

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("member");

  async function createUser() {
    setMessage("");
    try {
      await api.post("/api/users", { username, password, role });
      setUsername("");
      setPassword("");
      setMessage("账号已创建");
      await reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "创建失败");
    }
  }

  async function setRoleFor(user: User, next: string) {
    try {
      await api.patch(`/api/users/${encodeURIComponent(user.username)}`, { role: next });
      await reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "修改失败");
    }
  }

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  return (
    <Page title="设置" desc="模型来源、账号与运行环境">
      {message && <div className="notice">{message}</div>}

      <Card
        title="模型来源"
        sub="本地 Ollama 与云端 API 可随时切换，保存后立即生效"
        extra={<Badge tone={probe.startsWith("可用") ? "ok" : "neutral"}>{probe || "未检测"}</Badge>}
      >
        <div className="segment">
          <button
            className={`segment-item${source === "local" ? " on" : ""}`}
            onClick={() => setSource("local")}
          >
            本地模型
            <em>{localModel}</em>
          </button>
          <button
            className={`segment-item${source === "api" ? " on" : ""}`}
            onClick={() => setSource("api")}
          >
            云端 API
            <em>{apiModel}</em>
          </button>
        </div>

        {source === "local" ? (
          <div className="model-form">
            <Field label="模型名">
              <input className="input" value={localModel} onChange={(e) => setLocalModel(e.target.value)} />
            </Field>
            <Field label="Ollama 地址">
              <input className="input" value={localUrl} onChange={(e) => setLocalUrl(e.target.value)} />
            </Field>
          </div>
        ) : (
          <div className="model-form">
            <Field label="Base URL（OpenAI 兼容）">
              <input
                className="input"
                value={apiBase}
                onChange={(e) => setApiBase(e.target.value)}
                placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1"
              />
            </Field>
            <Field label="模型名">
              <input className="input" value={apiModel} onChange={(e) => setApiModel(e.target.value)} />
            </Field>
            <Field label={`API Key${data.models?.api.has_key ? "（已保存，留空则沿用）" : ""}`}>
              <input
                className="input"
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={data.models?.api.has_key ? "••••••••" : "sk-..."}
              />
            </Field>
          </div>
        )}

        <div className="row">
          <button className="btn" disabled={!editable || busy} onClick={() => void saveModels()}>
            {busy ? "保存中…" : "保存并切换"}
          </button>
          <button className="btn ghost" onClick={() => void runProbe()}>
            检测连通
          </button>
          {!editable && <span className="hint">需要管理员权限。</span>}
        </div>
      </Card>

      <Card
        title="数据接入"
        sub="淘宝开放平台 / 影刃八爪鱼 / 文件导入，保存后即可被采集链路使用"
        extra={
          <Badge tone="neutral">
            推送 {data.sources?.ingest.url ?? "/v1/ingest/snapshots"}
          </Badge>
        }
      >
        <div className="segment three">
          {([
            ["taobao", "淘宝开放平台", data.sources?.taobao.has_secret ? "已配置密钥" : "未配置"],
            ["octoparse", "影刃八爪鱼", data.sources?.octoparse.has_token ? "已配置令牌" : "未配置"],
            ["file", "文件导入", "CSV / JSON"],
          ] as const).map(([key, label, hint]) => (
            <button
              key={key}
              className={`segment-item${sourceTab === key ? " on" : ""}`}
              onClick={() => setSourceTab(key)}
            >
              {label}
              <em>{hint}</em>
            </button>
          ))}
        </div>

        {sourceTab === "taobao" && (
          <div className="model-form">
            <Field label="App Key">
              <input className="input" value={taobaoKey} onChange={(e) => setTaobaoKey(e.target.value)} />
            </Field>
            <Field label={`App Secret${data.sources?.taobao.has_secret ? "（已保存，留空沿用）" : ""}`}>
              <input
                className="input"
                type="password"
                value={taobaoSecret}
                onChange={(e) => setTaobaoSecret(e.target.value)}
                placeholder={data.sources?.taobao.has_secret ? "••••••••" : "secret"}
              />
            </Field>
          </div>
        )}

        {sourceTab === "octoparse" && (
          <div className="model-form">
            <Field label="API 地址">
              <input className="input" value={octoBase} onChange={(e) => setOctoBase(e.target.value)} />
            </Field>
            <Field label={`Access Token${data.sources?.octoparse.has_token ? "（已保存，留空沿用）" : ""}`}>
              <input
                className="input"
                type="password"
                value={octoToken}
                onChange={(e) => setOctoToken(e.target.value)}
                placeholder={data.sources?.octoparse.has_token ? "••••••••" : "token"}
              />
            </Field>
          </div>
        )}

        {sourceTab === "file" && (
          <div>
            <p className="hint" style={{ marginTop: 0 }}>
              支持 CSV（target_id,ts,list_price,title,source_tier）或 JSON 快照数组。
            </p>
            <input
              type="file"
              accept=".csv,.json"
              disabled={busy}
              onChange={(event) => void uploadFile(event.target.files?.[0] ?? null)}
            />
            {fileResult && <p className="hint">{fileResult}</p>}
          </div>
        )}

        {sourceTab !== "file" && (
          <div className="row" style={{ marginTop: 10 }}>
            <button className="btn" disabled={!editable || busy} onClick={() => void saveSources()}>
              {busy ? "保存中…" : "保存接入配置"}
            </button>
            {!editable && <span className="hint">需要管理员权限。</span>}
          </div>
        )}
      </Card>

      <div className="split">
        <Card title="账号" sub="管理员可创建账号与调整角色" flush>
          {(data.users ?? []).length === 0 ? (
            <Empty>未开启鉴权或没有账号。</Empty>
          ) : (
            <Table head={["账号", "角色", "操作"]}>
              {(data.users ?? []).map((user) => (
                <tr key={user.username}>
                  <td>{user.username}</td>
                  <td>
                    <Badge tone={user.role === "admin" ? "accent" : "neutral"}>{user.role}</Badge>
                  </td>
                  <td>
                    {editable ? (
                      <select
                        className="input"
                        value={user.role}
                        onChange={(event) => void setRoleFor(user, event.target.value)}
                      >
                        <option value="member">member</option>
                        <option value="manager">manager</option>
                        <option value="admin">admin</option>
                      </select>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </Table>
          )}
        </Card>

        <Card title="新建账号">
          <Field label="账号">
            <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} />
          </Field>
          <Field label="初始密码">
            <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Field label="角色">
            <select className="input" value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="member">member</option>
              <option value="manager">manager</option>
              <option value="admin">admin</option>
            </select>
          </Field>
          <button className="btn" disabled={!editable} onClick={() => void createUser()}>
            创建
          </button>
        </Card>
      </div>

      <Card title="运行环境">
        {!data.ops ? (
          <Empty>运维信息仅管理员可见。</Empty>
        ) : (
          <dl className="kv">
            <dt>鉴权</dt>
            <dd>{data.ops.auth_enabled ? <Badge tone="ok">已开启</Badge> : <Badge tone="neutral">本地模式</Badge>}</dd>
            <dt>调度</dt>
            <dd>
              {data.ops.scheduler.mode}
              {data.ops.scheduler.enabled ? " · 运行中" : " · 关闭"}
            </dd>
            <dt>数据新鲜度</dt>
            <dd>
              {data.ops.freshness?.lag_hours != null
                ? `${Math.round(data.ops.freshness.lag_hours)}h`
                : "—"}
              {data.ops.freshness?.stale ? " · 已超时" : ""}
            </dd>
            <dt>备份</dt>
            <dd>{data.ops.backups?.slice(0, 2).join(" / ") || "—"}</dd>
          </dl>
        )}
      </Card>
    </Page>
  );
}
