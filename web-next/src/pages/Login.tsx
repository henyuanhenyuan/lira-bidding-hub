import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "../auth";

export default function Login() {
  const { me, loading } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  if (!loading && me) return <Navigate to="/" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!username.trim() || !password) {
      setMessage("请输入用户名和密码");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      if (response.status === 429) throw new Error("尝试过于频繁，请稍后再试");
      if (!response.ok) throw new Error("用户名或密码错误");
      window.location.replace("/next/");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "登录失败");
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <section className="login-intro">
        <span className="brand-mark large">竞</span>
        <h1>竞品情报工作台</h1>
        <p>
          采集、事件、建议、审批与复盘在同一条链路上。
          <br />
          每一个结论都能回到证据，每一次决策都能回收结果。
        </p>
        <ul>
          <li>事实与数字由服务端计算，模型只负责解释</li>
          <li>证据闭包不通过，建议整条作废</li>
          <li>价格、评论、采集健康度一处可见</li>
        </ul>
      </section>

      <form className="login-card" onSubmit={submit}>
        <div className="login-card-head">
          <h2>登录</h2>
          <span>内网部署 · 数据不出域</span>
        </div>
        <label>
          用户名
          <input
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoFocus
          />
        </label>
        <label>
          密码
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <button className="btn block" type="submit" disabled={busy}>
          {busy ? "登录中…" : "登录"}
        </button>
        <div className="login-message" role="status" aria-live="polite">
          {message}
        </div>
        <a className="login-old" href="/">
          进入旧版界面
        </a>
      </form>
    </div>
  );
}
