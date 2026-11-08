import { NavLink, Outlet } from "react-router-dom";

import { api } from "../api";
import { useAuth } from "../auth";
import { useAsync, useStreamBridge, useStreamEvent } from "../hooks";
import { ROLE_TEXT } from "../labels";
import type { Suggestion } from "../types";
import Icon from "./Icon";

interface NavItem {
  to: string;
  label: string;
  icon: string;
  end?: boolean;
  adminOnly?: boolean;
  staffOnly?: boolean;
}

const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "监控任务管理",
    items: [
      { to: "/collection", label: "任务配置", icon: "collection", adminOnly: true },
      { to: "/import", label: "数据导入", icon: "import" },
    ],
  },
  {
    group: "数据看板",
    items: [
      { to: "/", label: "总览", icon: "overview", end: true },
      { to: "/competitors", label: "竞品 360", icon: "competitors" },
      { to: "/reviews", label: "评论洞察", icon: "cases" },
      { to: "/cases", label: "案例库", icon: "cases" },
    ],
  },
  {
    group: "预警中心",
    items: [
      { to: "/events", label: "预警事件", icon: "events" },
      { to: "/suggestions", label: "处置建议", icon: "suggestions" },
      { to: "/approvals", label: "审批", icon: "approvals" },
      { to: "/outcomes", label: "结果回收", icon: "outcome" },
    ],
  },
  {
    group: "系统设置",
    items: [
      { to: "/collect-logs", label: "采集日志", icon: "trace", adminOnly: true },
      { to: "/agent", label: "Agent 轨迹", icon: "trace" },
      { to: "/docs", label: "规则库", icon: "docs" },
      { to: "/targets", label: "竞品目标", icon: "competitors", staffOnly: true },
      { to: "/mappings", label: "SKU 对齐", icon: "cases", staffOnly: true },
      { to: "/ask", label: "问数", icon: "ask" },
      { to: "/skills", label: "Skill 管理", icon: "skills", staffOnly: true },
      { to: "/eval", label: "评测", icon: "eval", staffOnly: true },
      { to: "/observability", label: "观测", icon: "trace", staffOnly: true },
      { to: "/admin", label: "账号", icon: "admin", adminOnly: true },
    ],
  },
];

export default function Layout() {
  const { me, logout } = useAuth();
  useStreamBridge();

  const { data: approvals, reload } = useAsync(
    () => api.get<Suggestion[]>("/api/approvals/inbox"),
    [],
  );
  useStreamEvent(["approval"], () => void reload());

  const role = me?.role ?? "member";
  const name = me?.username || me?.actor || "local";
  const pending = approvals?.length ?? 0;

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">竞</span>
          <span className="brand-text">
            <strong>竞品情报</strong>
            <em>竞品情报工作台</em>
          </span>
        </div>

        <nav className="nav">
          {NAV.map((group) => {
            const items = group.items.filter((item) => {
              if (item.adminOnly) return role === "admin";
              if (item.staffOnly) return role === "admin" || role === "manager";
              return true;
            });
            if (!items.length) return null;
            return (
              <div className="nav-group" key={group.group}>
                <span className="nav-label">{group.group}</span>
                {items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
                  >
                    <Icon name={item.icon} />
                    <span className="nav-text">{item.label}</span>
                    {item.to === "/approvals" && pending > 0 && (
                      <span className="nav-badge">{pending}</span>
                    )}
                  </NavLink>
                ))}
              </div>
            );
          })}
        </nav>

        <div className="sidebar-foot">
          <div className="user">
            <span className="avatar">{name.slice(0, 1).toUpperCase()}</span>
            <span className="user-meta">
              <b>{name}</b>
              <em>{me?.auth ? ROLE_TEXT[role] ?? role : "本地模式"}</em>
            </span>
            <button className="icon-btn" onClick={() => void logout()} title="退出登录">
              <Icon name="logout" size={16} />
            </button>
          </div>
        </div>
      </aside>

      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
