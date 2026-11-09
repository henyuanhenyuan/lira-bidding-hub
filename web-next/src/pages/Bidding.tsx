import { useEffect, useMemo, useRef, useState } from "react";

import { api, ApiError } from "../core/api";
import { money, num, pct, ts } from "../core/format";
import { useAsync } from "../core/hooks";
import type {
  CompareRow,
  Dashboard,
  EventRow,
  ExecutionRow,
  GateStatus,
  Health,
  HoldoutReport,
  Metrics,
  PriceRow,
  RiskView,
  Suggestion,
  SuggestionDetail,
  TimelineRow,
} from "../core/types";
import QAWidget from "../ui/agentdock";
import { PriceBand } from "../ui/charts";
import {
  Delta,
  Empty,
  ErrorBox,
  Loading,
  Panel,
  Seg,
  SeverityBadge,
  Sparkline,
  StatusBadge,
  actionText,
  eventText,
} from "../ui/kit";
import Shelf from "../ui/shelf";

interface InsightReply {
  insights: string[];
  mode: string;
  cached?: boolean;
}

interface ProductRow {
  sku: string;
  title: string;
  price: number | null;
  cost?: number | null;
  margin_floor?: number | null;
}

interface MappingRow {
  id: string;
  my_sku: string;
  target_id: string;
  score: number | null;
  status: string;
  target_title?: string | null;
  my_title?: string | null;
}

interface OutcomeRow {
  id: string;
  suggestion_id: string;
  result: string;
  note?: string | null;
  recorded_at: string;
}

interface DueRow {
  id: string;
  event_id: string;
  action: string;
  status: string;
  target_id?: string | null;
  target_title?: string | null;
  due_at: string;
  days_overdue: number;
  due: boolean;
  observed?: { point?: number | null } | null;
}

interface EventDetail extends EventRow {
  similar_cases: { id: string; summary: string; outcome_7d?: string | null }[];
}

interface ExecutionPreview {
  plan: {
    from_price?: number | null;
    to_price: number;
    margin_at_target?: number | null;
    guardrail: string;
    guardrail_note?: string | null;
    mode: string;
  };
  configured: boolean;
  execution: Record<string, unknown> | null;
}

interface Bundle {
  dash: Dashboard;
  events: EventRow[];
  suggestions: Suggestion[];
  metrics: Metrics;
  gates: GateStatus | null;
  holdout: HoldoutReport | null;
  health: Health | null;
  products: ProductRow[];
  mappings: MappingRow[];
  due: DueRow[];
  overdue: DueRow[];
}

const STATUS_LABELS: Record<string, string> = {
  pending: "待提交",
  submitted: "待审批",
  approved: "已批准",
  executed: "已执行",
  rejected: "已驳回",
  cancelled: "已取消",
  accepted: "已采纳",
};

function shortId(value: string, size = 6) {
  return value ? value.slice(0, size) : "—";
}

