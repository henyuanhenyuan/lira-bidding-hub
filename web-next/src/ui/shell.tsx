import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../core/auth";
import { useLive } from "../core/live";
import { Boundary } from "./Boundary";
import { Icon } from "./icons";

const NAV = [
  { to: "/", label: "调度中枢", icon: "control", end: true },
  { to: "/bidding", label: "竞价台", icon: "bidding" },
  { to: "/agents", label: "智能体", icon: "agents" },
  { to: "/sources", label: "数据接入", icon: "sources" },
  { to: "/evaluation", label: "评测", icon: "eval" },
  { to: "/settings", label: "设置", icon: "settings" },
];

const TITLES: Record<string, { title: string; sub: string }> = {
  "/": { title: "调度中枢", sub: "Agent 自主竞价 · 人工只看异常" },
  "/bidding": { title: "竞价台", sub: "目标池 · 自主调价 · 人工确认" },
  "/agents": { title: "智能体集群", sub: "多智能体编排 · MCP 工具 · 全链路追踪" },
  "/sources": { title: "数据接入", sub: "影刃 / 八爪鱼 · 自有爬虫 · 文件导入" },
  "/evaluation": { title: "评测与质量", sub: "评测集 · Bad Case · LLM-as-Judge" },
  "/settings": { title: "控制设置", sub: "模型通道 · 竞价策略 · 微调" },
};

export default function Shell() {
  const { me, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { connected } = useLive(1);
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [location.pathname]);

  const meta = TITLES[location.pathname] || TITLES["/"];

  return (
    <div className="shell">
      <div className="aurora" aria-hidden="true">
        <span className="a1" />
        <span className="a2" />
        <span className="a3" />
      </div>
      <div className="grain" aria-hidden="true" />

      <aside className="rail glass">
        <div className="brand">
          <span className="brand-orb" />
          <div>
            <strong>Lira</strong>
            <span>竞价智能中枢</span>
          </div>
        </div>

        <nav className="nav">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
            >
              <span className="nav-icon">
                <Icon name={item.icon} size={19} />
              </span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="rail-foot">
          <button className="rail-action" onClick={() => navigate("/screen")}>
            <Icon name="screen" size={17} />
            进入大屏
          </button>
          <div className="identity">
            <span className="avatar">{(me?.display_name || "L").slice(0, 1)}</span>
            <div className="identity-text">
              <strong>{me?.display_name || "本地模式"}</strong>
              <span>{me?.role_text || "管理员"}</span>
            </div>
            <button className="icon-btn" title="退出登录" onClick={() => void logout()}>
              <Icon name="logout" size={16} />
            </button>
          </div>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="page-head">
            <h1>{meta.title}</h1>
            <p>{meta.sub}</p>
          </div>
          <div className="topbar-right">
            <div className={`live-pill ${connected ? "on" : "off"}`}>
              <span className="live-dot" />
              {connected ? "实时链路" : "重连中"}
            </div>
            <div className="clock-chip num">
              <Icon name="clock" size={15} />
              {now.toLocaleTimeString("zh-CN", { hour12: false })}
            </div>
            <div className="model-chip" title="当前推理通道">
              <Icon name="cpu" size={15} />
              <div>
                <strong>Qwen-Plus</strong>
                <span>竞价微调版</span>
              </div>
            </div>
          </div>
        </header>

        <main className="content">
          <Boundary>
            <Outlet />
          </Boundary>
        </main>
      </div>
    </div>
  );
}
