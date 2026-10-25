import { useState } from "react";

import { api, query } from "../api";
import { useAuth } from "../auth";
import {
  Card,
  Empty,
  ErrorBox,
  Loader,
  Metric,
  PageHead,
} from "../components/ui";
import { formatTs } from "../format";
import { useAsync, useStreamEvent } from "../hooks";
import { CHANNEL_TEXT, OUTCOME_TEXT } from "../labels";
import type { CollectLog, CollectSummary, ManualReview } from "../types";

const EMPTY_LOGS: CollectLog[] = [];
const EMPTY_REVIEWS: ManualReview[] = [];

export default function CollectLogs() {
  const { me } = useAuth();
  const isAdmin = me?.role === "admin";
  const [channel, setChannel] = useState("");
  const [busy, setBusy] = useState(false);

  const { data, error, loading, reload } = useAsync(async () => {
    if (!isAdmin) return null;
    const [logs, summary, reviews] = await Promise.all([
      api.get<{ logs: CollectLog[] }>(`/api/collect/logs${query({ channel, limit: 200 })}`),
      api.get<CollectSummary>("/api/collect/summary?hours=24"),
      api.get<{ reviews: ManualReview[] }>("/api/collect/reviews"),
    ]);
    return {
      logs: logs.logs ?? EMPTY_LOGS,
      summary,
      reviews: reviews.reviews ?? EMPTY_REVIEWS,
    };
  }, [isAdmin, channel]);

  useStreamEvent(["ingest", "event"], () => void reload());

  if (!isAdmin) {
    return (
      <>
        <PageHead title="采集日志" sub="仅管理员可见" />
        <Empty>当前账号没有查看采集日志的权限。</Empty>
      </>
    );
  }

  if (loading && !data) return <Loader label="载入采集日志…" />;
  if (error && !data) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;

  const { logs, summary, reviews } = data;
  const errorTotal = Object.entries(summary.errors).reduce(
    (sum, [, count]) => sum + count,
    0,
  );
  const topError = Object.entries(summary.errors).sort((a, b) => b[1] - a[1])[0];

  async function resolve(reviewId: string, decision: "released" | "discarded") {
    setBusy(true);
    try {
      await api.post(
        `/api/collect/reviews/${reviewId}/resolve?decision=${decision}`,
      );
      await reload();
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHead
        title="采集日志"
        sub="每一次采集的请求结果、耗时与异常原因都可追溯"
        actions={
          <button className="btn ghost" onClick={() => void reload()}>
            刷新
          </button>
        }
      />

      <div className="metric-row">
        <Metric
          label="成功 · 24h"
          value={summary.outcomes.done ?? 0}
          sub="正常返回观测"
          tone="ok"
        />
        <Metric
          label="已下发 · 24h"
          value={summary.outcomes.pending ?? 0}
          sub="等待结果回收"
        />
        <Metric
          label="失败 · 24h"
          value={errorTotal}
          sub={topError ? `主要是 ${topError[0]}（${topError[1]} 次）` : "没有异常"}
          tone={errorTotal ? "danger" : "ok"}
        />
        <Metric
          label="待人工复核"
          value={reviews.length}
          sub={reviews.length ? "熔断后需要放行或丢弃" : "队列为空"}
          tone={reviews.length ? "warn" : "ok"}
        />
      </div>

      <div className="toolbar">
        <div className="chips">
          {[
            { value: "", label: "全部通道" },
            { value: "rpa", label: CHANNEL_TEXT.rpa },
            { value: "api", label: CHANNEL_TEXT.api },
            { value: "manual", label: CHANNEL_TEXT.manual },
          ].map((item) => (
            <button
              key={item.value}
              className={`chip${channel === item.value ? " active" : ""}`}
              onClick={() => setChannel(item.value)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <span className="hint">{loading ? "刷新中…" : `${logs.length} 条记录`}</span>
      </div>

      {reviews.length > 0 && (
        <Card title="人工复核队列" sub="熔断期间被拦下的任务不会静默丢弃">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>通道</th>
                  <th>目标</th>
                  <th>原因</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {reviews.map((item) => (
                  <tr key={item.id}>
                    <td className="num">{formatTs(item.created_at)}</td>
                    <td>{CHANNEL_TEXT[item.channel] ?? item.channel}</td>
                    <td>{item.target_id || "—"}</td>
                    <td className="note-cell">{item.reason}</td>
                    <td>
                      <button
                        className="btn ghost small"
                        disabled={busy}
                        onClick={() => void resolve(item.id, "released")}
                      >
                        放行
                      </button>
                      <button
                        className="btn ghost small"
                        disabled={busy}
                        onClick={() => void resolve(item.id, "discarded")}
                      >
                        丢弃
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Card title="请求明细" sub="时间 · 通道 · 状态码 · 耗时 · 异常类型">
        {logs.length === 0 ? (
          <Empty>还没有采集记录。创建任务并等待调度下发后会出现。</Empty>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>通道</th>
                  <th>任务</th>
                  <th>结果</th>
                  <th>状态码</th>
                  <th>耗时</th>
                  <th>异常</th>
                  <th>详情</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((row) => (
                  <tr key={row.id}>
                    <td className="num">{formatTs(row.ts, true)}</td>
                    <td>{CHANNEL_TEXT[row.channel] ?? row.channel}</td>
                    <td className="hint">{row.task_id?.slice(0, 8) ?? "—"}</td>
                    <td>
                      <span
                        className={`badge ${
                          row.outcome === "error" ? "status-failed" : "status-done"
                        }`}
                      >
                        {OUTCOME_TEXT[row.outcome] ?? row.outcome}
                      </span>
                    </td>
                    <td className="num">{row.status_code ?? "—"}</td>
                    <td className="num">
                      {row.latency_ms == null ? "—" : `${row.latency_ms}ms`}
                    </td>
                    <td>{row.error_kind || "—"}</td>
                    <td className="note-cell">{row.detail || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
