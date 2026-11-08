import { useState } from "react";

import { api, query } from "../api";
import { Card, Empty, ErrorBox, Loader, Metric, PageHead } from "../components/ui";
import { formatTs, percent } from "../format";
import { useAsync } from "../hooks";
import type { TraceNode, TraceSummary } from "../types";

interface Metrics {
  calls: number;
  fallback_rate: number;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  p99_latency_ms: number | null;
  tokens: number;
  cost: number;
  budget_used_ratio: number | null;
  by_model: { model: string; calls: number; fallback: number; tokens: number; cost: number }[];
  by_kind: { kind: string; n: number; fallback: number }[];
}

function SpanRow({ node, depth }: { node: TraceNode; depth: number }) {
  return (
    <>
      <tr>
        <td style={{ paddingLeft: `${12 + depth * 18}px` }}>
          <span className="mono">{node.kind}</span> {node.name}
        </td>
        <td>
          <span className={`badge ${node.status === "ok" ? "run-succeeded" : "run-failed"}`}>
            {node.status}
          </span>
        </td>
        <td className="num">{node.duration_ms}ms</td>
      </tr>
      {node.children.map((child) => (
        <SpanRow key={child.id} node={child} depth={depth + 1} />
      ))}
    </>
  );
}

export default function Observability() {
  const { data, error, loading, reload } = useAsync(async () => {
    const [metrics, traces] = await Promise.all([
      api.get<Metrics>("/api/metrics"),
      api.get<TraceSummary[]>("/api/observability/traces" + query({ limit: 20 })),
    ]);
    return { metrics, traces };
  }, []);

  const [trace, setTrace] = useState<{ roots: TraceNode[]; count: number } | null>(null);
  const [active, setActive] = useState<string>("");

  async function openTrace(traceId: string) {
    setActive(traceId);
    const detail = await api.get<{ roots: TraceNode[]; count: number }>(
      `/api/observability/traces/${traceId}`,
    );
    setTrace(detail);
  }

  return (
    <>
      <PageHead
        title="观测"
        sub="模型调用、成本与 Agent 链路追踪"
        actions={
          <button className="btn ghost" onClick={() => void reload()}>
            刷新
          </button>
        }
      />

      {error && <ErrorBox message={error} />}
      {loading && !data && <Loader />}

      {data && (
        <>
          <div className="metric-row">
            <Metric label="调用次数" value={data.metrics.calls} sub="近 24 小时" />
            <Metric
              label="回退率"
              value={percent(data.metrics.fallback_rate)}
              sub="模型不可用时走模板"
              tone={data.metrics.fallback_rate > 0.3 ? "warn" : "ok"}
            />
            <Metric label="P50 / P95" value={`${data.metrics.p50_latency_ms ?? "—"} / ${data.metrics.p95_latency_ms ?? "—"}`} sub="毫秒" />
            <Metric label="Token" value={data.metrics.tokens} sub={`成本 ¥${data.metrics.cost}`} />
          </div>

          <Card title="按模型" sub="多 Provider 路由的实际分布">
            {data.metrics.by_model.length === 0 ? (
              <Empty>还没有模型调用记录。</Empty>
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>模型</th>
                      <th>调用</th>
                      <th>回退</th>
                      <th>Token</th>
                      <th>成本</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.metrics.by_model.map((row) => (
                      <tr key={row.model}>
                        <td>{row.model}</td>
                        <td className="num">{row.calls}</td>
                        <td className="num">{row.fallback}</td>
                        <td className="num">{row.tokens}</td>
                        <td className="num">¥{row.cost}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card title="链路追踪" sub="点击一行查看 span 树">
            {data.traces.length === 0 ? (
              <Empty>还没有 trace 记录，运行一次研判后再来。</Empty>
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Trace</th>
                      <th>Span 数</th>
                      <th>开始时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.traces.map((row) => (
                      <tr
                        key={row.trace_id}
                        className={row.trace_id === active ? "row-active" : ""}
                        onClick={() => void openTrace(row.trace_id)}
                      >
                        <td className="mono">{row.trace_id.slice(0, 12)}</td>
                        <td className="num">{row.spans}</td>
                        <td>{formatTs(row.started_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {trace && (
            <Card title="Span 树" sub={`共 ${trace.count} 个 span`}>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Span</th>
                      <th>状态</th>
                      <th>耗时</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trace.roots.map((node) => (
                      <SpanRow key={node.id} node={node} depth={0} />
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
    </>
  );
}
