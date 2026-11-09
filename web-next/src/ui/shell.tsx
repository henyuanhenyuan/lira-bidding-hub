import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { api } from "../core/api";
import { useAuth } from "../core/auth";
import { ROLE_TEXT } from "./kit";

const NAV = [
  { to: "/", label: "智能竞价分析", glyph: "◐" },
  { to: "/agent", label: "Agent 模型", glyph: "◇" },
  { to: "/settings", label: "设置", glyph: "⚙" },
];

const TITLES: Record<string, { title: string; sub: string }> = {
  "/": { title: "智能竞价分析", sub: "Intelligent Bidding Analysis" },
  "/agent": { title: "Agent 模型", sub: "Multi-Agent Orchestration" },
  "/settings": { title: "设置", sub: "Model Routing & Governance" },
};

export default function Shell() {
  const { me, logout } = useAuth();
  const loc = useLocation();
  const meta = TITLES[loc.pathname] ?? TITLES["/"];
  const [online, setOnline] = useState(false);
  const [pending, setPending] = useState(0);

  useEffect(() => {
    let alive = true;
    void api.get<{ llm_available?: boolean }>("/api/health")
      .then((h) => alive && setOnline(Boolean(h.llm_available)))
      .catch(() => undefined);
    const loadPending = () => {
      if (document.hidden) return;
      void api.get<unknown[]>("/api/approvals/inbox")
        .then((rows) => alive && setPending(rows.length))
        .catch(() => undefined);
    };
    loadPending();
    const timer = window.setInterval(loadPending, 60_000);
    document.addEventListener("visibilitychange", loadPending);
    return () => {
      alive = false;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", loadPending);
    };
  }, []);

  const name = me?.display_name || me?.username || "local";
  const role = me?.role_text || ROLE_TEXT[me?.role ?? ""] || "成员";

  return (
    <div className="app">
      <aside className="rail">
        <div className="brand">
          <div className="brand-mark" />
          <div className="stack" style={{ lineHeight: 1.15 }}>
            <span className="brand-name">Lira</span>
            <span className="brand-sub">Bidding Agent</span>
          </div>
        </div>

        <nav className="nav">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
            >
              <span className="glyph">{item.glyph}</span>
              <span>{item.label}</span>
              {item.to === "/" && pending > 0 && (
                <span className="badge rose" style={{ marginLeft: "auto", fontSize: 9.5 }}>{pending}</span>
              )}
            </NavLink>
          ))}
        </nav>

        <div style={{ flex: 1 }} />

        <div className="stack gap-10">
          <div className="divider" />
          <div className="user-chip">
            <div className="avatar">{name.slice(0, 1)}</div>
            <div className="stack" style={{ lineHeight: 1.2 }}>
              <span style={{ fontSize: 12.5, fontWeight: 600 }}>{name}</span>
              <span className="muted" style={{ fontSize: 10.5 }}>{role}</span>
            </div>
          </div>
          <button className="btn ghost sm" onClick={() => void logout()}>退出登录</button>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="topbar-left">
            <span className="eyebrow">{meta.sub}</span>
            <h1 className="h1">{meta.title}</h1>
          </div>
          <div className="topbar-actions">
            <span className={`badge ${online ? "mint" : ""}`}>
              <i className="dot" /> {online ? "模型在线" : "规则兜底"}
            </span>
            <span className="badge cyan">PostgreSQL · pgvector</span>
            <NavLink to="/screen" className="btn sm primary" style={{ textDecoration: "none" }}>
              切换可视化大屏
            </NavLink>
          </div>
        </header>
        <Outlet />
      </main>
    </div>
  );
}
