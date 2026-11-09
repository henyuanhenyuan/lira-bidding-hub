import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { api, ApiError } from "../core/api";
import { useAuth } from "../core/auth";

const FEATS = [
  { g: "◈", t: "多智能体实时研判", d: "Steward / Analyst / Risk / Writer 分工跑完采集、归因、护栏与建议" },
  { g: "◇", t: "结论可溯源", d: "每条建议绑定事件、价格与知识库证据，动作由确定性策略给出" },
  { g: "⌁", t: "评测与微调闭环", d: "金标、判官、门禁与 LoRA/SFT 数据链路都可量化" },
];

export default function Login() {
  const { me, refresh } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (me) return <Navigate to="/" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/login", { username: username.trim(), password });
      await refresh();
      navigate("/", { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "账号或密码不正确"
          : err instanceof Error
            ? err.message
            : "登录失败",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-shell">
      <div className="login-visual">
        <div className="brand">
          <div className="brand-mark" />
          <div className="stack" style={{ lineHeight: 1.15 }}>
            <span className="brand-name">Lira</span>
            <span className="brand-sub">Bidding Agent Console</span>
          </div>
        </div>

        <div className="login-copy fade-in">
          <h1 className="login-title">
            把竞品货架
            <br />
            <em>装进会分析的小卖铺</em>
          </h1>
          <p className="soft" style={{ marginTop: 16, fontSize: 15, maxWidth: 470 }}>
            不是问答工具。多智能体嵌入竞价视图，读取真实价格与事件，
            直接给出归因、置信度、毛利护栏与可执行动作。
          </p>

          <div className="login-feats">
            {FEATS.map((feat) => (
              <div className="feat" key={feat.t}>
                <div className="fi">{feat.g}</div>
                <div className="stack">
                  <span style={{ fontSize: 13.5, fontWeight: 600 }}>{feat.t}</span>
                  <span className="muted" style={{ fontSize: 12.5 }}>{feat.d}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="row gap-10 muted wrap" style={{ fontSize: 11.5 }}>
          <span className="badge mint"><i className="dot" /> FastAPI</span>
          <span className="badge violet"><i className="dot" /> LangGraph</span>
          <span className="badge cyan"><i className="dot" /> pgvector</span>
          <span className="badge amber"><i className="dot" /> MCP</span>
        </div>
      </div>

      <div className="login-card-wrap">
        <div className="orb" aria-hidden="true" />
        <div className="orb small" aria-hidden="true" />
        <div className="glass tilt login-card pad-lg fade-in" style={{ position: "relative", zIndex: 2 }}>
          <div className="stack gap-4">
            <span className="eyebrow">Sign in</span>
            <h2 className="h2">进入竞价控制台</h2>
            <p className="muted" style={{ fontSize: 12.5, marginTop: 2 }}>
              使用管理员分配的账号登录
            </p>
          </div>

          <form className="stack gap-12 mt-24" onSubmit={submit}>
            <div className="field">
              <label>账号</label>
              <input
                className="input"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="admin"
                autoComplete="username"
              />
            </div>
            <div className="field">
              <label>密码</label>
              <input
                className="input"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
              />
            </div>

            {error && (
              <div className="badge rose" style={{ whiteSpace: "normal", padding: "9px 12px" }}>
                {error}
              </div>
            )}

            <button className="btn primary mt-4" type="submit" disabled={busy || !username.trim()}>
              {busy ? "验证中…" : "进入控制台"}
            </button>
          </form>

          <div className="divider mt-24" />
          <div className="row between mt-12 muted" style={{ fontSize: 11.5 }}>
            <span>核心通道 qwen-plus · 本机 4B 仅测试</span>
            <span className="mono">v2.0</span>
          </div>
        </div>
      </div>
    </div>
  );
}
