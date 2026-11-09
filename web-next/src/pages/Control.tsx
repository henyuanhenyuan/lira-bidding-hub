import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { endpoints } from "../core/api";
import { clock, money, pct, signedPct, STATUS_TEXT, timeAgo, ACTION_TEXT } from "../core/format";
import { useAsync, useToast } from "../core/hooks";
import { useLive } from "../core/live";
import type { AgentRun, ExceptionItem } from "../core/types";
import { Btn, Chip, Empty, Panel, Skeleton, Stat, Toast } from "../ui/atoms";
import { Icon } from "../ui/icons";
import { FlowTopology, RegionMosaic, Spark } from "../ui/visuals";

export default function Control() {
  const navigate = useNavigate();
  const { message, push } = useToast();
  const [region, setRegion] = useState<string>("");
  const [busyId, setBusyId] = useState<string | null>(null);

  const dash = useAsync(() => endpoints.dashboard(7, region || undefined), [region], { pollMs: 20000 });
  const exc = useAsync(() => endpoints.exceptions(), [], { pollMs: 15000 });
  const runs = useAsync(() => endpoints.runs(8), [], { pollMs: 15000 });
  const insights = useAsync(() => endpoints.insights(), [], { pollMs: 60000 });
  const ops = useAsync(() => endpoints.ops(), [], { pollMs: 30000 });
  const { events, connected } = useLive(14);

  const lastEvent = events[0]?.id;
  useEffect(() => {
    if (!lastEvent) return;
    dash.reload();
    exc.reload();
    runs.reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastEvent]);

  const data = dash.data;
  const exceptions = exc.data?.items ?? [];
  const runList = runs.data ?? [];

  const trend = useMemo(() => (data?.trend ?? []).map((t) => t.count), [data]);
  const eventTotal = useMemo(
    () => Object.values(data?.severity ?? {}).reduce((sum, n) => sum + n, 0),
    [data],
  );
  const autoCount = (data?.status.executed ?? 0) + (data?.autopilot?.auto_executed ?? 0);
  const targets = data?.compare?.length ?? 0;
  const fresh = ops.data?.freshness;

  async function resolve(item: ExceptionItem, approve: boolean) {
    setBusyId(item.id);
    try {
      await endpoints.resolveException(item.id, {
        approve,
        note: approve ? "人工确认放行" : "人工驳回",
      });
      push(approve ? "已确认，Agent 继续执行" : "已驳回，Agent 重新研判", "ok");
      exc.reload();
      dash.reload();
    } catch (err) {
      push(err instanceof Error ? err.message : "操作失败", "error");
    } finally {
      setBusyId(null);
    }
  }

  async function tick() {
    try {
      await endpoints.autopilotTick();
      push("已触发一轮 Agent 巡检", "ok");
      runs.reload();
      exc.reload();
    } catch (err) {
      push(err instanceof Error ? err.message : "触发失败", "error");
    }
  }

  return (
    <>
      <div className="grid g4">
        <Stat
          label="今日自主成交"
          accent="cyan"
          value={autoCount.toLocaleString("zh-CN")}
          hint={`Agent 全自动闭环 · 共 ${targets} 个在盯目标`}
        >
          <Spark values={trend.length ? trend : [0, 1, 1, 2, 2, 3]} height={34} />
        </Stat>
        <Stat
          label="待人工确认"
          accent="amber"
          value={exceptions.length}
          hint="仅异常需人工 · 其余自动执行"
        />
        <Stat
          label="价格事件"
          accent="violet"
          value={eventTotal}
          hint={`高危 ${data?.severity.L3 ?? 0} · 关注 ${data?.severity.L2 ?? 0}`}
        />
        <Stat
          label="采集新鲜度"
          accent={fresh?.stale ? "rose" : "green"}
          value={fresh ? `${fresh.lag_hours.toFixed(1)}h` : "—"}
          hint={
            fresh
              ? fresh.stale
                ? `已超出 SLA ${fresh.sla_hours}h`
                : `SLA ${fresh.sla_hours}h 内`
              : "等待采集回传"
          }
        />
      </div>

      <div className="dash">
        <div className="stack">
          <Panel
            title="Agent 运行流"
            eyebrow="Autonomous Loop"
            tone="cyan"
            extra={
              <>
                <Chip tone={connected ? "green" : "amber"}>{connected ? "实时" : "离线"}</Chip>
                <Btn size="sm" onClick={() => void tick()}>
                  <Icon name="play" size={13} />
                  巡检一轮
                </Btn>
              </>
            }
          >
            <FlowTopology active={connected} />
            <div className="rows mt16">
              {runs.loading && !runList.length ? (
                [0, 1, 2].map((i) => <Skeleton key={i} height={58} />)
              ) : runList.length ? (
                runList.slice(0, 6).map((run) => <RunRow key={run.id} run={run} />)
              ) : (
                <Empty>Agent 尚未运行，点击「巡检一轮」触发</Empty>
              )}
            </div>
          </Panel>

          <Panel
            title="区域矩阵"
            eyebrow="Region Matrix"
            extra={
              <select
                className="select"
                style={{ width: 130, padding: "6px 10px", fontSize: 12 }}
                value={region}
                onChange={(e) => setRegion(e.target.value)}
              >
                <option value="">全部地区</option>
                {(data?.regions ?? []).map((r) => (
                  <option key={r.region} value={r.region}>
                    {r.region}
                  </option>
                ))}
              </select>
            }
          >
            {data?.regions?.length ? (
              <RegionMosaic
                regions={data.regions}
                active={region}
                onPick={(value) => setRegion(value === region ? "" : value)}
              />
            ) : (
              <Empty>暂无区域数据</Empty>
            )}
          </Panel>

          <Panel
            title="竞价流水"
            eyebrow="Bid Ledger"
            extra={
              <Btn size="sm" onClick={() => navigate("/bidding")}>
                查看竞价台
                <Icon name="chevron" size={13} />
              </Btn>
            }
          >
            <div className="ticker">
              {(data?.autopilot?.ledger ?? []).slice(0, 9).map((item) => (
                <div className="ticker-row" key={item.id}>
                  <span className="ticker-time num">{clock(item.ts)}</span>
                  <span className="ticker-main">
                    <strong>{ACTION_TEXT[item.action] || item.action}</strong>
                    <span className="muted"> · {item.region || "全国"} · {item.strategy || "跟随"}</span>
                  </span>
                  <span className="ticker-price num">
                    {money(item.from_price)} → {money(item.to_price)}
                  </span>
                  <span className={`num small ${(item.delta_pct ?? 0) < 0 ? "delta-down" : "delta-up"}`}>
                    {signedPct(item.delta_pct)}
                  </span>
                </div>
              ))}
              {!data?.autopilot?.ledger?.length && <Empty>暂无调价流水</Empty>}
            </div>
          </Panel>
        </div>

        <div className="stack">
          <Panel
            title="待人工确认"
            eyebrow="Human in the loop"
            tone="amber"
            extra={<Chip tone="amber">{exceptions.length} 项</Chip>}
          >
            <div className="stack" style={{ gap: 10 }}>
              {exceptions.length ? (
                exceptions.slice(0, 3).map((item) => (
                  <div className="alert-card" key={item.id}>
                    <div className="spread">
                      <strong style={{ fontSize: 13 }}>{item.target_title}</strong>
                      <Chip tone="amber">{item.region}</Chip>
                    </div>
                    <div className="reason">{item.exception_reason || item.guardrail_note || "需人工判断"}</div>
                    <div className="row small muted">
                      <span>建议 {money(item.target_price)}</span>
                      <span>· 置信度 {pct(item.confidence, 0)}</span>
                      <span>· {timeAgo(item.created_at)}</span>
                    </div>
                    <div className="row">
                      <Btn
                        size="sm"
                        tone="primary"
                        disabled={busyId === item.id}
                        onClick={() => void resolve(item, true)}
                      >
                        <Icon name="check" size={13} />
                        确认
                      </Btn>
                      <Btn
                        size="sm"
                        tone="danger"
                        disabled={busyId === item.id}
                        onClick={() => void resolve(item, false)}
                      >
                        <Icon name="close" size={13} />
                        驳回
                      </Btn>
                    </div>
                  </div>
                ))
              ) : (
                <Empty>没有待确认项，Agent 全自动运行中</Empty>
              )}
              {exceptions.length > 3 && (
                <Btn size="sm" onClick={() => navigate("/bidding")}>
                  还有 {exceptions.length - 3} 项 · 去竞价台处理
                </Btn>
              )}
            </div>
          </Panel>

          <Panel title="情报洞察" eyebrow="Agent Insights" tone="violet">
            <div className="stack" style={{ gap: 10 }}>
              {(insights.data?.insights ?? []).slice(0, 4).map((text, i) => (
                <div className="row" key={i} style={{ alignItems: "flex-start", flexWrap: "nowrap" }}>
                  <span className={`dot ${i === 0 ? "rose" : i === 1 ? "amber" : "cyan"}`} style={{ marginTop: 6 }} />
                  <span style={{ fontSize: 12.5, color: "var(--ink-2)" }}>{text}</span>
                </div>
              ))}
              {!insights.data?.insights?.length && <Empty>暂无洞察</Empty>}
            </div>
          </Panel>

          <Panel title="系统脉搏" eyebrow="System Pulse">
            <dl className="kv">
              <dt>模型通道</dt>
              <dd>Qwen-Plus · 竞价微调</dd>
              <dt>调度</dt>
              <dd>{ops.data?.scheduler.enabled ? "运行中" : "已停止"}</dd>
              <dt>近 24h 调用</dt>
              <dd>{ops.data?.metrics.calls ?? 0} 次</dd>
              <dt>降级率</dt>
              <dd>{pct(ops.data?.metrics.fallback_rate ?? 0)}</dd>
              <dt>P95 延迟</dt>
              <dd>{ops.data?.metrics.p95_latency_ms ?? 0} ms</dd>
            </dl>
            <div className="row mt16">
              {(ops.data?.scheduler.recent ?? []).slice(0, 3).map((job, i) => (
                <Chip key={i} tone={job.status === "ok" ? "green" : "rose"}>
                  {job.kind} · {STATUS_TEXT[job.status] || job.status}
                </Chip>
              ))}
            </div>
          </Panel>
        </div>
      </div>

      <Toast message={message} />
    </>
  );
}

function RunRow({ run }: { run: AgentRun }) {
  const tone =
    run.status === "succeeded" ? "ok" : run.status === "failed" ? "fail" : "live";
  const icon = run.status === "succeeded" ? "check" : run.status === "failed" ? "close" : "spark";
  return (
    <div className="run-card">
      <span className={`run-status ${tone}`}>
        <Icon name={icon} size={16} />
      </span>
      <div className="grow" style={{ flex: 1, minWidth: 0 }}>
        <div className="title-line">{run.target_title || run.event_id.slice(0, 10)}</div>
        <div className="sub-line">
          {run.event_type || "事件"} · {run.skill_id || "默认技能"} · {run.step_count} 步 ·{" "}
          {run.latency_ms ?? 0}ms
        </div>
      </div>
      <div className="step-dots">
        {Array.from({ length: Math.min(7, Math.max(3, run.step_count)) }).map((_, i) => (
          <span key={i} className={`step-dot ${i < Math.min(6, run.step_count) ? "on" : ""}`} />
        ))}
      </div>
      <Chip tone={run.status === "succeeded" ? "green" : run.status === "failed" ? "rose" : "cyan"}>
        {STATUS_TEXT[run.status] || run.status}
      </Chip>
    </div>
  );
}
