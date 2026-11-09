import { useState, type ReactNode } from "react";

export function Panel({
  title,
  sub,
  right,
  children,
  className = "",
  flush = false,
  fill = false,
}: {
  title?: ReactNode;
  sub?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  flush?: boolean;
  fill?: boolean;
}) {
  return (
    <section className={`glass tilt ${flush ? "flush" : ""} ${fill ? "panel-fill" : ""} ${className}`}>
      {(title || right) && (
        <header className="row between wrap gap-10 pad panel-head" style={{ paddingBottom: 12 }}>
          <div className="stack">
            {sub && <span className="eyebrow">{sub}</span>}
            {title && <h3 className="h3">{title}</h3>}
          </div>
          {right}
        </header>
      )}
      <div className={flush ? "panel-body" : "pad panel-body"} style={flush ? undefined : { paddingTop: 0 }}>
        {children}
      </div>
    </section>
  );
}

export function Sparkline({
  values,
  width = 140,
  height = 34,
  tone = "cyan",
}: {
  values: number[];
  width?: number;
  height?: number;
  tone?: "cyan" | "violet" | "mint" | "rose";
}) {
  const clean = values.filter((v) => v !== null && !Number.isNaN(v));
  if (clean.length < 2) return <div className="spark" style={{ height }} />;
  const min = Math.min(...clean);
  const max = Math.max(...clean);
  const span = max - min || 1;
  const step = width / (clean.length - 1);
  const pts = clean.map((v, i) => [i * step, height - ((v - min) / span) * (height - 4) - 2]);
  const line = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${line} L${width},${height} L0,${height} Z`;
  const id = `sg-${tone}-${Math.round(width)}-${clean.length}`;
  const colors: Record<string, string> = {
    cyan: "#5be1ff",
    violet: "#9b7bff",
    mint: "#4ef2c0",
    rose: "#ff7a9c",
  };
  const stroke = colors[tone] ?? colors.cyan;
  return (
    <svg className="spark" viewBox={`0 0 ${width} ${height}`} width="100%" height={height} preserveAspectRatio="none">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.34" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={stroke} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" opacity="0.95" />
    </svg>
  );
}

export function Delta({ value, inverted = false }: { value: number; inverted?: boolean }) {
  if (!Number.isFinite(value)) return <span className="delta flat">—</span>;
  if (Math.abs(value) < 0.0005) return <span className="delta flat">持平</span>;
  const good = inverted ? value < 0 : value > 0;
  return (
    <span className={`delta ${good ? "up" : "down"}`}>
      {value > 0 ? "▲" : "▼"} {Math.abs(value * 100).toFixed(1)}%
    </span>
  );
}

export function Seg<T extends string>({
  value,
  items,
  onChange,
}: {
  value: T;
  items: { key: T; label: string; sub?: string }[];
  onChange: (key: T) => void;
}) {
  return (
    <div className="seg">
      {items.map((item) => (
        <button key={item.key} className={value === item.key ? "on" : ""} onClick={() => onChange(item.key)}>
          {item.label}
          {item.sub && <span className="seg-sub">{item.sub}</span>}
        </button>
      ))}
    </div>
  );
}

export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div className="stack gap-10">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height: 44, opacity: 1 - i * 0.18 }} />
      ))}
    </div>
  );
}

export function Empty({ text = "暂无数据" }: { text?: string }) {
  return (
    <div className="muted" style={{ padding: "22px 0", textAlign: "center", fontSize: 13 }}>
      {text}
    </div>
  );
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="badge rose" style={{ whiteSpace: "normal", padding: "10px 12px", display: "block" }}>
      {message}
    </div>
  );
}

export function CopyButton({ text, label = "复制" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    setDone(true);
    window.setTimeout(() => setDone(false), 1500);
  }
  return (
    <button type="button" className="btn sm ghost" onClick={() => void copy()}>
      {done ? "已复制" : label}
    </button>
  );
}

const STATUS_TEXT: Record<string, string> = {
  pending: "待提交",
  submitted: "待审批",
  approved: "已批准",
  executed: "已执行",
  rejected: "已驳回",
  cancelled: "已取消",
  accepted: "已采纳",
  holdout: "观察组",
  running: "运行中",
  succeeded: "成功",
  failed: "失败",
  ok: "正常",
  confirmed: "已确认",
  invalid: "未通过",
  validated: "已校验",
};

export function StatusBadge({ value }: { value: string }) {
  const tone =
    value === "executed" || value === "succeeded" || value === "approved" || value === "accepted" || value === "confirmed" || value === "validated"
      ? "mint"
      : value === "failed" || value === "rejected" || value === "cancelled" || value === "invalid"
        ? "rose"
        : value === "submitted" || value === "running"
          ? "cyan"
          : "";
  return <span className={`badge ${tone}`}>{STATUS_TEXT[value] ?? value}</span>;
}

export function SeverityBadge({ value }: { value: string }) {
  const tone = value === "L3" ? "rose" : value === "L2" ? "amber" : "cyan";
  return <span className={`badge ${tone}`}>{value}</span>;
}

const ACTION_TEXT: Record<string, string> = {
  follow: "跟进降价",
  hold: "观察",
  adjust_coupon: "投券对冲",
  join_promo: "报名活动",
  no_action: "不动作",
};
export const actionText = (action: string) => ACTION_TEXT[action] ?? action;

const EVENT_TEXT: Record<string, string> = {
  price_drop: "价格下降",
  price_rise: "价格上涨",
  price_up: "价格上涨",
  price_down: "价格下降",
  band_breach: "击穿价格带",
  coupon_change: "券面变化",
  promotion_change: "活动变化",
  stock_signal: "库存信号",
  stock_change: "库存变化",
  title_change: "标题变化",
  image_change: "主图变化",
  data_gap: "数据缺口",
  low_confidence: "低置信",
};
export const eventText = (type: string) => EVENT_TEXT[type] ?? type;

export const ROLE_TEXT: Record<string, string> = {
  admin: "管理员",
  manager: "主管",
  member: "成员",
};
