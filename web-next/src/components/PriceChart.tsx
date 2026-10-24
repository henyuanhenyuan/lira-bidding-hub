import { formatTs } from "../format";
import type { PricePoint } from "../types";

export default function PriceChart({
  points,
  myPrice,
  height = 220,
}: {
  points: PricePoint[];
  myPrice?: number | null;
  height?: number;
}) {
  if (!points.length) {
    return <div className="empty">暂无价格序列</div>;
  }

  const list = [...points].sort(
    (a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime(),
  );
  const width = 760;
  const pad = { left: 52, right: 18, top: 18, bottom: 30 };
  const values = list.flatMap((p) => [p.price_low, p.price_high]);
  if (myPrice) values.push(myPrice);
  const min = Math.min(...values) * 0.97;
  const max = Math.max(...values) * 1.03 || 1;

  const x = (i: number) =>
    pad.left +
    (i * (width - pad.left - pad.right)) / Math.max(1, list.length - 1);
  const y = (value: number) =>
    height -
    pad.bottom -
    ((value - min) / (max - min || 1)) * (height - pad.top - pad.bottom);

  const band =
    list.map((p, i) => `${x(i)},${y(p.price_high)}`).join(" ") +
    " " +
    [...list]
      .reverse()
      .map((p, i) => `${x(list.length - 1 - i)},${y(p.price_low)}`)
      .join(" ");
  const line = list
    .map((p, i) => `${x(i)},${y((p.price_low + p.price_high) / 2)}`)
    .join(" ");

  const ticks = [min, (min + max) / 2, max];

  return (
    <svg
      className="price-chart"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="竞品到手价区间"
    >
      {ticks.map((tick, i) => (
        <g key={i}>
          <line
            x1={pad.left}
            x2={width - pad.right}
            y1={y(tick)}
            y2={y(tick)}
            className="chart-grid"
          />
          <text x={8} y={y(tick) + 4} className="chart-label">
            {tick.toFixed(0)}
          </text>
        </g>
      ))}
      <polygon points={band} className="chart-band" />
      <polyline points={line} className="chart-line" />
      {myPrice ? (
        <>
          <line
            x1={pad.left}
            x2={width - pad.right}
            y1={y(myPrice)}
            y2={y(myPrice)}
            className="chart-mine"
          />
          <text
            x={width - pad.right}
            y={y(myPrice) - 6}
            textAnchor="end"
            className="chart-label mine"
          >
            我方 ¥{myPrice.toFixed(2)}
          </text>
        </>
      ) : null}
      {list.map((p, i) => (
        <circle
          key={p.ts}
          cx={x(i)}
          cy={y((p.price_low + p.price_high) / 2)}
          r={2.6}
          className="chart-dot"
        >
          <title>
            {formatTs(p.ts)} · ¥{p.price_low.toFixed(2)}–{p.price_high.toFixed(2)}
          </title>
        </circle>
      ))}
      <text x={pad.left} y={height - 8} className="chart-label">
        {formatTs(list[0].ts)}
      </text>
      <text
        x={width - pad.right}
        y={height - 8}
        textAnchor="end"
        className="chart-label"
      >
        {formatTs(list[list.length - 1].ts)}
      </text>
    </svg>
  );
}