export default function Bidding() {
  const { data, error, loading, reload } = useAsync<Bundle>(async () => {
    const [dash, events, suggestions, metrics, gates, holdout, health, products, mappings, due, overdue] =
      await Promise.all([
        api.get<Dashboard>("/api/dashboard"),
        api.get<EventRow[]>("/api/events?limit=120"),
        api.get<Suggestion[]>("/api/suggestions?limit=160"),
        api.get<Metrics>("/api/metrics?hours=24").catch(() => null),
        api.get<GateStatus>("/api/gates").catch(() => null),
        api.get<HoldoutReport>("/api/experiments/holdout?days=30").catch(() => null),
        api.get<Health>("/api/health").catch(() => null),
        api.get<ProductRow[]>("/api/my-products").catch(() => []),
        api.get<MappingRow[]>("/api/mappings").catch(() => []),
        api.get<DueRow[]>("/api/outcomes/due?days=7").catch(() => []),
        api.get<DueRow[]>("/api/outcomes/overdue?days=7").catch(() => []),
      ]);
    return {
      dash,
      events,
      suggestions,
      metrics: metrics as Metrics,
      gates,
      holdout,
      health,
      products,
      mappings,
      due,
      overdue,
    };
  }, []);

  const [view, setView] = useState<"market" | "disposition" | "loop">("market");
  const [tab, setTab] = useState<"all" | "todo" | "done">("all");
  const [auto, setAuto] = useState(false);
  const [selectedEventId, setSelectedEventId] = useState("");
  const [selectedTargetId, setSelectedTargetId] = useState("");
  const [busyId, setBusyId] = useState("");
  const [notice, setNotice] = useState("");
  const [insight, setInsight] = useState<InsightReply | null>(null);
  const [insightLoading, setInsightLoading] = useState(true);
  const [detail, setDetail] = useState<SuggestionDetail | null>(null);
  const [eventDetail, setEventDetail] = useState<EventDetail | null>(null);
  const [timeline, setTimeline] = useState<TimelineRow[]>([]);
  const [executions, setExecutions] = useState<ExecutionRow[]>([]);
  const [risk, setRisk] = useState<RiskView | null>(null);
  const [outcome, setOutcome] = useState<OutcomeRow | null>(null);
  const [outcomeResult, setOutcomeResult] = useState("unchanged");
  const [outcomeNote, setOutcomeNote] = useState("");
  const [preview, setPreview] = useState<ExecutionPreview | null>(null);
  const [prices, setPrices] = useState<PriceRow[]>([]);
  const [detailTick, setDetailTick] = useState(0);
  const [myPriceDraft, setMyPriceDraft] = useState("");
  const [holdoutDraft, setHoldoutDraft] = useState(false);
  const [mappingBusy, setMappingBusy] = useState("");
  const refreshTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    let alive = true;
    void api
      .get<InsightReply>("/api/agent/insights")
      .then((reply) => alive && setInsight(reply))
      .catch(() => alive && setInsight(null))
      .finally(() => alive && setInsightLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  const dash = data?.dash;
  const events = useMemo(() => data?.events ?? [], [data?.events]);
  const suggestions = useMemo(() => data?.suggestions ?? [], [data?.suggestions]);

  const suggestionByEvent = useMemo(() => {
    const map: Record<string, Suggestion> = {};
    for (const item of suggestions) if (!map[item.event_id]) map[item.event_id] = item;
    return map;
  }, [suggestions]);

  const selected = useMemo(() => {
    if (selectedEventId) return events.find((item) => item.id === selectedEventId);
    if (selectedTargetId) return events.find((item) => item.target_id === selectedTargetId);
    return events.find((item) => suggestionByEvent[item.id]) ?? events[0];
  }, [events, selectedEventId, selectedTargetId, suggestionByEvent]);

  const selectedSuggestion = selected ? suggestionByEvent[selected.id] : undefined;

  const target = useMemo(() => {
    if (!dash) return undefined;
    return (
      dash.compare.find((item) => item.id === selectedTargetId) ??
      dash.compare.find((item) => item.id === selected?.target_id) ??
      dash.compare[0]
    );
  }, [dash, selectedTargetId, selected?.target_id]);

  useEffect(() => {
    if (!selectedTargetId && target?.id) setSelectedTargetId(target.id);
  }, [selectedTargetId, target?.id]);

  useEffect(() => {
    if (!target) return;
    setMyPriceDraft(target.my_price == null ? "" : String(target.my_price));
    setHoldoutDraft(Boolean(target.holdout));
  }, [target?.id, target?.my_price, target?.holdout]);

  useEffect(() => {
    if (!auto || !selected || selectedSuggestion || busyId) return;
    void analyze(selected.id, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auto, selected?.id, selectedSuggestion?.id]);

  useEffect(() => {
    const eid = selected?.id;
    if (!eid) {
      setEventDetail(null);
      return;
    }
    let alive = true;
    void api
      .get<EventDetail>(`/api/events/${encodeURIComponent(eid)}`)
      .then((row) => alive && setEventDetail(row))
      .catch(() => alive && setEventDetail(null));
    return () => {
      alive = false;
    };
  }, [selected?.id]);

  useEffect(() => {
    const sid = selectedSuggestion?.id;
    if (!sid) {
      setDetail(null);
      setTimeline([]);
      setExecutions([]);
      setRisk(null);
      setOutcome(null);
      setPreview(null);
      return;
    }
    let alive = true;
    void Promise.all([
      api.get<SuggestionDetail>(`/api/suggestions/${sid}`).catch(() => null),
      api.get<TimelineRow[]>(`/api/suggestions/${sid}/timeline`).catch(() => []),
      api.get<ExecutionRow[]>(`/api/suggestions/${sid}/executions`).catch(() => []),
      api.get<RiskView>(`/api/suggestions/${sid}/risk`).catch(() => null),
      api.get<OutcomeRow | null>(`/api/suggestions/${sid}/outcome`).catch(() => null),
    ]).then(([row, rows, runs, riskView, outcomeRow]) => {
      if (!alive) return;
      setDetail(row);
      setTimeline(rows);
      setExecutions(runs);
      setRisk(riskView);
      setOutcome(outcomeRow);
      setOutcomeResult(outcomeRow?.result ?? "unchanged");
      setOutcomeNote(outcomeRow?.note ?? "");
      setPreview(null);
    });
    return () => {
      alive = false;
    };
  }, [selectedSuggestion?.id, detailTick]);

  useEffect(() => {
    const tid = target?.id;
    if (!tid) {
      setPrices([]);
      return;
    }
    let alive = true;
    void api
      .get<PriceRow[]>(`/api/targets/${encodeURIComponent(tid)}/prices?limit=40`)
      .then((rows) => alive && setPrices(rows))
      .catch(() => alive && setPrices([]));
    return () => {
      alive = false;
    };
  }, [target?.id]);

  useEffect(() => {
    const source = new EventSource("/api/stream");
    const refresh = () => {
      window.clearTimeout(refreshTimer.current);
      refreshTimer.current = window.setTimeout(() => {
        if (!document.hidden) void reload();
      }, 1200);
    };
    source.addEventListener("approval", refresh);
    source.addEventListener("ingest", refresh);
    source.addEventListener("eval", refresh);
    return () => {
      source.close();
      window.clearTimeout(refreshTimer.current);
    };
  }, [reload]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!document.hidden) void reload();
    }, 60_000);
    return () => window.clearInterval(timer);
  }, [reload]);

  function flash(text: string) {
    setNotice(text);
    window.setTimeout(() => setNotice(""), 2800);
  }

  async function suggestionAction(fn: () => Promise<unknown>, done: string) {
    try {
      await fn();
      await reload();
      setDetailTick((value) => value + 1);
      flash(done);
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "操作失败");
    }
  }

  async function analyze(eventId: string, silent = false) {
    if (busyId) return;
    setBusyId(eventId);
    if (!silent) setNotice("");
    try {
      await api.post(`/api/events/${encodeURIComponent(eventId)}/analyze`);
      await reload();
      setDetailTick((value) => value + 1);
      if (!silent) flash("研判完成，已生成新建议");
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "研判失败");
    } finally {
      setBusyId("");
    }
  }

  async function previewExecution() {
    if (!selectedSuggestion) return;
    try {
      setPreview(await api.get<ExecutionPreview>(`/api/suggestions/${selectedSuggestion.id}/execution-preview`));
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "预览失败");
    }
  }

  async function recordOutcome() {
    if (!selectedSuggestion) return;
    try {
      await api.post(`/api/suggestions/${selectedSuggestion.id}/outcome`, {
        result: outcomeResult,
        note: outcomeNote || null,
      });
      setOutcome(
        await api.get<OutcomeRow | null>(`/api/suggestions/${selectedSuggestion.id}/outcome`).catch(() => null),
      );
      flash("结果已回收");
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "回收失败");
    }
  }

  async function suggestMappings() {
    setMappingBusy("suggest");
    try {
      const result = await api.post<{ created: number }>("/api/mappings/suggest");
      flash(`已生成 ${result.created} 条映射建议`);
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "生成失败");
    } finally {
      setMappingBusy("");
    }
  }

  async function decideMapping(mapping: MappingRow, decision: "confirmed" | "rejected") {
    setMappingBusy(mapping.id);
    try {
      await api.post(`/api/mappings/${mapping.id}/decide`, { decision });
      flash(decision === "confirmed" ? "映射已确认" : "映射已驳回");
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "操作失败");
    } finally {
      setMappingBusy("");
    }
  }

  async function saveTarget() {
    if (!target) return;
    const price = Number(myPriceDraft);
    if (!Number.isFinite(price) || price < 0) {
      flash("我方价需要是非负数字");
      return;
    }
    setMappingBusy("target");
    try {
      await api.patch(`/api/targets/${target.id}`, { my_price: price, holdout: holdoutDraft });
      flash("竞品设置已保存");
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "保存失败");
    } finally {
      setMappingBusy("");
    }
  }

  function pickTarget(id: string) {
    setSelectedTargetId(id);
    const latest = events.find((event) => event.target_id === id);
    setSelectedEventId(latest?.id ?? "");
  }

  function pickEvent(event: EventRow) {
    setSelectedEventId(event.id);
    setSelectedTargetId(event.target_id);
  }

  if (loading && !data) return <Loading rows={4} />;
  if (error) return <ErrorBox message={error} />;
  if (!data || !dash) return null;

  const metrics = data.metrics;
  const gates = data.gates;
  const holdout = data.holdout;
  const myPrice = target?.my_price ?? dash.compare.find((item) => item.my_price)?.my_price ?? null;
  const breaches = dash.compare.filter(
    (item) => item.my_price && item.point && item.point < item.my_price * 0.95,
  ).length;
  const pending = dash.status.submitted ?? 0;
  const l3 = dash.severity.L3 ?? 0;
  const accuracy = gates?.latest_eval?.accuracy ?? null;
  const rows = events.filter((event) => {
    const suggestion = suggestionByEvent[event.id];
    if (tab === "todo") return suggestion?.status === "submitted";
    if (tab === "done") return suggestion?.status === "executed";
    return true;
  });

  return (
    <div className="stack gap-16 fade-in">
      {notice && (
        <div className="badge mint" style={{ whiteSpace: "normal", padding: "9px 12px", alignSelf: "flex-start" }}>
          {notice}
        </div>
      )}

      <div className="row between wrap gap-10">
        <Seg
          value={view}
          onChange={setView}
          items={[
            { key: "market", label: "市场总览", sub: "货架 · 解读" },
            { key: "disposition", label: "事件与研判", sub: "审批 · 执行" },
            { key: "loop", label: "对齐与回收", sub: "映射 · 观察" },
          ]}
        />
        <div className="row gap-10 wrap">
          <label className="row gap-6 muted" style={{ fontSize: 12 }}>
            <input type="checkbox" checked={auto} onChange={(event) => setAuto(event.target.checked)} />
            自动研判
          </label>
          <button className="btn sm ghost" onClick={() => void reload()}>刷新</button>
        </div>
      </div>

      {view === "market" && (
        <div className="stack gap-16 fade-in">
      <div className="grid g6">
        <div className="kpi">
          <span className="glow" style={{ background: "#5be1ff" }} />
          <span className="kpi-label">我方价</span>
          <span className="kpi-value" style={{ color: "var(--cyan)", textShadow: "0 0 24px rgba(91,225,255,.45)" }}>
            {myPrice == null ? "—" : `¥${myPrice}`}
          </span>
          <span className="muted" style={{ fontSize: 11 }}>{dash.compare.length} 个竞品在架</span>
          <Sparkline values={dash.trend.map((item) => item.count)} />
        </div>
        <div className="kpi">
          <span className="glow" style={{ background: "#ff7a9c" }} />
          <span className="kpi-label">击穿价格带</span>
          <span className="kpi-value" style={{ color: "var(--rose)" }}>{breaches}</span>
          <span className="muted" style={{ fontSize: 11 }}>低于我方 95%</span>
        </div>
        <div className="kpi">
          <span className="glow" style={{ background: "#ffc46b" }} />
          <span className="kpi-label">待审批</span>
          <span className="kpi-value">{pending}</span>
          <span className="muted" style={{ fontSize: 11 }}>人工确认入口</span>
        </div>
        <div className="kpi">
          <span className="glow" style={{ background: "#ff7a9c" }} />
          <span className="kpi-label">L3 事件</span>
          <span className="kpi-value" style={{ color: l3 ? "var(--rose)" : undefined }}>{l3}</span>
          <span className="muted" style={{ fontSize: 11 }}>最高优先级</span>
        </div>
        <div className="kpi">
          <span className="glow" style={{ background: "#9b7bff" }} />
          <span className="kpi-label">模型调用</span>
          <span className="kpi-value">{num(metrics?.calls ?? 0)}</span>
          <span className="muted" style={{ fontSize: 11 }}>24h · P95 {metrics?.p95_latency_ms ?? "—"}ms</span>
        </div>
        <div className="kpi">
          <span className="glow" style={{ background: "#4ef2c0" }} />
          <span className="kpi-label">评测准确率</span>
          <span className="kpi-value" style={{ color: "var(--mint)" }}>{accuracy == null ? "—" : pct(accuracy)}</span>
          <span className="muted" style={{ fontSize: 11 }}>
            {gates?.latest_eval ? `${gates.latest_eval.passed}/${gates.latest_eval.total}` : "尚无评测"}
          </span>
        </div>
      </div>

      <div className="stack gap-16">
        <Panel
          title="实时货架"
          sub={`${dash.compare.length} 件在售 · 今日 ${dash.trend.at(-1)?.count ?? 0} 事件`}
          right={<span className="badge cyan">{target?.title ?? "全部竞品"}</span>}
        >
          <Shelf
            perRow={9}
            items={dash.compare.map((item) => ({
              id: item.id,
              title: item.title,
              mine: item.my_price,
              theirs: item.point,
              delta: item.delta,
              severity: item.severity,
            }))}
            myPrice={myPrice}
            selectedId={target?.id}
            onSelect={pickTarget}
          />
          <div className="row between wrap gap-10 mt-16">
            <span className="stack gap-4">
              <span className="muted" style={{ fontSize: 10.5 }}>竞品到手价</span>
              <span className="mono" style={{ fontSize: 17 }}>{target ? money(target.point) : "—"}</span>
            </span>
            <span className="stack gap-4">
              <span className="muted" style={{ fontSize: 10.5 }}>较上次</span>
              <Delta value={target?.delta ?? 0} inverted />
            </span>
            <span className="stack gap-4">
              <span className="muted" style={{ fontSize: 10.5 }}>价格区间</span>
              <span className="mono" style={{ fontSize: 13 }}>
                {target?.price_low != null ? `¥${target.price_low}–${target.price_high}` : "—"}
              </span>
            </span>
            <span className="stack gap-4">
              <span className="muted" style={{ fontSize: 10.5 }}>最近采集</span>
              <span className="mono" style={{ fontSize: 12 }}>{target?.last_ts ? ts(target.last_ts) : "—"}</span>
            </span>
          </div>
        </Panel>

        <Panel
          title="AI 市场解读"
          sub="模型只写解释，动作由确定性策略给出"
          right={<span className={`badge ${insight?.mode === "llm" ? "violet" : ""}`}>{insight?.mode === "llm" ? "模型解读" : "规则兜底"}</span>}
        >
          {insightLoading && !insight ? (
            <Loading rows={3} />
          ) : !insight ? (
            <Empty text="暂无解读" />
          ) : (
            <div className="stack gap-10">
              {insight.insights.map((text, index) => (
                <div className="driver" key={index} style={{ gridTemplateColumns: "auto 1fr" }}>
                  <span className="badge cyan" style={{ fontSize: 9.5 }}>{index + 1}</span>
                  <span style={{ fontSize: 12.5, lineHeight: 1.55 }}>{text}</span>
                </div>
              ))}
              <div className="row between muted" style={{ fontSize: 10.5 }}>
                <span>{insight.cached ? "缓存解读 · 5 分钟刷新" : "实时生成"}</span>
                <span>{ts(dash.generated_at)}</span>
              </div>
            </div>
          )}
        </Panel>
      </div>
        </div>
      )}

      {view === "disposition" && (
        <div className="stack gap-16 fade-in">
          <div className="row between wrap gap-10">
            <Seg
              value={tab}
              onChange={setTab}
              items={[
                { key: "all", label: "全部事件" },
                { key: "todo", label: "待审批" },
                { key: "done", label: "已执行" },
              ]}
            />
            <span className="muted" style={{ fontSize: 11 }}>{rows.length} 条事件 · 点选后研判</span>
          </div>

      <div className="grid g3">
        <Panel title="事件与处置" sub={`${rows.length} 条 · 点选后研判`} right={<StatusBadge value={tab === "todo" ? "submitted" : tab === "done" ? "executed" : "ok"} />}>
          {rows.length === 0 ? (
            <Empty text="没有符合条件的事件" />
          ) : (
            <div className="stack gap-6" style={{ maxHeight: 470, overflowY: "auto" }}>
              {rows.slice(0, 40).map((event) => {
                const suggestion = suggestionByEvent[event.id];
                return (
                  <button
                    key={event.id}
                    type="button"
                    className="driver event-row"
                    onClick={() => pickEvent(event)}
                    style={{
                      gridTemplateColumns: "1fr auto",
                      textAlign: "left",
                      cursor: "pointer",
                      borderColor: selected?.id === event.id ? "rgba(91,225,255,.45)" : undefined,
                    }}
                  >
                    <span className="stack" style={{ lineHeight: 1.35, minWidth: 0 }}>
                      <span style={{ fontSize: 12.5, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {event.target_title ?? event.target_id}
                      </span>
                      <span className="muted" style={{ fontSize: 10.5 }}>
                        {eventText(event.type)} · {ts(event.ts)}
                      </span>
                    </span>
                    <span className="row gap-6">
                      <SeverityBadge value={event.severity} />
                      {suggestion ? (
                        <span className="badge violet" style={{ fontSize: 9.5 }}>{actionText(suggestion.action)}</span>
                      ) : busyId === event.id ? (
                        <span className="badge amber" style={{ fontSize: 9.5 }}>研判中</span>
                      ) : (
                        <span className="badge" style={{ fontSize: 9.5 }}>待研判</span>
                      )}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </Panel>

        <Panel
          title="AI 研判"
          sub={selected ? `${selected.target_title ?? selected.target_id} · ${eventText(selected.type)}` : "选择一条事件"}
          right={
            selected && (
              <button className="btn sm ghost" disabled={busyId === selected.id} onClick={() => void analyze(selected.id)}>
                {busyId === selected.id ? "研判中…" : selectedSuggestion ? "重新研判" : "立即研判"}
              </button>
            )
          }
        >
          {!selected ? (
            <Empty text="左侧选择一条事件" />
          ) : busyId === selected.id ? (
            <Loading rows={4} />
          ) : !selectedSuggestion ? (
            <Empty text="还没有研判结果，点右上角「立即研判」" />
          ) : (
            <div className="stack gap-10">
              <div className="row wrap gap-6">
                <span className="badge violet">{actionText(selectedSuggestion.action)}</span>
                <StatusBadge value={selectedSuggestion.status} />
                <span className="badge cyan">置信 {pct(selectedSuggestion.confidence)}</span>
                {risk && <span className={`badge ${risk.level === "high" ? "rose" : "amber"}`}>风险 {risk.level}</span>}
              </div>
              <p className="soft" style={{ margin: 0, fontSize: 13, lineHeight: 1.6 }}>{selectedSuggestion.narrative}</p>

              <div className="grid g2" style={{ gap: 8 }}>
                {[
                  ["目标价", money(selectedSuggestion.target_price)],
                  ["目标毛利", selectedSuggestion.margin_at_target == null ? "—" : pct(selectedSuggestion.margin_at_target)],
                  ["护栏", selectedSuggestion.guardrail || "—"],
                  ["证据", String(detail?.evidence_docs?.length ?? selected.evidence.length)],
                ].map(([label, value]) => (
                  <div className="driver" key={label} style={{ gridTemplateColumns: "1fr auto" }}>
                    <span className="muted" style={{ fontSize: 10.5 }}>{label}</span>
                    <span className="mono" style={{ fontSize: 12 }}>{value}</span>
                  </div>
                ))}
              </div>

              {risk?.reason && <span className="muted" style={{ fontSize: 10.5 }}>· {risk.reason}</span>}

              <div className="row wrap gap-6">
                <button
                  className="btn sm primary"
                  disabled={selectedSuggestion.status !== "submitted"}
                  onClick={() => void suggestionAction(() => api.post(`/api/suggestions/${selectedSuggestion.id}/approve`, {}), "已批准")}
                >
                  批准
                </button>
                <button
                  className="btn sm ghost"
                  disabled={selectedSuggestion.status !== "submitted"}
                  onClick={() => void suggestionAction(() => api.post(`/api/suggestions/${selectedSuggestion.id}/reject`, {}), "已拒绝")}
                >
                  拒绝
                </button>
                <button
                  className="btn sm ghost"
                  disabled={selectedSuggestion.status !== "pending"}
                  onClick={() => void suggestionAction(() => api.post(`/api/suggestions/${selectedSuggestion.id}/submit`, {}), "已提交审批")}
                >
                  提交
                </button>
                <button
                  className="btn sm ghost"
                  disabled={selectedSuggestion.status !== "approved"}
                  onClick={() =>
                    void suggestionAction(
                      () => api.post(`/api/suggestions/${selectedSuggestion.id}/execute`, { executed_price: selectedSuggestion.target_price ?? undefined }),
                      "已执行",
                    )
                  }
                >
                  执行
                </button>
                <button className="btn sm ghost" onClick={() => void previewExecution()}>预览</button>
                {executions.length > 0 && (
                  <button className="btn sm ghost" onClick={() => void suggestionAction(() => api.post(`/api/executions/${executions[0].id}/rollback`), "已回滚")}>
                    回滚
                  </button>
                )}
              </div>

              {preview && (
                <div className="driver" style={{ gridTemplateColumns: "1fr auto" }}>
                  <span className="muted" style={{ fontSize: 10.5 }}>执行预览 · {preview.plan.mode} · {preview.plan.guardrail}</span>
                  <span className="mono" style={{ fontSize: 12 }}>
                    {money(preview.plan.from_price)} → {money(preview.plan.to_price)}
                  </span>
                </div>
              )}

              {timeline.length > 0 && (
                <div className="timeline">
                  {timeline.slice(-5).map((row) => (
                    <div className="tl-item" key={row.id}>
                      <div className="row between">
                        <span style={{ fontSize: 12, fontWeight: 600 }}>{row.action}</span>
                        <span className="muted mono" style={{ fontSize: 9.5 }}>{ts(row.at)}</span>
                      </div>
                      <div className="muted" style={{ fontSize: 10.5 }}>
                        {row.note || `${row.from_status ?? "—"} → ${row.to_status ?? "—"}`} · {row.actor}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {detail?.evidence_docs && detail.evidence_docs.length > 0 && (
                <div className="row wrap gap-6">
                  <span className="eyebrow">证据</span>
                  {detail.evidence_docs.slice(0, 4).map((doc) => (
                    <span className="evidence" key={doc.id}>{doc.doc_title ?? doc.doc_id} · #{doc.chunk_no}</span>
                  ))}
                </div>
              )}

              {eventDetail?.similar_cases && eventDetail.similar_cases.length > 0 && (
                <div className="stack gap-6">
                  <span className="eyebrow">相似案例</span>
                  {eventDetail.similar_cases.slice(0, 2).map((item) => (
                    <div className="driver" key={item.id} style={{ gridTemplateColumns: "1fr auto" }}>
                      <span style={{ fontSize: 11.5 }}>{item.summary}</span>
                      <span className="muted" style={{ fontSize: 10 }}>{item.outcome_7d ?? "—"}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </Panel>

        <Panel
          title="价格带走势"
          sub={target ? `${target.title} · 低/高到手价` : "选择竞品"}
          right={<span className="badge">{prices.length} 个价格点</span>}
        >
          <div className="row wrap gap-6" style={{ marginBottom: 10 }}>
            {dash.compare.slice(0, 5).map((item) => (
              <button
                key={item.id}
                className={`btn sm ${target?.id === item.id ? "primary" : "ghost"}`}
                onClick={() => pickTarget(item.id)}
              >
                {shortId(item.title, 6)}
              </button>
            ))}
          </div>
          <PriceBand points={prices} mine={myPrice} />
          <div className="row between wrap gap-10 mt-12">
            <span className="stack gap-4">
              <span className="muted" style={{ fontSize: 10 }}>置信度</span>
              <span className="mono" style={{ fontSize: 12 }}>
                {prices.at(-1)?.confidence != null ? pct(prices.at(-1)?.confidence) : "—"}
              </span>
            </span>
            <span className="stack gap-4">
              <span className="muted" style={{ fontSize: 10 }}>SKU</span>
              <span className="mono" style={{ fontSize: 12 }}>{target?.my_sku ?? "未映射"}</span>
            </span>
            <span className="stack gap-4">
              <span className="muted" style={{ fontSize: 10 }}>实验</span>
              <span className="mono" style={{ fontSize: 12 }}>{target?.holdout ? "观察组" : "对照组"}</span>
            </span>
          </div>
        </Panel>
      </div>
        </div>
      )}

      {view === "loop" && (
        <div className="stack gap-16 fade-in">
      <div className="grid g3">
        <Panel
          title="SKU 对齐"
          sub="竞品与我方商品映射；确认后同步我方价"
          right={<button className="btn sm ghost" disabled={mappingBusy === "suggest"} onClick={() => void suggestMappings()}>{mappingBusy === "suggest" ? "生成中…" : "生成建议"}</button>}
        >
          {data.mappings.length === 0 ? (
            <Empty text="还没有映射，点「生成建议」自动对齐" />
          ) : (
            <div className="stack gap-6">
              {data.mappings.slice(0, 6).map((mapping) => (
                <div className="driver" key={mapping.id} style={{ gridTemplateColumns: "1fr auto" }}>
                  <span className="stack" style={{ lineHeight: 1.3, minWidth: 0 }}>
                    <span style={{ fontSize: 12, fontWeight: 600 }}>{mapping.my_title ?? mapping.my_sku}</span>
                    <span className="muted" style={{ fontSize: 10 }}>
                      ↔ {mapping.target_title ?? mapping.target_id}
                      {mapping.score != null ? ` · ${(mapping.score * 100).toFixed(0)}%` : ""}
                    </span>
                  </span>
                  {mapping.status === "pending" ? (
                    <span className="row gap-4">
                      <button className="btn sm ghost" disabled={mappingBusy === mapping.id} onClick={() => void decideMapping(mapping, "confirmed")}>确认</button>
                      <button className="btn sm ghost" onClick={() => void decideMapping(mapping, "rejected")}>驳回</button>
                    </span>
                  ) : (
                    <StatusBadge value={mapping.status} />
                  )}
                </div>
              ))}
            </div>
          )}

          {target && (
            <>
              <div className="divider mt-16" />
              <div className="row wrap gap-8 mt-12" style={{ alignItems: "flex-end" }}>
                <div className="field" style={{ width: 120 }}>
                  <label>我方价</label>
                  <input className="input" value={myPriceDraft} onChange={(event) => setMyPriceDraft(event.target.value)} inputMode="decimal" />
                </div>
                <label className="row gap-6 muted" style={{ fontSize: 11.5, paddingBottom: 10 }}>
                  <input type="checkbox" checked={holdoutDraft} onChange={(event) => setHoldoutDraft(event.target.checked)} />
                  观察组
                </label>
                <button className="btn sm primary" disabled={mappingBusy === "target"} onClick={() => void saveTarget()}>
                  {mappingBusy === "target" ? "保存中…" : "保存竞品设置"}
                </button>
                <span className="muted" style={{ fontSize: 10.5, paddingBottom: 10 }}>
                  {target.my_sku ?? "未映射"} · {target.platform}
                </span>
              </div>
            </>
          )}
        </Panel>

        <Panel
          title="结果回收"
          sub="执行 7 天后观察；改善会沉淀为案例"
          right={<span className={`badge ${data.overdue.length ? "amber" : "mint"}`}>{data.overdue.length} 条逾期</span>}
        >
          {data.due.length === 0 ? (
            <Empty text="没有待回收的建议" />
          ) : (
            <div className="stack gap-6">
              {data.due.slice(0, 5).map((row) => (
                <button
                  key={row.id}
                  type="button"
                  className="driver"
                  style={{ gridTemplateColumns: "1fr auto", textAlign: "left", cursor: "pointer" }}
                  onClick={() => {
                    setSelectedTargetId(row.target_id ?? "");
                    setSelectedEventId(row.event_id);
                  }}
                >
                  <span className="stack" style={{ lineHeight: 1.3 }}>
                    <span style={{ fontSize: 12 }}>{row.target_title ?? row.target_id ?? row.id.slice(0, 6)}</span>
                    <span className="muted" style={{ fontSize: 10 }}>
                      {actionText(row.action)} · {row.observed?.point != null ? `现价 ¥${row.observed.point}` : "待观察"}
                    </span>
                  </span>
                  <span className={`badge ${row.due ? "amber" : ""}`} style={{ fontSize: 9.5 }}>
                    {row.due ? `逾期 ${Math.abs(row.days_overdue).toFixed(0)}d` : `${Math.max(0, -row.days_overdue).toFixed(0)}d 后`}
                  </span>
                </button>
              ))}
            </div>
          )}

          {selectedSuggestion && ["executed", "accepted", "holdout"].includes(selectedSuggestion.status) && (
            <>
              <div className="divider mt-16" />
              <div className="row between mt-12">
                <span className="eyebrow">记录当前建议结果</span>
                <span className={`badge ${outcome ? "mint" : ""}`} style={{ fontSize: 9.5 }}>
                  {outcome ? `${outcome.result} · ${ts(outcome.recorded_at)}` : "未回收"}
                </span>
              </div>
              <div className="row gap-8 mt-8 wrap">
                <select className="input" style={{ width: 110 }} value={outcomeResult} onChange={(event) => setOutcomeResult(event.target.value)}>
                  <option value="improved">改善</option>
                  <option value="unchanged">无变化</option>
                  <option value="worse">变差</option>
                </select>
                <input className="input" style={{ flex: 1, minWidth: 120 }} placeholder="备注（可选）" value={outcomeNote} onChange={(event) => setOutcomeNote(event.target.value)} />
                <button className="btn sm primary" onClick={() => void recordOutcome()}>记录</button>
              </div>
            </>
          )}

          {holdout && (
            <div className="row between muted mt-12" style={{ fontSize: 10.5 }}>
              <span>执行组提升 {holdout.treatment.improvement_rate == null ? "样本不足" : pct(holdout.treatment.improvement_rate)}</span>
              <span>观察组 {holdout.control.improvement_rate == null ? "样本不足" : pct(holdout.control.improvement_rate)}</span>
            </div>
          )}
        </Panel>

        <Panel title="研判漏斗" sub="事件 → 建议 → 待审 → 执行">
          <div className="stack gap-8">
            {[
              ["事件", events.length, "#5be1ff"],
              ["建议", suggestions.length, "#9b7bff"],
              ["待审批", pending, "#ffc46b"],
              ["已执行", dash.status.executed ?? 0, "#4ef2c0"],
            ].map(([label, value, color]) => (
              <div className="row between gap-8" key={label as string} style={{ fontSize: 11 }}>
                <span className="muted" style={{ width: 40 }}>{label}</span>
                <span className="meter" style={{ flex: 1 }}><i style={{ width: `${Math.max(5, (Number(value) / Math.max(1, events.length)) * 100)}%`, background: color as string }} /></span>
                <span className="mono" style={{ width: 30, textAlign: "right" }}>{value}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
        </div>
      )}

      <QAWidget
        context={
          target
            ? `${target.title}：竞品到手价 ${target.point ?? "—"} 元，我方价 ${target.my_price ?? "—"} 元`
            : undefined
        }
      />
    </div>
  );
}
