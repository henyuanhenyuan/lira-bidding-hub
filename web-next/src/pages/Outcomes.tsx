import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { Empty, ErrorBox, Loader, Metric, PageHead } from "../components/ui";
import { formatTs, money, percent } from "../format";
import { useAsync } from "../hooks";
import { ACTION_TEXT } from "../labels";
import type { OutcomeDue } from "../types";

const RESULTS = [
  { value: "improved", label: "改善" },
  { value: "unchanged", label: "无变化" },
  { value: "worse", label: "变差" },
];

export default function Outcomes() {
  const { data, error, loading, reload } = useAsync(
    () => api.get<OutcomeDue[]>("/api/outcomes/due?days=7"),
    [],
  );
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  async function record(id: string, result: string) {
    setBusy(id);
    setMessage("");
    try {
      const response = await api.post<{ case_id?: string | null }>(
        `/api/suggestions/${id}/outcome`,
        { result },
      );
      setMessage(
        response.case_id ? "已记录，并沉淀为案例" : "已记录，但未生成案例",
      );
      await reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "记录失败");
    } finally {
      setBusy(null);
    }
  }

  if (loading && !data) return <Loader label="载入待回收建议…" />;
  if (error && !data) return <ErrorBox message={error} onRetry={reload} />;

  const rows = data ?? [];
  const due = rows.filter((row) => row.due);
  const overdue = due.filter((row) => row.days_overdue >= 1);
  const observed = rows.filter((row) => row.observed).length;

  return (
    <>
      <PageHead
        title="结果回收"
        sub="执行 7 天后回收真实结果；观察到的竞品价格变化只作参考，不替代人工判断"
        actions={
          <button className="btn ghost" onClick={() => void reload()}>
            刷新
          </button>
        }
      />

      <div className="metric-row">
        <Metric
          label="待回收"
          value={due.length}
          sub={`共 ${rows.length} 条执行/采纳记录`}
          tone={due.length ? "warn" : "ok"}
        />
        <Metric
          label="已逾期"
          value={overdue.length}
          sub="超过 7 天未记录"
          tone={overdue.length ? "danger" : "ok"}
        />
        <Metric
          label="有观察数据"
          value={observed}
          sub="可按价格序列核对"
        />
        <Metric
          label="最久逾期"
          value={
            overdue.length
              ? `${Math.max(...overdue.map((row) => row.days_overdue)).toFixed(0)} 天`
              : "—"
          }
          sub="建议优先处理"
        />
      </div>

      {message && <div className="notice">{message}</div>}
      {rows.length === 0 && (
        <Empty>没有待回收的结果。建议执行或采纳后 7 天会出现在这里。</Empty>
      )}

      <div className="outcome-list">
        {rows.map((row) => (
          <article className={`card outcome-item ${row.due ? "due" : ""}`} key={row.id}>
            <div className="outcome-head">
              <span
                className={`badge ${
                  row.due ? (row.days_overdue >= 1 ? "run-failed" : "status-submitted") : "status-executed"
                }`}
              >
                {row.due
                  ? row.days_overdue >= 1
                    ? "已逾期"
                    : "到期"
                  : "未到期"}
              </span>
              <b>{row.target_title || row.target_id}</b>
              <span className="hint">{ACTION_TEXT[row.action] ?? row.action}</span>
              <span className="outcome-when">
                {row.executed_at ? `执行 ${formatTs(row.executed_at)}` : `采纳 ${formatTs(row.created_at)}`}
              </span>
            </div>

            <div className="outcome-meta">
              <span>
                到期 {formatTs(row.due_at)}
                {row.days_overdue >= 0
                  ? ` · 逾期 ${row.days_overdue.toFixed(1)} 天`
                  : ` · 还有 ${Math.abs(row.days_overdue).toFixed(1)} 天`}
              </span>
              {row.executed_price != null && <span>执行价 {money(row.executed_price)}</span>}
              <Link to={`/suggestions/${row.id}`}>查看建议</Link>
            </div>

            {row.observed && (
              <div className="outcome-observed">
                <span className="hint">竞品到手价</span>
                <b>
                  {money(row.observed.baseline_price)} → {money(row.observed.after_price)}
                </b>
                <span
                  className={
                    (row.observed.delta_pct ?? 0) > 0 ? "ok-text" : "error-text"
                  }
                >
                  {row.observed.delta_pct == null
                    ? "—"
                    : `${row.observed.delta_pct > 0 ? "+" : ""}${percent(row.observed.delta_pct, 1)}`}
                </span>
                <span className="hint">仅供参考</span>
              </div>
            )}

            <div className="actions">
              {RESULTS.map((item) => (
                <button
                  className="btn ghost small"
                  key={item.value}
                  disabled={busy === row.id}
                  onClick={() => void record(row.id, item.value)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </article>
        ))}
      </div>
    </>
  );
}
