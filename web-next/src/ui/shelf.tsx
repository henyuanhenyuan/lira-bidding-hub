import type { CSSProperties } from "react";

export interface ShelfItem {
  id: string;
  title: string;
  mine: number | null;
  theirs: number | null;
  delta: number | null;
  severity?: string | null;
}

const TONE: Record<string, string> = {
  L3: "#ff7a9c",
  L2: "#ffc46b",
  L1: "#5be1ff",
};

const BAG_COLORS = [
  "#5be1ff", "#ffc46b", "#ff7a9c", "#9b7bff", "#4ef2c0",
  "#60a5fa", "#f472b6", "#a3e635", "#fb923c", "#22d3ee",
];

function rowsOf<T>(items: T[], perRow: number): T[][] {
  const rows: T[][] = [];
  for (let index = 0; index < items.length; index += perRow) {
    rows.push(items.slice(index, index + perRow));
  }
  return rows;
}

function short(value: string, size = 7) {
  return value.length > size ? `${value.slice(0, size)}…` : value;
}

/** 商品货架：唯一保留的“小卖铺”元素，其余全部照搬 lirav1 设计。 */
export default function Shelf({
  items,
  myPrice,
  selectedId,
  onSelect,
  perRow = 6,
}: {
  items: ShelfItem[];
  myPrice: number | null;
  selectedId?: string;
  onSelect?: (id: string) => void;
  perRow?: number;
}) {
  const valid = items.filter((item) => item.theirs != null);
  const rows = rowsOf(valid, perRow);

  return (
    <div className="shelf">
      <div className="shelf-head">
        <span className="shelf-title">
          <i />
          LIRA MART · 竞品货架
        </span>
        <div className="shelf-head-right">
          {myPrice != null && (
            <span className="shelf-head-price">
              <em>我方价</em>
              <b>¥{myPrice}</b>
            </span>
          )}
          <span className="badge cyan">{valid.length} 件</span>
        </div>
      </div>
      <div className="shelf-body">
        {rows.length === 0 ? (
          <div className="shelf-empty">货架空置，等待接入竞品数据</div>
        ) : (
          rows.map((row, rowIndex) => (
            <div className="shelf-row" key={rowIndex}>
              <div className="shelf-items">
                {row.map((item, index) => {
                  const globalIndex = rowIndex * perRow + index;
                  const tone = BAG_COLORS[globalIndex % BAG_COLORS.length];
                  const below = item.mine != null && (item.theirs as number) < item.mine;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      className={`shelf-product${item.id === selectedId ? " active" : ""}${below ? " below" : ""}`}
                      style={{ "--tone": tone } as CSSProperties}
                      onClick={() => onSelect?.(item.id)}
                      title={`${item.title} · 竞品 ¥${item.theirs ?? "—"} · 我方 ¥${item.mine ?? "—"}`}
                    >
                      <span className="sp-body">
                        <span className="sp-smile" />
                        <span className="sp-badge">{item.severity ?? "L1"}</span>
                        <span className="sp-price">¥{item.theirs ?? "—"}</span>
                      </span>
                      <span className="sp-label">
                        <b>{short(item.title, 10)}</b>
                        <span>{item.mine == null ? "未映射" : below ? "低于我方" : "高于我方"}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
              <div className="shelf-plank" />
            </div>
          ))
        )}
        <div className="shelf-foot">
          <span className="shelf-slot" />
          <span className="muted" style={{ fontSize: 10 }}>{valid.length} 件在售 · 自动贩卖机</span>
          <span className="shelf-key" />
          <span className="shelf-key" />
        </div>
      </div>
    </div>
  );
}
