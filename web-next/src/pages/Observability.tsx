import { useState } from "react";

import { api, qs } from "../core/api";
import { ts } from "../core/format";
import { useAsync } from "../core/hooks";
import type { Metrics, TraceNode, TraceSummary } from "../core/types";
import { Badge, Card, Empty, ErrorBox, Page, Spinner, Stat, Table } from "../ui/kit";

function SpanRows({ nodes, depth = 0 }: { nodes: TraceNode[]; depth?: number }) {
  return (
    <>
      {nodes.map((node) => (
        <tr key={node.id}>
          <td style={{ paddingLeft: 14 + depth * 20 }}>
            <span className="trace-kind">{node.kind}</span> {node.name}
          </td>
          <td>
            <Badge tone={node.status === "ok" ? "ok" : "danger"}>{node.status}</Badge>
          </td>
          <td className="num">{node.duration_ms}ms</td>
        </tr>
      ))}
      {nodes.flatMap((node) =>
        node.children.length ? [
          <SpanRows key={`${node.id}-children`} nodes={node.children} depth={depth + 1} />,
        ] : [],
      )}
    </>
  );
}

export default function Observability() {
  const { data, error, loading, reload } = useAsync(async () => {
    const [metrics, traces] = await Promise.all([
      api.get<Metrics>("/api/metrics"),
      api.get<TraceSummary[]>("/api/observability/traces" + qs({ limit: 15 })),
    ]);
    return { metrics, traces };
  }, []);

  const [tree, setTree] = useState<{ roots: TraceNode[]; count: number } | null>(null);
  const [active, setActive] = useState("");

  async function openTrace(id: string) {
    setActive(id);
    setTree(await api.get<{ roots: TraceNode[]; count: number }>(`/api/observability/traces/${id}`));
  }

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  const { metrics, traces } = data;

  return (
    <Page
      title="可观测"
      desc="模型调用、成本与 Agent 链路追踪"
      actions={
        <button className="btn ghost" onClick={() => void reload()}>
          刷新
        </button>
      }
    >
      <div className="stat-grid">
        <Stat label="24h 调用" value={metrics.calls} hint={`回退率 ${(metrics.fallback_rate * 100).toFixed(0)}%`} tone={metrics.fallback_rate > 0.6 ? "warn" : "ok"} />
        <Stat label="P50 / P95" value={`${metrics.p50_latency_ms ?? "—"} / ${metrics.p95_latency_ms ?? "—"}`} hint="毫秒" />
        <Stat label="P99" value={`${metrics.p99_latency_ms ?? "—"}ms`} />
        <Stat label="Token / 成本" value={metrics.tokens} hint={`¥${metrics.cost}`} />
      </div>

      <div className="split">
        <Card title="按模型" sub="多 Provider 路由的真实分布" flush>
          {metrics.by_model.length === 0 ? (
            <Empty>还没有模型调用记录。</Empty>
          ) : (
            <Table head={["模型", "调用", "回退", "Token", "成本"]}>
              {metrics.by_model.map((row) => (
                <tr key={row.model}>
                  <td className="mono">{row.model}</td>
                  <td className="num">{row.calls}</td>
                  <td className="num">{row.fallback}</td>
                  <td className="num">{row.tokens}</td>
                  <td className="num">¥{row.cost}</td>
                </tr>
              ))}
            </Table>
          )}
        </Card>

        <Card title="按类型" flush>
          {metrics.by_kind.length === 0 ? (
            <Empty>暂无数据。</Empty>
          ) : (
            <Table head={["类型", "调用", "回退"]}>
              {metrics.by_kind.map((row) => (
                <tr key={row.kind}>
                  <td>{row.kind}</td>
                  <td className="num">{row.n}</td>
                  <td className="num">{row.fallback}</td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      </div>

      <Card title="链路追踪" sub="点击一条查看 span 树" flush>
        {traces.length === 0 ? (
          <Empty>还没有 trace，运行一次研判后再看。</Empty>
        ) : (
          <Table head={["Trace", "Span 数", "开始时间"]}>
            {traces.map((row) => (
              <tr
                key={row.trace_id}
                className="click"
                onClick={() => void openTrace(row.trace_id)}
                style={row.trace_id === active ? { background: "#fafaf7" } : undefined}
              >
                <td className="mono">{row.trace_id.slice(0, 12)}</td>
                <td className="num">{row.spans}</td>
                <td className="sub">{ts(row.started_at)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      {tree && (
        <Card title="Span 树" sub={`共 ${tree.count} 个 span`} flush>
          <Table head={["Span", "状态", "耗时"]}>
            <SpanRows nodes={tree.roots} />
          </Table>
        </Card>
      )}
    </Page>
  );
}
