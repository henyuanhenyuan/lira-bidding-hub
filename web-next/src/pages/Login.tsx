import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../core/auth";
import { Icon } from "../ui/icons";

export default function Login() {
  const { login, me } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (me) navigate("/", { replace: true });
  }, [me, navigate]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败，请重试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <div className="aurora" aria-hidden="true">
        <span className="a1" />
        <span className="a2" />
        <span className="a3" />
      </div>
      <div className="grain" aria-hidden="true" />

      <div className="login-art">
        <div className="brand">
          <span className="brand-orb" />
          <div>
            <strong>Lira</strong>
            <span>竞价智能中枢</span>
          </div>
        </div>
        <h1>
          让 Agent 自主跑竞价,
          <br />
          <em>人只看异常。</em>
        </h1>
        <p>
          多智能体编排自动完成采集、研判、调价与复盘；风控护栏实时校验毛利与幅度，仅把需要判断的异常推到人工台。
        </p>
        <div className="login-points">
          <span>自主调价</span>
          <span>多智能体协同</span>
          <span>MCP 工具链</span>
          <span>全链路追踪</span>
          <span>区域流水</span>
        </div>
      </div>

      <div className="glass login-card">
        <h2>进入控制台</h2>

        <form
          className="login-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <label className="field">
            <span className="field-label">账号</span>
            <input
              className="input"
              value={username}
              autoComplete="username"
              onChange={(e) => setUsername(e.target.value)}
              placeholder="请输入账号"
            />
          </label>
          <label className="field">
            <span className="field-label">密码</span>
            <input
              className="input"
              type="password"
              value={password}
              autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)}
              placeholder="请输入密码"
            />
          </label>
          {error && <div className="login-error">{error}</div>}
          <button className="btn primary lg" type="submit" disabled={busy}>
            {busy ? "正在验证…" : "登入中枢"}
            {!busy && <Icon name="arrow" size={16} />}
          </button>
        </form>
      </div>
    </div>
  );
}
