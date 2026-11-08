import { useState } from "react";

import { api } from "../core/api";
import { canManage, useAuth } from "../core/auth";
import { money } from "../core/format";
import { useAsync } from "../core/hooks";
import { Badge, Card, Empty, ErrorBox, Page, Spinner, Table } from "../ui/kit";

interface Target {
  id: string;
  platform: string;
  title: string;
  my_sku: string | null;
  my_price: number | null;
  active: number;
  mapping_status: string;
  holdout: number;
}

export default function Targets() {
  const { me } = useAuth();
  const editable = canManage(me);
  const { data, error, loading, reload } = useAsync(
    () => api.get<Target[]>("/api/targets"),
    [],
  );
  const [draft, setDraft] = useState<Record<string, { sku: string; price: string }>>({});
  const [saved, setSaved] = useState("");
  const [message, setMessage] = useState("");

  function get(target: Target, field: "sku" | "price"): string {
    const entry = draft[target.id];
    if (entry) return entry[field];
    return field === "sku" ? target.my_sku ?? "" : target.my_price == null ? "" : String(target.my_price);
  }

  function edit(target: Target, field: "sku" | "price", value: string) {
    setDraft((prev) => ({
      ...prev,
      [target.id]: {
        sku: field === "sku" ? value : get(target, "sku"),
        price: field === "price" ? value : get(target, "price"),
      },
    }));
  }

  async function save(target: Target) {
    const price = get(target, "price").trim();
    setMessage("");
    try {
      await api.patch(`/api/targets/${encodeURIComponent(target.id)}`, {
        my_sku: get(target, "sku").trim() || null,
        my_price: price === "" ? null : Number(price),
      });
      setSaved(target.id);
      window.setTimeout(() => setSaved(""), 1400);
      setDraft((prev) => {
        const next = { ...prev };
        delete next[target.id];
        return next;
      });
      await reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "保存失败");
    }
  }

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  return (
    <Page title="竞品目标" desc="维护我方 SKU 与价格，用于毛利护栏和价格带判断">
      {message && <div className="notice">{message}</div>}

      <Card flush>
        {data.length === 0 ? (
          <Empty>还没有竞品目标。</Empty>
        ) : (
          <Table head={["竞品", "平台", "我方 SKU", "我方价", "映射", "操作"]}>
            {data.map((target) => (
              <tr key={target.id}>
                <td>
                  <b>{target.title}</b>
                  <div className="sub mono">{target.id}</div>
                </td>
                <td>{target.platform}</td>
                <td>
                  <input
                    className="input"
                    value={get(target, "sku")}
                    disabled={!editable}
                    onChange={(event) => edit(target, "sku", event.target.value)}
                  />
                </td>
                <td>
                  <input
                    className="input"
                    style={{ width: 110 }}
                    value={get(target, "price")}
                    disabled={!editable}
                    onChange={(event) => edit(target, "price", event.target.value)}
                  />
                  <div className="sub">{money(target.my_price)}</div>
                </td>
                <td>
                  <Badge tone={target.mapping_status === "confirmed" ? "ok" : "neutral"}>
                    {target.mapping_status}
                  </Badge>
                </td>
                <td>
                  {editable && (
                    <button className="btn sm" onClick={() => void save(target)}>
                      {saved === target.id ? "已保存" : "保存"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </Page>
  );
}
