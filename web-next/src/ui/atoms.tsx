import type { ReactNode } from "react";

export function Panel({
  title,
  eyebrow,
  extra,
  children,
  className = "",
  tone,
  padded = true,
}: {
  title?: ReactNode;
  eyebrow?: ReactNode;
  extra?: ReactNode;
  children: ReactNode;
  className?: string;
  tone?: "cyan" | "violet" | "amber" | "rose" | "green" | "blue";
  padded?: boolean;
}) {
  return (
    <section className={`glass panel ${tone ? `tone-${tone}` : ""} ${className}`}>
      {(title || extra || eyebrow) && (
        <header className="panel-head">
          <div className="panel-heading">
            {eyebrow && <span className="eyebrow">{eyebrow}</span>}
            {title && <h2 className="panel-title">{title}</h2>}
          </div>
          {extra && <div className="panel-extra">{extra}</div>}
        </header>
      )}
      <div className={padded ? "panel-body" : "panel-body tight"}>{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
  accent = "cyan",
  children,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  accent?: "cyan" | "violet" | "amber" | "rose" | "green";
  children?: ReactNode;
}) {
  return (
    <div className={`glass stat accent-${accent}`}>
      <div className="stat-top">
        <span className="eyebrow">{label}</span>
        <span className={`dot ${accent}`} />
      </div>
      <div className="stat-value num">{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
      {children}
    </div>
  );
}

export function Chip({
  children,
  tone = "neutral",
  className = "",
}: {
  children: ReactNode;
  tone?: "neutral" | "cyan" | "violet" | "amber" | "rose" | "green" | "blue";
  className?: string;
}) {
  return <span className={`chip tone-${tone} ${className}`}>{children}</span>;
}

export function Btn({
  children,
  onClick,
  tone = "ghost",
  size = "md",
  disabled,
  type = "button",
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  tone?: "primary" | "ghost" | "danger" | "soft";
  size?: "sm" | "md" | "lg";
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
}) {
  return (
    <button
      type={type}
      className={`btn ${tone} ${size} ${className}`}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}

export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: ReactNode;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      className={`toggle ${checked ? "on" : ""}`}
      onClick={() => onChange(!checked)}
    >
      <span className="toggle-track">
        <span className="toggle-thumb" />
      </span>
      {label && <span className="toggle-label">{label}</span>}
    </button>
  );
}

export function Empty({ children = "暂无数据" }: { children?: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Skeleton({ height = 16, width = "100%" }: { height?: number; width?: string }) {
  return <div className="skeleton" style={{ height, width }} />;
}

export function SectionTitle({ children, eyebrow }: { children: ReactNode; eyebrow?: string }) {
  return (
    <div className="section-title">
      {eyebrow && <span className="eyebrow">{eyebrow}</span>}
      <h3>{children}</h3>
    </div>
  );
}

export function Toast({ message }: { message: { text: string; tone: string } | null }) {
  if (!message) return null;
  return <div className={`toast ${message.tone}`}>{message.text}</div>;
}
