import { useId } from "react";

export function Spark({
  values,
  height = 44,
  tone = "cyan",
  fill = true,
}: {
  values: number[];
  height?: number;
  tone?: "cyan" | "violet" | "amber" | "rose" | "green";
  fill?: boolean;
}) {
  const id = useId().replace(/:/g, "");
  const data = values.length ? values : [0, 0];
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const span = max - min || 1;
  const w = 100;
  const h = height;
  const step = data.length > 1 ? w / (data.length - 1) : w;
  const pts = data.map((v, i) => [i * step, h - ((v - min) / span) * (h - 6) - 3]);
  const line = pts
    .map(([x, y], i) => {
      if (i === 0) return `M ${x.toFixed(2)} ${y.toFixed(2)}`;
      const [px, py] = pts[i - 1];
      const cx = (px + x) / 2;
      return `C ${cx.toFixed(2)} ${py.toFixed(2)}, ${cx.toFixed(2)} ${y.toFixed(2)}, ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
  const area = `${line} L ${w} ${h} L 0 ${h} Z`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className={`spark ${tone}`} aria-hidden="true">
      <defs>
        <linearGradient id={`g${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.22" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      {fill && <path d={area} fill={`url(#g${id})`} />}
      <path d={line} fill="none" stroke="currentColor" strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="1.8" fill="currentColor" />
    </svg>
  );
}

export function Gauge({
  value,
  label,
  sub,
  tone = "cyan",
}: {
  value: number;
  label: string;
  sub?: string;
  tone?: "cyan" | "violet" | "amber" | "rose" | "green";
}) {
  const clamped = Math.max(0, Math.min(1, value));
  const r = 42;
  const c = Math.PI * r;
  const dash = c * clamped;
  return (
    <div className={`gauge ${tone}`}>
      <svg viewBox="0 0 110 62" aria-hidden="true">
        <path d="M 13 55 A 42 42 0 0 1 97 55" fill="none" stroke="rgba(255,255,255,.09)" strokeWidth="7" strokeLinecap="round" />
        <path
          d="M 13 55 A 42 42 0 0 1 97 55"
          fill="none"
          stroke="currentColor"
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${c}`}
        />
      </svg>
      <div className="gauge-body">
        <strong className="num">{label}</strong>
        {sub && <span>{sub}</span>}
      </div>
    </div>
  );
}

export function Ring({
  value,
  size = 54,
  tone = "cyan",
  children,
}: {
  value: number;
  size?: number;
  tone?: "cyan" | "violet" | "amber" | "rose" | "green";
  children?: React.ReactNode;
}) {
  const clamped = Math.max(0, Math.min(1, value));
  const r = size / 2 - 4;
  const c = 2 * Math.PI * r;
  return (
    <div className={`ring ${tone}`} style={{ width: size, height: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,.08)" strokeWidth="4" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={`${c * clamped} ${c}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="ring-body">{children}</div>
    </div>
  );
}

export function PriceLadder({
  myPrice,
  low,
  high,
  severity,
}: {
  myPrice: number | null;
  low: number | null;
  high: number | null;
  severity?: string | null;
}) {
  const vals = [myPrice, low, high].filter((v): v is number => typeof v === "number");
  if (!vals.length) return <div className="ladder empty-ladder" />;
  const max = Math.max(...vals) * 1.15;
  const min = Math.min(...vals) * 0.85;
  const span = max - min || 1;
  const pos = (v: number) => ((v - min) / span) * 100;
  const gap = myPrice !== null && low !== null && high !== null ? low - myPrice : null;
  const tone = severity === "L3" ? "rose" : severity === "L2" ? "amber" : "cyan";
  return (
    <div className={`ladder ${tone}`}>
      <div className="ladder-track" />
      {low !== null && high !== null && (
        <div
          className="ladder-band"
          style={{ left: `${pos(Math.min(low, high))}%`, width: `${Math.abs(pos(high) - pos(low))}%` }}
        />
      )}
      {myPrice !== null && (
        <div className="ladder-mine" style={{ left: `${pos(myPrice)}%` }}>
          <span className="ladder-pin" />
          <span className="ladder-tag num">¥{myPrice.toFixed(0)}</span>
        </div>
      )}
      {gap !== null && (
        <span className={`ladder-gap ${gap < 0 ? "down" : "up"}`}>
          {gap < 0 ? "低" : "高"} ¥{Math.abs(gap).toFixed(0)}
        </span>
      )}
    </div>
  );
}

export function Bars({
  items,
  max,
  tone = "cyan",
}: {
  items: { label: string; value: number }[];
  max?: number;
  tone?: "cyan" | "violet" | "amber" | "rose" | "green";
}) {
  const peak = max ?? Math.max(...items.map((i) => i.value), 1);
  return (
    <div className={`bars ${tone}`}>
      {items.map((item) => (
        <div className="bar-row" key={item.label}>
          <span className="bar-label">{item.label}</span>
          <span className="bar-track">
            <span className="bar-fill" style={{ width: `${(item.value / peak) * 100}%` }} />
          </span>
          <span className="bar-value num">{item.value}</span>
        </div>
      ))}
    </div>
  );
}

export function FlowTopology({ active = false }: { active?: boolean }) {
  const nodes = [
    { key: "steward", label: "调度", tone: "cyan" },
    { key: "planning", label: "规划", tone: "cyan" },
    { key: "tools", label: "工具", tone: "violet" },
    { key: "analyst", label: "研判", tone: "violet" },
    { key: "risk", label: "风控", tone: "amber" },
    { key: "verification", label: "校验", tone: "amber" },
    { key: "writer", label: "输出", tone: "green" },
  ];
  return (
    <div className={`flow ${active ? "active" : ""}`}>
      {nodes.map((node, i) => (
        <div className="flow-node-wrap" key={node.key}>
          <div className={`flow-node tone-${node.tone}`}>
            <span className="flow-dot" />
            <span className="flow-label">{node.label}</span>
          </div>
          {i < nodes.length - 1 && <span className="flow-link" />}
        </div>
      ))}
    </div>
  );
}

export function RegionMosaic({
  regions,
  active,
  onPick,
}: {
  regions: { region: string; targets: number; avg_price?: number | null }[];
  active?: string;
  onPick?: (region: string) => void;
}) {
  const peak = Math.max(...regions.map((r) => r.targets || 0), 1);
  return (
    <div className="mosaic">
      {regions.map((r) => (
        <button
          type="button"
          key={r.region}
          className={`mosaic-tile ${active === r.region ? "active" : ""}`}
          onClick={() => onPick?.(r.region)}
        >
          <span className="mosaic-glow" style={{ opacity: 0.24 + (r.targets / peak) * 0.5 }} />
          <span className="mosaic-name">{r.region}</span>
          <span className="mosaic-count num">{r.targets}</span>
          <span className="mosaic-sub num">
            {typeof r.avg_price === "number" ? `均价 ¥${r.avg_price.toFixed(0)}` : "在盯目标"}
          </span>
        </button>
      ))}
    </div>
  );
}
