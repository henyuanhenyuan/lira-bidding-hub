import { useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import { Card, Empty, ErrorBox, Loader, PageHead } from "../components/ui";
import { useAsync } from "../hooks";
import type { Target } from "../types";

export default function Targets() {
  const { me } = useAuth();
  const canEdit = me?.role === "admin" || me?.role === "manager";
  const { data, error, loading, reload } = useAsync(
    () => api.get<Target[]>("/api/targets"),
    [],
  );
  const [draft, setDraft] = useState<Record<string, { sku: string; price: string }>>({});
  const [saved, setSaved] = useState<string>("");
  const [message, setMessage] = useState("");

  function edit(target: Target, field: "sku" | "price", value: string) {
    setDraft((prev) => ({
      ...prev,
      [target.id]: {
        sku: field === "sku" ? value : prev[target.id]?.sku ?? target.my_sku ?? "",
        price:
          field === "price"
            ? value
            : prev[target.id]?.price ?? (target.my_price == null ? "" : String(target.my_price)),
      },
    }));
  }

  async function save(target: Target) {
    const current = draft[target.id];
    if (!current) return;
    const price = current.price.trim();
    setMessage("");
    try {
      await api.patch(`/api/targets/${encodeURIComponent(target.id)}`, {
        my_sku: current.sku.trim() || null,
        my_price: price === "" ? null : Number(price),
      });
      setSaved(target.id);
      setTimeout(() => setSaved(""), 1200);
      await reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "保存失败");
    }
  }

  return (
    <>
      <PageHead
        title="竞品目标"
        sub="维护我方 SKU、我方价格，用于毛利护栏与价格带判断"
      />
      {message && <div className="notice">{message}</div>}
      {error && <ErrorBox message={error} />}
      {loading && !data && <Loader />}

      <Card title="目标列表" sub="修改后点击保存；留空表示未知">
        {data && data.length === 0 && <Empty>还没有竞品目标。</Empty>}
        {data && data.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>竞品</th>
                  <th>平台</th>
                  <th>我方 SKU</th>
                  <th>我方价格</th>
                  <th>状态</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.map((target) => {
                  const current = draft[target.id] ?? {
                    sku: target.my_sku ?? "",
                    price: target.my_price == null ? "" : String(target.my_price),
                  };
                  return (
                    <tr key={target.id}>
                      <td>{target.title}</td>
                      <td>{target.platform}</td>
                      <td>
                        <input
                          className="input"
                          value={current.sku}
                          disabled={!canEdit}
                          onChange={(event) => edit(target, "sku", event.target.value)}
                        />
                      </td>
                      <td>
                        <input
                          className="input"
                          value={current.price}
                          disabled={!canEdit}
                          inputMode="decimal"
                          onChange={(event) => edit(target, "price", event.target.value)}
                        />
                      </td>
                      <td>{target.mapping_status}</td>
                      <td>
                        {canEdit && (
                          <button className="btn small" onClick={() => void save(target)}>
                            {saved === target.id ? "已保存" : "保存"}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
