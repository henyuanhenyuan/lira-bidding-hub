import { NavLink } from "react-router-dom";
import type { ReactNode } from "react";

import { useAuth } from "../core/auth";

export function Page({
  title,
  desc,
  actions,
  children,
}: {
  title: string;
  desc?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <>
      <header className="page-head">
        <div>
          <h1>{title}</h1>
          {desc && <p className="page-desc">{desc}</p>}
        </div>
        {actions && <div className="page-actions">{actions}</div>}
      </header>
      {children}
    </>
  );
}

export function Card({
  title,
  sub,
  extra,
  flush,
  children,
}: {
  title?: string;
  sub?: string;
  extra?: ReactNode;
  flush?: boolean;
  children: ReactNode;
}) {
  return (
    <section className="card">
      {(title || extra) && (
        <div className="card-head">
          {title && <h2>{title}</h2>}
          {sub && <span className="card-sub">{sub}</span>}
          {extra && <div className="card-extra">{extra}</div>}
        </div>
      )}
      <div className={`card-body${flush ? " flush" : ""}`}>{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "ok" | "warn" | "danger";
}) {
  return (
    <div className={`stat${tone ? ` tone-${tone}` : ""}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

export function Badge({
  tone = "neutral",
  children,
}: {
  tone?: "neutral" | "ok" | "warn" | "danger" | "accent";
  children: ReactNode;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Spinner({ label = "加载中…" }: { label?: string }) {
  return <div className="loader">{label}</div>;
}

export function ErrorBox({ message }: { message: string }) {
  return <div className="error-box">{message}</div>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

export function Table({
  head,
  children,
}: {
  head: ReactNode[];
  children: ReactNode;
}) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            {head.map((item, index) => (
              <th key={index}>{item}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function SeverityBadge({ value }: { value: string }) {
  const tone = value === "L3" ? "danger" : value === "L2" ? "warn" : "neutral";
  return <Badge tone={tone}>{value}</Badge>;
}

const STATUS_TEXT: Record<string, string> = {
  pending: "待提交",
  submitted: "待审批",
  approved: "已批准",
  executed: "已执行",
  rejected: "已驳回",
  cancelled: "已取消",
  holdout: "观察组",
  running: "运行中",
  succeeded: "成功",
  failed: "失败",
};

export function StatusBadge({ value }: { value: string }) {
  const tone =
    value === "executed" || value === "succeeded"
      ? "ok"
      : value === "failed" || value === "rejected"
        ? "danger"
        : value === "submitted" || value === "running"
          ? "accent"
          : "neutral";
  return <Badge tone={tone}>{STATUS_TEXT[value] ?? value}</Badge>;
}

const ACTION_TEXT: Record<string, string> = {
  follow: "跟进降价",
  hold: "观察",
  adjust_coupon: "投券对冲",
  join_promo: "报名活动",
  no_action: "不动作",
};

export function actionText(action: string): string {
  return ACTION_TEXT[action] ?? action;
}

export function Shell({
  children,
  pending,
}: {
  children: ReactNode;
  pending?: number;
}) {
  const { me, logout } = useAuth();
  const roleText =
    me?.role === "admin" ? "管理员" : me?.role === "manager" ? "主管" : me ? "成员" : "未登录";

  const groups: { group: string; items: { to: string; label: string }[] }[] = [
    {
      group: "工作区",
      items: [
        { to: "/", label: "总览" },
        { to: "/events", label: "事件与研判" },
        { to: "/suggestions", label: "建议" },
        { to: "/approvals", label: "待审批" },
      ],
    },
    {
      group: "Agent",
      items: [
        { to: "/runs", label: "运行轨迹" },
        { to: "/knowledge", label: "知识库" },
        { to: "/tools", label: "工具与 MCP" },
      ],
    },
    {
      group: "质量",
      items: [
        { to: "/eval", label: "评测" },
        { to: "/observability", label: "可观测" },
      ],
    },
    {
      group: "系统",
      items: [
        { to: "/targets", label: "竞品目标" },
        { to: "/settings", label: "设置" },
      ],
    },
  ];

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">L</div>
          <div className="brand-text">
            <b>Lira Agent</b>
            <span>竞品情报 · Agent 工作台</span>
          </div>
        </div>
        <nav className="nav">
          {groups.map((group) => (
            <div className="nav-group" key={group.group}>
              <span className="nav-label">{group.group}</span>
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
                >
                  <i className="dot" />
                  {item.label}
                  {item.to === "/approvals" && (pending ?? 0) > 0 && (
                    <span className="nav-badge">{pending}</span>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="avatar">{(me?.username ?? "L").slice(0, 1).toUpperCase()}</div>
          <div className="who">
            <b>{me?.username ?? "local"}</b>
            <span>{me?.auth ? roleText : `${roleText} · 本地模式`}</span>
          </div>
          <button className="icon-btn" title="退出登录" onClick={() => void logout()}>
            ⎋
          </button>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
