import type { ReactNode } from "react";

import { GUARDRAIL_TEXT, STATUS_TEXT } from "../labels";
import type { Guardrail, Severity, SuggestionStatus } from "../types";

export function PageHead({
  title,
  sub,
  actions,
}: {
  title: string;
  sub?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-head">
      <div>
        <h1>{title}</h1>
        {sub && <p>{sub}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}

export function Card({
  title,
  sub,
  actions,
  children,
  className = "",
}: {
  title?: string;
  sub?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <div className="card-head">
          <div>
            {title && <h2>{title}</h2>}
            {sub && <p>{sub}</p>}
          </div>
          {actions && <div className="card-actions">{actions}</div>}
        </div>
      )}
      <div className="card-body">{children}</div>
    </section>
  );
}

export function Metric({
  label,
  value,
  sub,
  tone = "",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "warn" | "danger" | "ok" | "";
}) {
  return (
    <div className={`metric ${tone}`}>
      <span className="metric-label">{label}</span>
      <strong>{value}</strong>
      {sub && <span className="metric-sub">{sub}</span>}
    </div>
  );
}

export function SeverityBadge({ value }: { value: Severity }) {
  return <span className={`badge sev-${value}`}>{value}</span>;
}

export function GateBadge({ value }: { value: string }) {
  return <span className={`badge gate-${value}`}>{value}</span>;
}

export function StatusBadge({ value }: { value: SuggestionStatus }) {
  return <span className={`badge status-${value}`}>{STATUS_TEXT[value] ?? value}</span>;
}

export function GuardrailBadge({ value }: { value?: Guardrail }) {
  if (!value) return null;
  return <span className={`badge guard-${value}`}>{GUARDRAIL_TEXT[value]}</span>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Loader({ label = "载入中…" }: { label?: string }) {
  return (
    <div className="state">
      <span className="spinner" />
      {label}
    </div>
  );
}

export function ErrorBox({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="error-box">
      <strong>读取失败</strong>
      <span>{message}</span>
      {onRetry && (
        <button className="btn ghost small" onClick={onRetry}>
          重试
        </button>
      )}
    </div>
  );
}

export function KV({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="kv">
      {rows.map(([key, value], index) => (
        <div key={`${key}-${index}`}>
          <dt>{key}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <h3 className="section-title">{children}</h3>;
}
