import { Link } from "react-router-dom";

import { api } from "../api";
import SuggestionActions from "../components/SuggestionActions";
import {
  Empty,
  ErrorBox,
  GuardrailBadge,
  Loader,
  PageHead,
  StatusBadge,
} from "../components/ui";
import { formatTs, percent } from "../format";
import { useAsync, useStreamEvent } from "../hooks";
import { ACTION_TEXT } from "../labels";
import type { Suggestion } from "../types";

export default function Approvals() {
  const { data, error, loading, reload } = useAsync(
    () => api.get<Suggestion[]>("/api/approvals/inbox"),
    [],
  );
  useStreamEvent(["approval", "event"], () => void reload());

  return (
    <>
      <PageHead
        title="审批"
        sub="批准后运营才能执行；审批记录会进入时间线"
        actions={
          <button className="btn ghost" onClick={() => void reload()}>
            刷新
          </button>
        }
      />

      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !data && <Loader />}
      {data && data.length === 0 && <Empty>没有待审批的建议。</Empty>}

      <div className="approval-grid">
        {data?.map((item) => (
          <article className="card approval-card" key={item.id}>
            <div className="approval-head">
              <StatusBadge value={item.status} />
              <GuardrailBadge value={item.guardrail} />
              <span className="hint">
                {item.target_title || item.target_id} · 提交人 {item.submitted_by || "—"}
              </span>
              <span className="approval-margin">
                毛利 {item.margin_at_target == null ? "—" : percent(item.margin_at_target, 1)}
              </span>
            </div>

            <h3>
              <Link to={`/suggestions/${item.id}`}>
                {ACTION_TEXT[item.action] ?? item.action}
              </Link>
            </h3>
            <p className="narrative">{item.narrative}</p>
            <div className="approval-meta">
              <span>置信 {percent(item.confidence)}</span>
              <span>{formatTs(item.created_at)}</span>
              {item.impact_low != null && item.impact_high != null && (
                <span>
                  价差 ¥{item.impact_low.toFixed(2)} ~ ¥{item.impact_high.toFixed(2)}
                </span>
              )}
            </div>

            <SuggestionActions suggestion={item} onChange={reload} />
          </article>
        ))}
      </div>
    </>
  );
}
