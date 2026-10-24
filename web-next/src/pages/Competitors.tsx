import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { Empty, ErrorBox, Loader, PageHead } from "../components/ui";
import { money } from "../format";
import { useAsync } from "../hooks";
import type { Target } from "../types";

function TargetRow({ target, onChange }: { target: Target; onChange: () => void }) {
  const [sku, setSku] = useState(target.my_sku ?? "");
  const [price, setPrice] = useState(target.my_price?.toString() ?? "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await api.patch(`/api/targets/${encodeURIComponent(target.id)}`, {
        my_sku: sku.trim() || null,
        my_price: price.trim() === "" ? null : Number(price),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 1200);
      onChange();
    } finally {
      setSaving(false);
    }
  }

  return (
    <tr>
      <td>
        <Link className="strong-link" to={`/competitors/${target.id}`}>
          {target.title}
        </Link>
        <span className="sub">
          {target.platform} · {target.id}
        </span>
      </td>
      <td>
        <input
          className="input"
          value={sku}
          placeholder="SKU"
          onChange={(event) => setSku(event.target.value)}
        />
      </td>
      <td>
        <input
          className="input narrow"
          inputMode="decimal"
          value={price}
          placeholder="价格"
          onChange={(event) => setPrice(event.target.value)}
        />
      </td>
      <td>{target.active ? "启用" : "停用"}</td>
      <td>
        <button className="btn small" disabled={saving} onClick={() => void save()}>
          {saved ? "已保存" : "保存"}
        </button>
      </td>
    </tr>
  );
}

export default function Competitors() {
  const { data, error, loading, reload } = useAsync(
    () => api.get<Target[]>("/api/targets"),
    [],
  );

  return (
    <>
      <PageHead
        title="竞品"
        sub="竞品与 SKU 的对应关系在这里确认；对齐后价格带击穿才会生效"
        actions={
          <button className="btn ghost" onClick={() => void reload()}>
            刷新
          </button>
        }
      />

      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !data && <Loader />}
      {data && data.length === 0 && <Empty>还没有监控目标。先导入采集数据。</Empty>}

      {data && data.length > 0 && (
        <div className="table-wrap card">
          <table className="table">
            <thead>
              <tr>
                <th>竞品</th>
                <th>我方 SKU</th>
                <th>我方价</th>
                <th>状态</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.map((target) => (
                <TargetRow key={target.id} target={target} onChange={reload} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
