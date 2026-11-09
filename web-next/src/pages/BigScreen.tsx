import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api, qs } from "../core/api";
import { num, pct, ts } from "../core/format";
import { useAsync } from "../core/hooks";
import type { Metrics, TraceNode, TraceSummary } from "../core/types";
import { Ticker, VendingMachine } from "../ui/viz";
import { Badge, Empty, Spinner, StatusBadge } from "../ui/kit";

interface CompareRow {
  id: string;
  title: string;
  my_price: number | null;
  point: number | null;
  delta: number | null;
  severity: string | null;
}

interface Dashboard {
  compare: CompareRow[];
  severity: Record<string, number>;
  status: Record<string, number>;
}

interface EvalRow {
  run_key: string;
  total: number;
  passed: number;
  accuracy: number;
  tier?: string | null;
  created_at: string;
}

interface RunRow {
  id: string;
  status: string;
  model: string;
  latency_ms?: number | null;
  started_at: string;
  target_title?: string | null;
}

interface InsightReply {
  insights: string[];
  mode: string;
}

function flatten(nodes: TraceNode[], depth = 0): (TraceNode & { depth: number })[] {
  return nodes.flatMap((node) => [
    { ...node, depth },
    ...flatten(node.children ?? [], depth + 1),
  ]);
}

function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return <span className="screen-clock">{now.toLocaleTimeString("zh-CN")}</span>;
}

