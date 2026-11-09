import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api, ApiError } from "../core/api";
import { money, pct, ts } from "../core/format";
import { useAsync } from "../core/hooks";
import type { EventRow, Suggestion } from "../core/types";
import { Cabinet, ProductShelf } from "../ui/viz";
import { Badge, Empty, ErrorBox, Page, SeverityBadge, Spinner, Stat, StatusBadge, actionText } from "../ui/kit";

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
  trend: { date: string; count: number }[];
  severity: Record<string, number>;
  status: Record<string, number>;
}

interface InsightReply {
  insights: string[];
  mode: string;
}

interface ChatReply {
  answer: string;
  citations: { id: string; title?: string; index?: number }[];
  mode: string;
}

interface TimelineRow {
  id: string;
  action: string;
  actor: string;
  from_status?: string | null;
  to_status?: string | null;
  note?: string | null;
  at: string;
}

interface ExecutionRow {
  id: string;
  status?: string;
  to_price?: number | null;
}

export default function Workspace() {
  const { data, error, loading, reload } = useAsync(async () => {
    const [dash, events, suggestions, insights] = await Promise.all([
      api.get<Dashboard>("/api/dashboard"),
      api.get<EventRow[]>("/api/events?limit=80"),
      api.get<Suggestion[]>("/api/suggestions?limit=100"),
      api.get<InsightReply>("/api/agent/insights").catch(() => null),
    ]);
    return { dash, events, suggestions, insights };
  }, []);

  const [selectedId, setSelectedId] = useState("");
  const [tab, setTab] = useState<"all" | "todo" | "done">("all");
  const [auto, setAuto] = useState(true);
  const [busyId, setBusyId] = useState("");
  const [notice, setNotice] = useState("");
  const [chatInput, setChatInput] = useState("");
  const [chatReply, setChatReply] = useState<ChatReply | null>(null);
  const [chatBusy, setChatBusy] = useState(false);
  const [timeline, setTimeline] = useState<TimelineRow[]>([]);
  const [executions, setExecutions] = useState<ExecutionRow[]>([]);
  const [detailTick, setDetailTick] = useState(0);

  const events = data?.events ?? [];
  const suggestions = data?.suggestions ?? [];
  const dash = data?.dash;
  const insights = data?.insights;

  const suggestionByEvent = useMemo(() => {
    const map: Record<string, Suggestion> = {};
    for (const item of suggestions) if (!map[item.event_id]) map[item.event_id] = item;
    return map;
  }, [suggestions]);

  const selected = events.find((item) => item.id === selectedId) ?? events[0];
  const selectedSuggestion = selected ? suggestionByEvent[selected.id] : undefined;

  const rows = events.filter((event) => {
    const suggestion = suggestionByEvent[event.id];
    if (tab === "todo") return suggestion?.status === "submitted";
    if (tab === "done") return suggestion?.status === "executed";
    return true;
  });

  useEffect(() => {
    if (!auto || !selected || selectedSuggestion || busyId) return;
    void analyze(selected.id, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auto, selected?.id, selectedSuggestion?.id]);

  useEffect(() => {
    const sid = selectedSuggestion?.id;
    if (!sid) {
      setTimeline([]);
      setExecutions([]);
      return;
    }
    let alive = true;
    void Promise.all([
      api.get<TimelineRow[]>(`/api/suggestions/${sid}/timeline`).catch(() => []),
      api.get<ExecutionRow[]>(`/api/suggestions/${sid}/executions`).catch(() => []),
    ]).then(([rows, runs]) => {
      if (!alive) return;
      setTimeline(rows);
      setExecutions(runs);
    });
    return () => {
      alive = false;
    };
  }, [selectedSuggestion?.id, detailTick]);

  async function suggestionAction(fn: () => Promise<unknown>, done: string) {
    try {
      await fn();
      await reload();
      setDetailTick((value) => value + 1);
      setNotice(done);
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "操作失败");
    }
  }

  async function analyze(eventId: string, silent = false) {
    setBusyId(eventId);
    if (!silent) setNotice("");
    try {
      await api.post(`/api/events/${encodeURIComponent(eventId)}/analyze`);
      await reload();
      if (!silent) setNotice("研判完成");
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "研判失败");
    } finally {
      setBusyId("");
    }
  }

  async function ask() {
    const question = chatInput.trim();
    if (!question || chatBusy) return;
    setChatBusy(true);
    try {
      setChatReply(await api.post<ChatReply>("/api/agent/chat", { question }));
      setChatInput("");
    } catch (err) {
      setChatReply({ answer: err instanceof Error ? err.message : "问答失败", citations: [], mode: "error" });
    } finally {
      setChatBusy(false);
    }
  }

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!data || !dash) return null;

  const pending = dash.status.submitted ?? 0;
  const l3 = dash.severity.L3 ?? 0;
  const breaches = dash.compare.filter(
    (item) => item.my_price && item.point && item.point < item.my_price * 0.95,
  ).length;

  return (
    <Page
      title="工作区"
      desc="市场对比、事件处置与 AI 解读在同一屏完成"
      actions={
        <div className="row">
          <label className="switch">
            <input type="checkbox" checked={auto} onChange={(event) => setAuto(event.target.checked)} />
            <span>自动研判</span>
          </label>
          <Link className="btn ghost" to="/screen">
            沉浸大屏
          </Link>
        </div>
      }
    >
      {notice && <div className="notice">{notice}</div>}

      <div className="stat-grid">
        <Stat label="击穿价格带" value={breaches} hint="竞品低于我方 95%" tone={breaches ? "danger" : undefined} />
        <Stat label="待审批" value={pending} hint="等待人工确认" />
        <Stat label="L3 事件" value={l3} hint="高优先级" />
        <Stat label="在跟竞品" value={dash.compare.length} hint="实时价格对比" />
      </div>

      <div className="workspace-grid">
        <section className="card">
          <div className="card-head">
            <h2>市场货架</h2>
            <span className="card-sub">货架陈列：越高价格越高，颜色是严重度，虚线框是低于我方价</span>
          </div>
          <div className="card-body">
            <Cabinet title="在售竞品" tag={`${dash.compare.length} 件`}>
            <ProductShelf
              items={dash.compare.map((item) => ({
                id: item.id,
                title: item.title,
                mine: item.my_price,
                theirs: item.point,
                delta: item.delta,
                severity: item.severity,
              }))}
            />
            </Cabinet>
          </div>
        </section>

        <section className="card">
          <div className="card-head">
            <h2>AI 市场解读</h2>
            <span className="card-sub">实时分析价格与事件</span>
            <div className="card-extra">
              <Badge tone={insights?.mode === "llm" ? "accent" : "neutral"}>
                {insights?.mode === "llm" ? "模型" : "规则"}
              </Badge>
            </div>
          </div>
          <div className="card-body">
            {!insights ? (
              <Empty>暂无解读。</Empty>
            ) : (
              <ul className="insight-list">
                {insights.insights.map((item, index) => (
                  <li key={index}>
                    <i />
                    {item}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        <section className="card">
          <div className="card-head">
            <h2>事件与处置</h2>
            <div className="card-extra">
              <div className="chipbar" style={{ margin: 0 }}>
                {([
                  ["all", "全部"],
                  ["todo", "待审批"],
                  ["done", "已执行"],
                ] as const).map(([key, label]) => (
                  <button
                    key={key}
                    className={`chip${tab === key ? " on" : ""}`}
                    onClick={() => setTab(key)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="card-body flush">
            {rows.length === 0 ? (
              <Empty>没有符合条件的事件。</Empty>
            ) : (
              <div className="event-cards">
                {rows.slice(0, 30).map((event) => {
                  const suggestion = suggestionByEvent[event.id];
                  return (
                    <button
                      key={event.id}
                      className={`event-card${selected?.id === event.id ? " on" : ""}`}
                      onClick={() => setSelectedId(event.id)}
                    >
                      <span className={`event-edge sev-${event.severity}`} />
                      <span className="event-main">
                        <b>{event.target_title ?? event.target_id}</b>
                        <em>{event.note}</em>
                      </span>
                      <span className="event-side">
                        <SeverityBadge value={event.severity} />
                        {suggestion ? (
                          <Badge tone="accent">{actionText(suggestion.action)}</Badge>
                        ) : busyId === event.id ? (
                          <Badge tone="neutral">研判中</Badge>
                        ) : (
                          <span className="sub">待研判</span>
                        )}
                        <span className="sub">{ts(event.ts)}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </section>

        <section className="card">
          <div className="card-head">
            <h2>AI 研判</h2>
            <span className="card-sub">
              {selected ? `${selected.target_title ?? selected.target_id} · ${selected.type}` : "选择一条事件"}
            </span>
            <div className="card-extra">
              {selected && (
                <button
                  className="btn ghost sm"
                  disabled={busyId === selected.id}
                  onClick={() => void analyze(selected.id)}
                >
                  {busyId === selected.id ? "研判中…" : selectedSuggestion ? "重新研判" : "立即研判"}
                </button>
              )}
            </div>
          </div>
          <div className="card-body">
            {!selected ? (
              <Empty>左侧选择一条事件。</Empty>
            ) : busyId === selected.id ? (
              <Spinner label="Agent 正在检索证据并生成建议…" />
            ) : !selectedSuggestion ? (
              <Empty>还没有研判结果。</Empty>
            ) : (
              <>
                <div className="row" style={{ marginBottom: 8 }}>
                  <Badge tone="accent">{actionText(selectedSuggestion.action)}</Badge>
                  <StatusBadge value={selectedSuggestion.status} />
                  <span className="sub">置信 {pct(selectedSuggestion.confidence)}</span>
                </div>
                <p style={{ margin: "0 0 10px" }}>{selectedSuggestion.narrative}</p>
                <dl className="kv">
                  <dt>生成方式</dt>
                  <dd className="mono">{selectedSuggestion.generated_by}</dd>
                  <dt>目标价</dt>
                  <dd>{money(selectedSuggestion.target_price)}</dd>
                  <dt>护栏</dt>
                  <dd>{selectedSuggestion.guardrail}</dd>
                </dl>
                {timeline.length > 0 && (
                  <ul className="timeline">
                    {timeline.slice(-6).map((row) => (
                      <li key={row.id}>
                        <time>{ts(row.at)}</time>
                        <b>{row.action}</b>
                        <span>
                          {row.note || `${row.from_status ?? "—"} → ${row.to_status ?? "—"}`}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="row" style={{ marginTop: 12, flexWrap: "wrap" }}>
                  <button
                    className="btn sm"
                    disabled={selectedSuggestion.status !== "submitted"}
                    onClick={() =>
                      suggestionAction(
                        () => api.post(`/api/suggestions/${selectedSuggestion.id}/approve`, {}),
                        "已批准",
                      )
                    }
                  >
                    批准
                  </button>
                  <button
                    className="btn ghost sm"
                    disabled={selectedSuggestion.status !== "submitted"}
                    onClick={() =>
                      suggestionAction(
                        () => api.post(`/api/suggestions/${selectedSuggestion.id}/reject`, {}),
                        "已拒绝",
                      )
                    }
                  >
                    拒绝
                  </button>
                  <button
                    className="btn ghost sm"
                    disabled={selectedSuggestion.status !== "pending"}
                    onClick={() =>
                      suggestionAction(
                        () => api.post(`/api/suggestions/${selectedSuggestion.id}/submit`, {}),
                        "已提交审批",
                      )
                    }
                  >
                    提交审批
                  </button>
                  <button
                    className="btn ghost sm"
                    disabled={selectedSuggestion.status !== "approved"}
                    onClick={() =>
                      suggestionAction(
                        () =>
                          api.post(`/api/suggestions/${selectedSuggestion.id}/execute`, {
                            executed_price: selectedSuggestion.target_price ?? undefined,
                          }),
                        "已执行",
                      )
                    }
                  >
                    执行
                  </button>
                  {executions.length > 0 && (
                    <button
                      className="btn ghost sm"
                      onClick={() =>
                        suggestionAction(
                          () => api.post(`/api/executions/${executions[0].id}/rollback`),
                          "已回滚",
                        )
                      }
                    >
                      回滚
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        </section>

        <section className="card">
          <div className="card-head">
            <h2>问 Agent</h2>
            <span className="card-sub">基于知识库回答，附引用</span>
          </div>
          <div className="card-body">
            <div className="row" style={{ marginBottom: 10 }}>
              <input
                className="input"
                style={{ flex: 1 }}
                placeholder="例如：价格带击穿的判定标准是什么？"
                value={chatInput}
                onChange={(event) => setChatInput(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && void ask()}
              />
              <button className="btn" disabled={chatBusy} onClick={() => void ask()}>
                {chatBusy ? "思考中…" : "提问"}
              </button>
            </div>
            {!chatReply ? (
              <p className="hint" style={{ margin: 0 }}>
                AI 已接入工作区：实时解读市场，选事件自动研判。
              </p>
            ) : (
              <div className="chat-answer">
                <p style={{ marginTop: 0, whiteSpace: "pre-wrap" }}>{chatReply.answer}</p>
                {chatReply.citations.length > 0 && (
                  <div className="row">
                    {chatReply.citations.map((item) => (
                      <span className="badge neutral" key={item.id}>
                        {item.index ? `${item.index}. ` : ""}
                        {item.title ?? item.id}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </section>
      </div>
    </Page>
  );
}
