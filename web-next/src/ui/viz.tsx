import type { ReactNode } from "react";

const LABEL = "#7f90ae";
const GRID = "rgba(120,170,255,.14)";

const SEV_COLOR: Record<string, string> = {
  L3: "#fb7185",
  L2: "#fbbf24",
  L1: "#22d3ee",
};

function color(severity?: string | null): string {
  return (severity && SEV_COLOR[severity]) || "#38bdf8";
}

export interface MarketPoint {
  id: string;
  title: string;
  mine: number | null;
  theirs: number | null;
  delta: number | null;
  severity?: string | null;
}

export function PipelineFlow({
  steps,
  active,
}: {
  steps: { key: string; label: string }[];
  active?: string;
}) {
  return (
    <div className="pipeline">
      {steps.map((step, index) => (
        <div className={`pipe-node${step.key === active ? " on" : ""}`} key={step.key}>
          <span className="pipe-dot">{index + 1}</span>
          <em>{step.label}</em>
          {index < steps.length - 1 && <i className="pipe-link" />}
        </div>
      ))}
    </div>
  );
}

export function Ticker({ items }: { items: ReactNode[] }) {
  if (items.length === 0) return null;
  return (
    <div className="ticker">
      <div className="ticker-track">
        {[0, 1].map((copy) => (
          <div className="ticker-set" key={copy}>
            {items.map((item, index) => (
              <span className="ticker-item" key={`${copy}-${index}`}>
                {item}
              </span>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}


export interface ShelfItem {
  id: string;
  title: string;
  mine: number | null;
  theirs: number | null;
  delta: number | null;
  severity?: string | null;
}

/** 商品货架：按价格陈列竞品，像货架上的商品；颜色是严重度。 */
export function ProductShelf({ items, rows = 2 }: { items: ShelfItem[]; rows?: number }) {
  const valid = items.filter((item) => item.theirs);
  if (valid.length === 0) return <div className="chart-empty">还没有竞品数据</div>;

  const myPrice = items.find((item) => item.mine)?.mine ?? null;
  const prices = valid.map((item) => item.theirs as number);
  if (myPrice != null) prices.push(myPrice);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const span = max - min || 1;
  const perRow = Math.max(3, Math.min(6, Math.ceil(valid.length / Math.max(1, rows))));
  const shelves: ShelfItem[][] = [];
  for (let index = 0; index < valid.length; index += perRow) {
    shelves.push(valid.slice(index, index + perRow));
  }

  return (
    <div className="shelf2">
      {shelves.map((row, rowIndex) => (
        <div className="shelf-row" key={rowIndex}>
          <div className="shelf-items">
            {row.map((item) => {
              const norm = ((item.theirs as number) - min) / span;
              const height = 72 + norm * 52;
              const tone = color(item.severity);
              const below = myPrice != null && (item.theirs as number) < myPrice;
              return (
                <div
                  className={`shelf-product${below ? " below" : ""}`}
                  key={item.id}
                  style={{ height, ["--tone" as string]: tone }}
                  title={`${item.title} · 竞品 ¥${item.theirs} · 我方 ¥${item.mine ?? "—"}`}
                >
                  <span className="sp-art" />
                  <span className="sp-sticker">{item.severity ?? "L1"}</span>
                  <span className="sp-label">
                    <b>¥{item.theirs}</b>
                    <em>{item.title.length > 6 ? `${item.title.slice(0, 6)}…` : item.title}</em>
                  </span>
                </div>
              );
            })}
          </div>
          <div className="shelf-plank" />
        </div>
      ))}
      {myPrice != null && (
        <div className="shelf-mark">我方价 ¥{myPrice}</div>
      )}
    </div>
  );
}


export interface ShelfEntry {
  id: string;
  title: string;
  value: number;
  label: string;
  tone?: string;
}

/** 通用货架：文档、工具等也按商品陈列。 */
export function ItemShelf({ items, maxValue }: { items: ShelfEntry[]; maxValue?: number }) {
  if (items.length === 0) return <div className="chart-empty">暂无内容</div>;
  const ceiling = maxValue ?? Math.max(...items.map((item) => item.value), 1);
  const perRow = 6;
  const shelves: ShelfEntry[][] = [];
  for (let index = 0; index < items.length; index += perRow) {
    shelves.push(items.slice(index, index + perRow));
  }
  return (
    <div className="shelf2">
      {shelves.map((row, rowIndex) => (
        <div className="shelf-row" key={rowIndex}>
          <div className="shelf-items">
            {row.map((item) => {
              const height = 64 + (item.value / ceiling) * 56;
              return (
                <div
                  className="shelf-product"
                  key={item.id}
                  style={{ height, ["--tone" as string]: item.tone ?? "#22d3ee" }}
                  title={`${item.title} · ${item.label}`}
                >
                  <span className="sp-art" />
                  <span className="sp-sticker">{item.label}</span>
                  <span className="sp-label">
                    <b>{item.title.length > 10 ? `${item.title.slice(0, 10)}…` : item.title}</b>
                    <em>{item.value}</em>
                  </span>
                </div>
              );
            })}
          </div>
          <div className="shelf-plank" />
        </div>
      ))}
    </div>
  );
}


/** 自动贩卖机：把货架装进玻璃柜，用于实时大屏。 */
export function VendingMachine({
  items,
  myPrice,
}: {
  items: ShelfItem[];
  myPrice: number | null;
}) {
  const count = items.filter((item) => item.theirs).length;
  return (
    <div className="vending">
      <div className="vending-head">
        <span className="vending-brand">LIRA MART</span>
        <em>实时竞价 · {count} 件在售</em>
      </div>
      <div className="vending-glass">
        <span className="glass-shine" />
        <ProductShelf items={items} rows={3} />
      </div>
      <div className="vending-foot">
        <span className="vending-slot" />
        <span className="vending-price">我方价 ¥{myPrice ?? "—"}</span>
        <span className="vending-key" />
        <span className="vending-key" />
      </div>
    </div>
  );
}


/** 轻量货柜：把任意货架装进玻璃柜，B 端各页共用。 */
export function Cabinet({
  title,
  tag,
  children,
}: {
  title: string;
  tag?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="vending cabinet">
      <div className="vending-head">
        <span className="vending-brand">{title}</span>
        {tag && <em>{tag}</em>}
      </div>
      <div className="vending-glass">
        <span className="glass-shine" />
        {children}
      </div>
    </div>
  );
}
