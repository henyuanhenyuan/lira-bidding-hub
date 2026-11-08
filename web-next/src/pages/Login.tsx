import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { api, ApiError } from "../core/api";
import { useAuth } from "../core/auth";

export default function Login() {
  const { me, refresh } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (me) return <Navigate to="/" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.post("/api/login", { username, password });
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
    <div className="login">
      <div className="login-art">
        <div>
          <div className="brand-mark" style={{ marginBottom: 28 }}>
            L
          </div>
          <h1>
            让 Agent 替你
            <br />
            盯竞品、给方案、留证据
          </h1>
          <p>
            采集 → 到手价 → 事件 → 多 Agent 研判 → 人工审批 → 结果回收。
            每一步都可审计，模型只解释，不决策。
          </p>
          <ul className="login-points">
            <li>
              <b>多 Agent</b>　Steward / Analyst / Risk / Writer 分工协作
            </li>
            <li>
              <b>可评测</b>　120 条金标 + 检索指标 + 门禁
            </li>
            <li>
              <b>可观测</b>　span 追踪、token 与成本、P95 延迟
            </li>
          </ul>
        </div>
        <span style={{ color: "#64748b", fontSize: 12 }}>
          Lira Agent · 单机可运行 · 本地模型或 qwen-plus
        </span>
      </div>

      <div className="login-form">
        <form className="login-card" onSubmit={submit}>
          <h2>登录工作台</h2>
          <p className="hint">使用账号密码进入。本地模式下可直接访问。</p>

          {error && <div className="error-box">{error}</div>}

          <label className="field">
            <span>账号</span>
            <input
              className="input"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="admin"
            />
          </label>
          <label className="field">
            <span>密码</span>
            <input
              className="input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="••••••••"
            />
          </label>

          <button className="btn" style={{ width: "100%", marginTop: 6 }} disabled={busy}>
            {busy ? "登录中…" : "登录"}
          </button>
          <p className="login-foot">
            未开启鉴权时也可直接进入；开启后请使用管理员分配的账号。
          </p>
        </form>
      </div>
    </div>
  );
}
