import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, qs } from "../core/api";
import { num, pct, ts } from "../core/format";
import { useAsync } from "../core/hooks";
import type {
  AgentRun,
  Dashboard,
  EvalRun,
  GateStatus,
  Health,
  Metrics,
  TraceNode,
  TraceSummary,
} from "../core/types";
import { Donut, SpreadBars, TrendBars } from "../ui/charts";
import { Loading, StatusBadge } from "../ui/kit";
import Shelf from "../ui/shelf";

interface InsightReply {
  insights: string[];
  mode: string;
}

interface Bundle {
  dash: Dashboard;
  metrics: Metrics;
  evals: EvalRun[];
  traces: TraceSummary[];
  runs: AgentRun[];
  spans: (TraceNode & { depth: number })[];
  health: Health | null;
  gates: GateStatus | null;
}

function flatten(nodes: TraceNode[], depth = 0): (TraceNode & { depth: number })[] {
  return nodes.flatMap((node) => [{ ...node, depth }, ...flatten(node.children ?? [], depth + 1)]);
}

function short(value: string, size = 8) {
  return value.length > size ? `${value.slice(0, size)}…` : value;
}

export default function BigScreen() {
  const navigate = useNavigate();
  const [now, setNow] = useState(new Date());
  const [insights, setInsights] = useState<InsightReply | null>(null);
  const [evalBusy, setEvalBusy] = useState(false);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const { data, error, loading, reload } = useAsync<Bundle>(async () => {
    const [dash, metrics, evals, traces, runs, health, gates] = await Promise.all([
      api.get<Dashboard>("/api/dashboard"),
      api.get<Metrics>("/api/metrics"),
      api.get<EvalRun[]>("/api/eval/runs" + qs({ limit: 8 })).catch(() => []),
      api.get<TraceSummary[]>("/api/observability/traces" + qs({ limit: 1 })).catch(() => []),
      api.get<AgentRun[]>("/api/agent/runs" + qs({ limit: 8 })).catch(() => []),
      api.get<Health>("/api/health").catch(() => null),
      api.get<GateStatus>("/api/gates").catch(() => null),
    ]);
    let spans: (TraceNode & { depth: number })[] = [];
    if (traces.length > 0) {
      const detail = await api.get<{ roots: TraceNode[] }>(`/api/observability/traces/${traces[0].trace_id}`)
        .catch(() => ({ roots: [] }));
      spans = flatten(detail.roots).slice(0, 8);
    }
    return { dash, metrics, evals, traces, runs, spans, health, gates };
  }, []);

  useEffect(() => {
    let alive = true;
    const load = () => {
      void api.get<InsightReply>("/api/agent/insights")
        .then((reply) => alive && setInsights(reply))
        .catch(() => undefined);
    };
    load();
    const timer = window.setInterval(() => {
      if (!document.hidden) {
        void reload();
        load();
      }
    }, 60_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [reload]);

  async function runEval() {
    setEvalBusy(true);
    try {
      await api.post("/api/eval/run?tier=smoke&retrieval=false");
      await reload();
    } finally {
      setEvalBusy(false);
    }
  }

  if (loading && !data) return <Loading rows={5} />;
  if (error) return <div className="badge rose">{error}</div>;
  if (!data) return null;

  const { dash, metrics, evals, runs, spans, health, gates } = data;
  const latestEval = evals[0];
  const myPrice = dash.compare.find((item) => item.my_price)?.my_price ?? null;
  const priced = dash.compare.filter((item) => item.point != null);
  const lowest = priced.length ? Math.min(...priced.map((item) => item.point as number)) : null;
  const safe = myPrice == null
    ? 0
    : priced.filter((item) => (item.point as number) >= myPrice).length;
  const coverage = priced.length ? safe / priced.length : null;
  const breaches = priced.filter(
    (item) => myPrice != null && (item.point as number) < myPrice * 0.95,
  ).length;
  const l1 = dash.severity.L1 ?? 0;
  const l2 = dash.severity.L2 ?? 0;
  const l3 = dash.severity.L3 ?? 0;
  const pending = dash.status.submitted ?? 0;
  const trend = dash.trend.slice(-14).map((item) => ({ label: item.date.slice(5), value: item.count }));
  const peak = Math.max(0, ...trend.map((item) => item.value));
  const spreads = [...dash.compare]
    .filter((item) => item.delta != null)
    .sort((a, b) => (a.delta as number) - (b.delta as number))
    .slice(0, 6)
    .map((item) => ({ label: short(item.title), value: item.delta as number }));
  const clock = now.toLocaleTimeString("zh-CN", { hour12: false });
  const date = now.toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
  const week = "周" + "日一二三四五六"[now.getDay()];
  const budget = metrics.budget_used_ratio;

  const tiles: { label: string; value: string | number; note: string }[] = [
    { label: "我方价", value: myPrice == null ? "—" : `¥${myPrice}`, note: `${dash.compare.length} 个竞品在架` },
    {
      label: "竞品最低",
      value: lowest == null ? "—" : `¥${lowest}`,
      note: lowest != null && myPrice != null ? (lowest < myPrice ? "低于我方" : "高于我方") : "—",
    },
    { label: "价格带安全率", value: coverage == null ? "—" : pct(coverage), note: "竞品不低于我方" },
    { label: "击穿价格带", value: breaches, note: "低于我方 95%" },
    { label: "L3 事件", value: l3, note: "最高优先级" },
    { label: "待审批", value: pending, note: "人工确认入口" },
    { label: "24h 调用", value: num(metrics.calls), note: `P95 ${metrics.p95_latency_ms ?? "—"}ms` },
    {
      label: "向量索引",
      value: health?.vector_index.indexed ?? 0,
      note: `案例 ${health?.vector_index.cases ?? 0}`,
    },
  ];

  const statusRows = [
    { label: "已执行", value: dash.status.executed ?? 0, color: "linear-gradient(90deg, var(--mint), var(--cyan))" },
    { label: "待审批", value: dash.status.submitted ?? 0, color: "linear-gradient(90deg, var(--amber), var(--rose))" },
    { label: "待执行", value: dash.status.approved ?? 0, color: "linear-gradient(90deg, var(--cyan), var(--violet))" },
    { label: "已采纳", value: dash.status.accepted ?? 0, color: "linear-gradient(90deg, var(--violet), var(--cyan))" },
  ];
  const statusMax = Math.max(1, ...statusRows.map((row) => row.value));

  return (
    <div className="screen">
      <div className="sc-scan" />
      <div className="screen-head">
        <div className="row gap-12">
          <div className="brand-mark" />
          <div className="stack" style={{ lineHeight: 1.35 }}>
            <span className="badge cyan" style={{ fontSize: 9.5 }}>LIRA BIDDING OS</span>
            <span className="muted" style={{ fontSize: 10, letterSpacing: ".22em" }}>
              多智能体 · 实时竞价中枢
            </span>
          </div>
        </div>
        <div className="screen-actions">
          <span className={`badge ${health?.llm_available ? "mint" : "amber"}`}>
            <i className="dot" /> {health?.llm_available ? "4B 测试通道" : "规则兜底"}
          </span>
          <span className="badge violet">{dash.compare.length} 竞品在架</span>
          <span className="screen-clock">{date} {week} {clock}</span>
          <button className="btn sm ghost" onClick={() => void reload()}>刷新</button>
          <button className="btn sm primary" onClick={() => navigate("/")}>返回智能竞价</button>
        </div>
      </div>

      <div className="screen-frame">
        <div className="sc-banner">
          <div className="wing" />
          <div className="plate">
            <div className="stack" style={{ alignItems: "center" }}>
              <h1>竞品竞价智能中枢</h1>
              <span className="sub">Real-time Bidding Command Center</span>
            </div>
          </div>
          <div className="wing right" />
        </div>

        <div className="screen-grid">
          <div className="stack gap-10" style={{ minHeight: 0 }}>
            <div className="sc-panel" style={{ flex: "1 1 42%", minHeight: 0 }}>
              <div className="row between">
                <div className="sc-title">核心指标</div>
                <span className="muted" style={{ fontSize: 9, letterSpacing: ".14em" }}>实时</span>
              </div>
              <div className="sc-metrics mt-8">
                {tiles.map((tile) => (
                  <div className="sc-metric" key={tile.label}>
                    <span>{tile.label}</span>
                    <b>{tile.value}</b>
                    <em>{tile.note}</em>
                  </div>
                ))}
              </div>
              <div className="row between mt-8">
                <span className="muted" style={{ fontSize: 9, letterSpacing: ".12em" }}>处置状态</span>
                <span className="muted" style={{ fontSize: 9 }}>建议数</span>
              </div>
              <div className="sc-eval-rows mt-4">
                {statusRows.map((row) => (
                  <div className="sc-eval-row" key={row.label}>
                    <div className="line">
                      <span>{row.label}</span>
                      <b>{row.value}</b>
                    </div>
                    <div className="sc-meter">
                      <i style={{ width: `${Math.max(4, (row.value / statusMax) * 100)}%`, background: row.color }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="sc-panel" style={{ flex: "0 0 158px", minHeight: 0 }}>
              <div className="sc-title">事件严重度</div>
              <div className="mt-8">
                <Donut
                  compact
                  center={l1 + l2 + l3}
                  unit="事件"
                  segments={[
                    { label: "L1 提示", value: l1, tone: "cyan" },
                    { label: "L2 预警", value: l2, tone: "amber" },
                    { label: "L3 高危", value: l3, tone: "rose" },
                  ]}
                />
              </div>
            </div>

            <div className="sc-panel" style={{ flex: "1 1 0", minHeight: 0 }}>
              <div className="row between">
                <div className="sc-title">AI 解读</div>
                <span className={`badge ${insights?.mode === "llm" ? "violet" : ""}`} style={{ fontSize: 9 }}>
                  {insights?.mode === "llm" ? "模型实时" : "规则兜底"}
                </span>
              </div>
              <div className="sc-list mt-8">
                {(insights?.insights ?? ["等待数据…"]).slice(0, 4).map((text, index) => (
                  <div className="sc-row" key={index}>
                    <span className="rk">{index + 1}</span>
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{text}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="sc-panel stack" style={{ minHeight: 0, gap: 8 }}>
            <div className="sc-ring-bg" />
            <div className="row between" style={{ padding: "2px 2px 0", minHeight: 18 }}>
              <span className="muted" style={{ fontSize: 9.5, letterSpacing: ".12em" }}>
                价格带安全率{" "}
                <b style={{ color: coverage != null && coverage >= 0.6 ? "var(--mint)" : "var(--amber)" }}>
                  {coverage == null ? "—" : pct(coverage)}
                </b>
              </span>
              <span className="muted" style={{ fontSize: 9.5 }}>
                竞品最低 <b style={{ color: "var(--ink)" }}>{lowest == null ? "—" : `¥${lowest}`}</b>
              </span>
            </div>
            <div style={{ flex: "1 1 auto", minHeight: 0, display: "flex", alignItems: "stretch" }}>
              <Shelf
                perRow={6}
                items={dash.compare.slice(0, 18).map((item) => ({
                  id: item.id,
                  title: item.title,
                  mine: item.my_price,
                  theirs: item.point,
                  delta: item.delta,
                  severity: item.severity,
                }))}
                myPrice={myPrice}
              />
            </div>
            <div style={{ height: 132, flex: "0 0 132px" }}>
              <div className="row between" style={{ marginBottom: 2 }}>
                <span className="muted" style={{ fontSize: 9.5, letterSpacing: ".14em" }}>近 14 天事件</span>
                <span className="muted" style={{ fontSize: 9.5 }}>峰值 {peak}</span>
              </div>
              <TrendBars data={trend} height={108} />
            </div>
          </div>

          <div className="stack gap-10" style={{ minHeight: 0 }}>
            <div className="sc-panel" style={{ flex: "1 1 34%", minHeight: 0 }}>
              <div className="row between">
                <div className="sc-title">评测与门禁</div>
                <button className="btn sm ghost" disabled={evalBusy} onClick={() => void runEval()}>
                  {evalBusy ? "评测中…" : "运行评测"}
                </button>
              </div>
              <div className="sc-eval-rows mt-8">
                <div className="sc-eval-row">
                  <div className="line"><span>最近准确率</span><b>{latestEval ? pct(latestEval.accuracy) : "—"}</b></div>
                  <div className="sc-meter"><i style={{ width: `${(latestEval?.accuracy ?? 0) * 100}%` }} /></div>
                </div>
                <div className="sc-eval-row">
                  <div className="line"><span>模型回退率</span><b>{pct(metrics.fallback_rate)}</b></div>
                  <div className="sc-meter"><i style={{ width: `${Math.min(100, metrics.fallback_rate * 100)}%`, background: "linear-gradient(90deg, var(--amber), var(--rose))" }} /></div>
                </div>
                <div className="sc-eval-row">
                  <div className="line"><span>当日预算</span><b>{budget == null ? "—" : pct(budget)}</b></div>
                  <div className="sc-meter"><i style={{ width: `${Math.min(100, (budget ?? 0) * 100)}%`, background: "linear-gradient(90deg, var(--mint), var(--cyan))" }} /></div>
                </div>
                <div className="row between mt-4">
                  <span className={`badge ${gates?.ok ? "mint" : "amber"}`} style={{ fontSize: 9 }}>
                    {gates?.ok ? "门禁通过" : "门禁未达标"}
                  </span>
                  <span className="muted" style={{ fontSize: 9.5 }}>
                    {latestEval ? `${latestEval.passed}/${latestEval.total} 用例` : "尚无评测"}
                  </span>
                </div>
              </div>
              <div className="row between mt-8">
                <span className="muted" style={{ fontSize: 9, letterSpacing: ".12em" }}>历史准确率</span>
                <span className="muted" style={{ fontSize: 9 }}>{evals.length} 次</span>
              </div>
              <div style={{ height: 62, marginTop: 2 }}>
                <TrendBars
                  height={62}
                  tone="mint"
                  data={[...evals].reverse().map((item) => ({
                    label: item.created_at.slice(5, 10),
                    value: Math.round(item.accuracy * 100),
                  }))}
                />
              </div>
            </div>

            <div className="sc-panel" style={{ flex: "1 1 30%", minHeight: 0 }}>
              <div className="row between">
                <div className="sc-title">价差分布</div>
                <span className="muted" style={{ fontSize: 9 }}>相对我方</span>
              </div>
              <div className="mt-8">
                <SpreadBars rows={spreads} />
              </div>
            </div>

            <div className="sc-panel" style={{ flex: "1 1 36%", minHeight: 0 }}>
              <div className="row between">
                <div className="sc-title">最近运行</div>
                <span className="muted" style={{ fontSize: 9 }}>{spans.length} span</span>
              </div>
              <div className="sc-list mt-8">
                {runs.slice(0, 5).map((run) => (
                  <div className="sc-row" key={run.id}>
                    <span className="rk">·</span>
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {run.target_title ?? short(run.id)}
                    </span>
                    <StatusBadge value={run.status} />
                  </div>
                ))}
                {runs.length === 0 && <span className="muted" style={{ fontSize: 11 }}>暂无运行</span>}
              </div>
            </div>
          </div>
        </div>

        <div className="sc-marquee">
          <span className="tag">AI 研判</span>
          <div className="roll">
            <div className="roll-inner">
              {[0, 1].map((index) => (
                <span key={index}>
                  {(insights?.insights ?? ["多智能体正在分析竞品价格与事件…"]).join("　｜　")}
                </span>
              ))}
            </div>
          </div>
          <span className="badge violet">最近 {ts(dash.generated_at)}</span>
        </div>
      </div>
    </div>
  );
}
