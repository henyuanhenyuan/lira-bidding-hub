import { useState, type FormEvent } from "react";

import { api, query } from "../api";
import { Card, Empty, ErrorBox, Loader, PageHead } from "../components/ui";
import { formatTs } from "../format";
import { useAsync } from "../hooks";
import type { CaseItem } from "../types";

export default function Cases() {
  const [draft, setDraft] = useState("");
  const [term, setTerm] = useState("");

  const { data, error, loading, reload } = useAsync(
    () =>
      term
        ? api.get<CaseItem[]>(`/api/cases/search${query({ query: term, limit: 20 })}`)
        : api.get<CaseItem[]>("/api/cases?limit=100"),
    [term],
  );

  function search(event: FormEvent) {
    event.preventDefault();
    setTerm(draft.trim());
  }

  async function seed() {
    await api.post("/api/cases/seed");
    await reload();
  }

  return (
    <>
      <PageHead
        title="案例库"
        sub="历史归因与 7 日结果，检索后会进入下一次研判的证据链"
        actions={
          <button className="btn ghost" onClick={() => void seed()}>
            载入示例案例
          </button>
        }
      />

      <Card title="检索" sub="向量召回 + 关键词召回 + 重排">
        <form className="search-row" onSubmit={search}>
          <input
            className="input"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="例如：大促前降价、价格带击穿、直播专享价"
          />
          <button className="btn" type="submit">
            检索
          </button>
          {term && (
            <button
              className="btn ghost"
              type="button"
              onClick={() => {
                setDraft("");
                setTerm("");
              }}
            >
              清空
            </button>
          )}
        </form>
        <p className="hint">
          {term ? `检索「${term}」` : "显示全部案例"} · {data?.length ?? 0} 条
        </p>
      </Card>

      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !data && <Loader />}
      {data && data.length === 0 && (
        <Empty>{term ? "没有检索到相似案例" : "案例库为空，先载入示例案例或等待结果回收。"}</Empty>
      )}

      <div className="case-grid">
        {data?.map((item) => (
          <article className="card case-card" key={item.id}>
            <div className="case-head">
              <span className="badge gate-confirm">{item.event_type}</span>
              <span className="hint">
                {item.category} · {item.price_band}
              </span>
              {item.embed_provider && <span className="hint">{item.embed_provider}</span>}
            </div>
            <h3>{item.summary}</h3>
            <p>归因：{item.attribution}</p>
            {item.outcome_7d && <p className="ok-text">7 日结果：{item.outcome_7d}</p>}
            <div className="case-foot">
              <code className="evidence">case:{item.id}</code>
              {item.decision && <span className="hint">当时决策：{item.decision}</span>}
              {item.ts && <span className="hint">{formatTs(item.ts)}</span>}
            </div>
          </article>
        ))}
      </div>
    </>
  );
}