export default function BigScreen() {
  const { data, error, loading, reload } = useAsync(async () => {
    const [dash, metrics, evals, traces, runs, insights] = await Promise.all([
      api.get<Dashboard>("/api/dashboard"),
      api.get<Metrics>("/api/metrics"),
      api.get<EvalRow[]>("/api/eval/runs" + qs({ limit: 3 })),
      api.get<TraceSummary[]>("/api/observability/traces" + qs({ limit: 1 })),
      api.get<RunRow[]>("/api/agent/runs" + qs({ limit: 6 })),
      api.get<InsightReply>("/api/agent/insights").catch(() => null),
    ]);
    let spans: (TraceNode & { depth: number })[] = [];
    if (traces.length > 0) {
      const detail = await api.get<{ roots: TraceNode[] }>(
        `/api/observability/traces/${traces[0].trace_id}`,
      );
      spans = flatten(detail.roots).slice(0, 9);
    }
    return { dash, metrics, evals, runs, spans, insights };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!document.hidden) void reload();
    }, 10_000);
    return () => window.clearInterval(timer);
  }, [reload]);

  const [evalBusy, setEvalBusy] = useState(false);
  const [evalMsg, setEvalMsg] = useState("");

  async function runEval() {
    setEvalBusy(true);
    setEvalMsg("");
    try {
      await api.post("/api/eval/run?tier=smoke&retrieval=false");
      await reload();
      setEvalMsg("评测完成");
    } catch (err) {
      setEvalMsg(err instanceof Error ? err.message : "评测失败");
    } finally {
      setEvalBusy(false);
    }
  }

  if (loading && !data) return <Spinner label="大屏载入中…" />;
  if (error) return <div className="screen-error">{error}</div>;
  if (!data) return null;

  const { dash, metrics, evals, runs, spans, insights } = data;
  const latestEval = evals[0];
  const myPrice = dash.compare.find((item) => item.my_price)?.my_price ?? null;
  const breaches = dash.compare.filter(
    (item) => item.my_price && item.point && item.point < item.my_price * 0.95,
  ).length;

  const tickerItems = [
    ...(insights?.insights ?? []).map((text) => (
      <span className="tick-insight">{text}</span>
    )),
    ...runs.map((run) => (
      <span className="tick-run">
        {run.target_title ?? run.id.slice(0, 6)} · {run.status} · {run.latency_ms ?? "—"}ms
      </span>
    )),
  ];

  return (
    <div className="screen immersive">
      <header className="screen-head">
        <div>
          <span className="screen-eyebrow">LIRA · LIVE MARKET</span>
          <h1>竞品智能体 · 实时大屏</h1>
        </div>
        <div className="screen-meta">
          <Clock />
          <span className="screen-dot" />
          <Link className="btn ghost sm" to="/">
            返回工作区
          </Link>
        </div>
      </header>

      <div className="screen-body">
        <aside className="screen-side">
          <div className="screen-stat-block">
            <span>我方价</span>
            <b>¥{myPrice ?? "—"}</b>
          </div>
          <div className="screen-stat-block">
            <span>击穿价格带</span>
            <b className={breaches ? "danger" : undefined}>{breaches}</b>
          </div>
          <div className="screen-stat-block">
            <span>L3 事件</span>
            <b className={dash.severity.L3 ? "danger" : undefined}>{dash.severity.L3 ?? 0}</b>
          </div>
          <div className="screen-stat-block">
            <span>待审批</span>
            <b>{dash.status.submitted ?? 0}</b>
          </div>
          <div className="screen-insights">
            <h2>AI 解读</h2>
            <ul>
              {(insights?.insights ?? ["等待数据…"]).map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
            <Badge tone={insights?.mode === "llm" ? "accent" : "neutral"}>
              {insights?.mode === "llm" ? "模型实时" : "规则"}
            </Badge>
          </div>
        </aside>

        <div className="screen-center">
          <VendingMachine
            myPrice={myPrice}
            items={dash.compare.map((item) => ({
              id: item.id,
              title: item.title,
              mine: item.my_price,
              theirs: item.point,
              delta: item.delta,
              severity: item.severity,
            }))}
          />
        </div>

        <aside className="screen-side right">
          <div className="screen-panel">
            <h2>模型</h2>
            <div className="screen-metric">
              <b>{metrics.calls}</b>
              <span>24h 调用</span>
            </div>
            <div className="screen-metric">
              <b>{pct(metrics.fallback_rate)}</b>
              <span>回退率</span>
            </div>
            <div className="screen-metric">
              <b>{metrics.p95_latency_ms ?? "—"}ms</b>
              <span>P95</span>
            </div>
            <div className="screen-metric">
              <b>{num(metrics.tokens)}</b>
              <span>Token</span>
            </div>
          </div>

          <div className="screen-panel">
            <h2>
              评测
              <button className="btn ghost sm" disabled={evalBusy} onClick={() => void runEval()}>
                {evalBusy ? "评测中…" : "运行评测"}
              </button>
            </h2>
            {latestEval ? (
              <>
                <div className="screen-eval">
                  <b>{pct(latestEval.accuracy)}</b>
                  <span>
                    {latestEval.passed}/{latestEval.total} · {latestEval.tier ?? "legacy"}
                  </span>
                </div>
                <p className="panel-sub">{ts(latestEval.created_at)}</p>
              </>
            ) : (
              <Empty>还没有评测。</Empty>
            )}
            {evalMsg && <p className="panel-sub">{evalMsg}</p>}
          </div>

          <div className="screen-panel">
            <h2>执行脉冲</h2>
            {spans.length === 0 ? (
              <Empty>暂无 trace。</Empty>
            ) : (
              <ul className="pulse">
                {spans.map((span) => (
                  <li key={span.id} className={`pulse-item k-${span.kind}`}>
                    <i />
                    <span>{span.name}</span>
                    <em>{span.duration_ms}ms</em>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="screen-panel">
            <h2>最近运行</h2>
            <ul className="run-feed">
              {runs.slice(0, 5).map((run) => (
                <li key={run.id}>
                  <span>{run.target_title ?? run.id.slice(0, 6)}</span>
                  <StatusBadge value={run.status} />
                </li>
              ))}
            </ul>
          </div>
        </aside>
      </div>

      <Ticker items={tickerItems} />
    </div>
  );
}
