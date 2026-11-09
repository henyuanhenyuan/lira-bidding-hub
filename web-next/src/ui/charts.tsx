import type { ReactNode } from "react";

export type Tone = "cyan" | "violet" | "mint" | "amber" | "rose" | "slate";

const TONE: Record<Tone, string> = {
  cyan: "#5be1ff",
  violet: "#9b7bff",
  mint: "#4ef2c0",
  amber: "#ffc46b",
  rose: "#ff7a9c",
  slate: "#93a1c0",
};

/** 价格带：竞品低/高到手价区间。 */
export function PriceBand({
  points,
  mine,
  tone = "cyan",
}: {
  points: { ts: string; price_low: number; price_high: number }[];
  mine?: number | null;
  tone?: Tone;
}) {
  if (points.length === 0) return <ChartEmpty>暂无价格历史</ChartEmpty>;
  const width = 560;
  const height = 190;
  const pad = { top: 18, right: 18, bottom: 28, left: 42 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const values = points.flatMap((item) => [item.price_low, item.price_high]);
  if (mine != null) values.push(mine);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x = (index: number) =>
    pad.left + (points.length === 1 ? innerW / 2 : (index / (points.length - 1)) * innerW);
  const y = (value: number) => pad.top + innerH - ((value - min) / span) * innerH;
  const lows = points.map((item, index) => `${x(index).toFixed(1)},${y(item.price_low).toFixed(1)}`);
  const highs = [...points].reverse().map((item, index) => {
    const real = points.length - 1 - index;
    return `${x(real).toFixed(1)},${y(item.price_high).toFixed(1)}`;
  });
  const mid = points
    .map((item, index) => `${x(index).toFixed(1)},${y((item.price_low + item.price_high) / 2).toFixed(1)}`)
    .join(" ");
  return (
    <svg className="chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="价格带">
      <defs>
        <linearGradient id="band-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={TONE[tone]} stopOpacity="0.3" />
          <stop offset="100%" stopColor={TONE[tone]} stopOpacity="0.03" />
        </linearGradient>
      </defs>
      {[0, 0.5, 1].map((ratio) => (
        <line
          key={ratio}
          x1={pad.left}
          x2={pad.left + innerW}
          y1={pad.top + innerH * ratio}
          y2={pad.top + innerH * ratio}
          stroke="rgba(255,255,255,.07)"
          strokeDasharray="3 6"
        />
      ))}
      <polygon points={[...lows, ...highs].join(" ")} fill="url(#band-fill)" />
      <polyline points={mid} fill="none" stroke={TONE[tone]} strokeWidth="2.4" strokeLinecap="round" />
      {points.map((item, index) => (
        <circle
          key={item.ts}
          cx={x(index)}
          cy={y((item.price_low + item.price_high) / 2)}
          r="3.2"
          fill="#04060e"
          stroke={TONE[tone]}
          strokeWidth="2"
        >
          <title>{`${item.ts} · ¥${item.price_low}–${item.price_high}`}</title>
        </circle>
      ))}
      {mine != null && mine >= min && mine <= max && (
        <>
          <line
            x1={pad.left}
            x2={pad.left + innerW}
            y1={y(mine)}
            y2={y(mine)}
            stroke="#ff7a9c"
            strokeWidth="1.6"
            strokeDasharray="6 5"
          />
          <text x={pad.left + 6} y={y(mine) - 6} className="chart-axis" fill="#ff9ab4">
            我方 ¥{mine}
          </text>
        </>
      )}
      <text x={8} y={y(max) + 4} className="chart-axis">{Math.round(max)}</text>
      <text x={8} y={y(min) + 4} className="chart-axis">{Math.round(min)}</text>
      <text x={pad.left} y={height - 8} className="chart-axis">{points[0]?.ts?.slice(5, 10)}</text>
      <text x={pad.left + innerW} y={height - 8} className="chart-axis" textAnchor="end">
        {points[points.length - 1]?.ts?.slice(5, 10)}
      </text>
    </svg>
  );
}

export function ChartEmpty({ children }: { children: ReactNode }) {
  return <div className="chart-empty">{children}</div>;
}

/** 柱状趋势：事件数 / 调用量等按日计数。 */
export function TrendBars({
  data,
  tone = "cyan",
  height = 120,
}: {
  data: { label: string; value: number }[];
  tone?: Tone;
  height?: number;
}) {
  if (data.length === 0) return <div className="sc-empty">暂无趋势数据</div>;
  const width = 480;
  const pad = { top: 8, right: 6, bottom: 16, left: 6 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const max = Math.max(1, ...data.map((item) => item.value));
  const slot = innerW / data.length;
  const barW = Math.max(2, slot * 0.55);
  return (
    <div className="trend-bars">
      <svg
        className="chart-svg"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        role="img"
        aria-label="趋势"
      >
        {[0, 0.5, 1].map((ratio) => (
          <line
            key={ratio}
            className="chart-grid-line"
            x1={pad.left}
            x2={pad.left + innerW}
            y1={pad.top + innerH * ratio}
            y2={pad.top + innerH * ratio}
          />
        ))}
        {data.map((item, index) => {
          const bar = (item.value / max) * innerH;
          const x = pad.left + slot * index + (slot - barW) / 2;
          const y = pad.top + innerH - bar;
          return (
            <rect
              key={item.label + index}
              className="chart-bar"
              x={x}
              y={y}
              width={barW}
              height={Math.max(1.5, bar)}
              rx={2}
              fill={TONE[tone]}
              opacity={0.82}
            >
              <title>{`${item.label} · ${item.value}`}</title>
            </rect>
          );
        })}
      </svg>
      <div className="trend-labels">
        <span>{data[0]?.label}</span>
        <span>{data[Math.floor(data.length / 2)]?.label}</span>
        <span>{data[data.length - 1]?.label}</span>
      </div>
    </div>
  );
}

/** 环形分布：严重度 / 状态。compact 用于大屏。 */
export function Donut({
  segments,
  center,
  unit = "总计",
  compact = false,
}: {
  segments: { label: string; value: number; tone: Tone }[];
  center?: string | number;
  unit?: string;
  compact?: boolean;
}) {
  const total = segments.reduce((sum, item) => sum + item.value, 0);
  const radius = 40;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  return (
    <div className={compact ? "sc-donut" : "donut"}>
      <svg viewBox="0 0 100 100" role="img" aria-label="分布">
        <circle cx="50" cy="50" r={radius} fill="none" stroke="rgba(255,255,255,.06)" strokeWidth="12" />
        {total > 0 &&
          segments.map((item) => {
            const length = (item.value / total) * circumference;
            const node = (
              <circle
                key={item.label}
                cx="50"
                cy="50"
                r={radius}
                fill="none"
                stroke={TONE[item.tone]}
                strokeWidth="12"
                strokeDasharray={`${Math.max(0, length - 1.5)} ${circumference}`}
                strokeDashoffset={-offset}
                transform="rotate(-90 50 50)"
              >
                <title>{`${item.label} · ${item.value}`}</title>
              </circle>
            );
            offset += length;
            return node;
          })}
      </svg>
      <div className="donut-center">
        <b>{center ?? total}</b>
        <em>{unit}</em>
      </div>
      <ul className={compact ? "sc-legend" : "donut-legend"}>
        {segments.map((item) => (
          <li key={item.label}>
            <i style={{ background: TONE[item.tone] }} />
            {item.label}
            <b>{item.value}</b>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** 价差分布：竞品相对我方的偏离，左右分向。 */
export function SpreadBars({ rows }: { rows: { label: string; value: number }[] }) {
  if (rows.length === 0) return <div className="sc-empty">暂无可比价差</div>;
  const max = Math.max(0.0001, ...rows.map((row) => Math.abs(row.value)));
  return (
    <ul className="sc-diverge">
      {rows.map((row) => {
        const low = row.value < 0;
        const width = (Math.abs(row.value) / max) * 50;
        return (
          <li key={row.label}>
            <span className="name" title={row.label}>{row.label}</span>
            <span className="track">
              <i className="zero" />
              <i
                className={`bar ${low ? "low" : "high"}`}
                style={{ left: low ? `${50 - width}%` : "50%", width: `${width}%` }}
              />
            </span>
            <b className={low ? "low" : "high"}>
              {low ? "" : "+"}
              {(row.value * 100).toFixed(1)}%
            </b>
          </li>
        );
      })}
    </ul>
  );
}
