import { useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import { Card, Empty, ErrorBox, Loader, Metric, PageHead } from "../components/ui";
import { useAsync } from "../hooks";
import type { MappingItem } from "../types";

export default function Mappings() {
  const { me } = useAuth();
  const canEdit = me?.role === "admin" || me?.role === "manager";
  const { data, error, loading, reload } = useAsync(async () => {
    const [pending, confirmed] = await Promise.all([
      api.get<MappingItem[]>("/api/mappings?status=pending"),
      api.get<MappingItem[]>("/api/mappings?status=confirmed"),
    ]);
    return { pending, confirmed };
  }, []);
  const [message, setMessage] = useState("");

  async function run(label: string, fn: () => Promise<unknown>) {
    setMessage("");
    try {
      await fn();
      await reload();
    } catch (err) {
      setMessage(`${label}失败：${err instanceof Error ? err.message : "未知错误"}`);
    }
  }

  function card(item: MappingItem, actionable: boolean) {
    return (
      <div className="card" key={item.id}>
        <div className="row">
          <b>{Math.round(item.score * 100)}</b>
          <span>{item.my_title || item.my_sku}</span>
          <span>→</span>
          <span>{item.target_title || item.target_id}</span>
        </div>
        <p className="hint">
          我方 {item.my_sku}
          {item.my_price ? ` · ${item.my_price} 元` : ""}
          {item.method ? ` · ${item.method}` : ""}
          {item.decided_by ? ` · 由 ${item.decided_by} 确认` : ""}
        </p>
        {actionable && canEdit && (
          <div className="row">
            <button
              className="btn small"
              onClick={() =>
                void run("确认", () =>
                  api.post(`/api/mappings/${item.id}/decide`, { decision: "confirmed" }),
                )
              }
            >
              确认对齐
            </button>
            <button
              className="btn ghost small"
              onClick={() =>
                void run("忽略", () =>
                  api.post(`/api/mappings/${item.id}/decide`, { decision: "rejected" }),
                )
              }
            >
              忽略
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <>
      <PageHead
        title="SKU 对齐"
        sub="竞品与我方 SKU 的对应关系，决定毛利率是否可比"
        actions={
          canEdit ? (
            <div className="row">
              <button
                className="btn ghost"
                onClick={() => void run("载入示例", () => api.post("/api/my-products/seed"))}
              >
                载入示例商品
              </button>
              <button
                className="btn"
                onClick={() =>
                  void run("生成建议", () => api.post("/api/mappings/suggest"))
                }
              >
                生成匹配建议
              </button>
            </div>
          ) : undefined
        }
      />
      {message && <div className="notice">{message}</div>}
      {error && <ErrorBox message={error} />}
      {loading && !data && <Loader />}

      {data && (
        <>
          <div className="metric-row">
            <Metric label="待确认" value={data.pending.length} sub="需要人工判断" />
            <Metric label="已对齐" value={data.confirmed.length} sub="可用于毛利比较" />
            <Metric label="合计" value={data.pending.length + data.confirmed.length} sub="全部映射" />
          </div>

          <Card title="待确认" sub="确认后才会参与毛利与价格带计算">
            {data.pending.length === 0 ? (
              <Empty>暂无待确认。先载入示例商品，再生成匹配建议。</Empty>
            ) : (
              data.pending.map((item) => card(item, true))
            )}
          </Card>

          <Card title="已对齐">
            {data.confirmed.length === 0 ? (
              <Empty>还没有已对齐的 SKU。</Empty>
            ) : (
              data.confirmed.map((item) => card(item, false))
            )}
          </Card>
        </>
      )}
    </>
  );
}
