import { useEffect, useMemo, useState } from "react";

import { endpoints } from "../core/api";
import {
  ACTION_TEXT,
  clock,
  money,
  pct,
  signedPct,
  STRATEGY_TEXT,
  severityClass,
  STATUS_TEXT,
  timeAgo,
} from "../core/format";
import { useAsync, useToast } from "../core/hooks";
import type { CompareRow, ExceptionItem } from "../core/types";
import { Btn, Chip, Empty, Panel, Skeleton, Toast, Toggle } from "../ui/atoms";
import { Icon } from "../ui/icons";
import { PriceLadder, Spark } from "../ui/visuals";

const STRATEGIES = ["follow", "undercut", "match_band", "hold"];

export default function Bidding() {
  const { message, push } = useToast();
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const dash = useAsync(() => endpoints.dashboard(7), [], { pollMs: 20000 });
  const exc = useAsync(() => endpoints.exceptions(), [], { pollMs: 15000 });
  const ledger = useAsync(() => endpoints.ledger(20), [], { pollMs: 20000 });
  const status = useAsync(() => endpoints.autopilotStatus(), [], { pollMs: 20000 });

  const rows = dash.data?.compare ?? [];
  const exceptions = exc.data?.items ?? [];
  const current = useMemo(
    () => rows.find((r) => r.id === (selected ?? rows[0]?.id)) ?? null,
    [rows, selected],
  );
  const history = useAsync(
    () => (current ? endpoints.prices(current.id, 40) : Promise.resolve([])),
    [current?.id],
  );

  useEffect(() => {
    if (!selected && rows.length) setSelected(rows[0].id);
  }, [rows, selected]);

  async function toggleAuto(next: boolean) {
    try {
      await endpoints.autopilotConfig({ enabled: next });
      status.reload();
      push(next ? "自主竞价已开启" : "自主竞价已暂停", next ? "ok" : "warn");
    } catch (err) {
      push(err instanceof Error ? err.message : "设置失败", "error");
    }
  }

  async function runAgent(row: CompareRow) {
    setBusy(row.id);
    try {
      await endpoints.autopilotRun(row.id);
      push(`Agent 已接管「${row.title}」，自动研判中`, "ok");
      dash.reload();
      ledger.reload();
    } catch (err) {
      push(err instanceof Error ? err.message : "触发失败", "error");
    } finally {
      setBusy(null);
    }
  }

  async function changeStrategy(row: CompareRow, strategy: string) {
    try {
      await endpoints.patchTarget(row.id, { pricing_strategy: strategy });
      push("策略已更新", "ok");
      dash.reload();
    } catch (err) {
      push(err instanceof Error ? err.message : "更新失败", "error");
    }
  }

  async function resolve(item: ExceptionItem, approve: boolean) {
    setBusy(item.id);
    try {
      await endpoints.resolveException(item.id, {
        approve,
        note: approve ? "人工确认放行" : "人工驳回",
      });
      push(approve ? "已确认放行" : "已驳回", "ok");
      exc.reload();
      dash.reload();
    } catch (err) {
      push(err instanceof Error ? err.message : "操作失败", "error");
    } finally {
      setBusy(null);
    }
  }

  const auto = status.data?.config.enabled ?? false;

  return (
    <>
      <Panel
        title="自主竞价"
        eyebrow="Autonomous bidding"
        tone="cyan"
        extra={
          <>
            <Chip tone={auto ? "green" : "amber"}>{auto ? "自动执行中" : "已暂停"}</Chip>
            <Toggle checked={auto} onChange={(v) => void toggleAuto(v)} label="Agent 自主调价" />
          </>
        }
      >
        <div className="grid g4">
          <MiniStat label="自动执行" value={status.data?.counts.auto_executed ?? 0} tone="green" />
          <MiniStat label="自动保留" value={status.data?.counts.auto_held ?? 0} tone="cyan" />
          <MiniStat label="异常待确认" value={status.data?.counts.exceptions ?? 0} tone="amber" />
          <MiniStat label="人工待办" value={status.data?.counts.manual_pending ?? 0} tone="violet" />
        </div>
        <div className="row mt16 small muted">
          <span>策略 {STRATEGY_TEXT[status.data?.config.strategy || "follow"]}</span>
          <span>· 跟降 {pct(status.data?.config.undercut_pct ?? 0.02)}</span>
          <span>· 最大幅度 {pct(status.data?.config.max_delta_pct ?? 0.15)}</span>
          <span>· 置信阈值 {pct(status.data?.config.min_confidence ?? 0.8)}</span>
        </div>
      </Panel>

      <div className="dash">
        <Panel
          title="目标池"
          eyebrow="Targets"
          extra={<Chip tone="cyan">{rows.length} 个</Chip>}
          padded
        >
          <div style={{ overflowX: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th>目标</th>
                  <th>地区</th>
                  <th className="right">我方价</th>
                  <th>竞品区间</th>
                  <th className="right">价差</th>
                  <th>策略</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {dash.loading && !rows.length
                  ? [0, 1, 2, 3].map((i) => (
                      <tr key={i}>
                        <td colSpan={7}>
                          <Skeleton height={22} />
                        </td>
                      </tr>
                    ))
                  : rows.map((row) => (
                      <tr
                        key={row.id}
                        onClick={() => setSelected(row.id)}
                        style={{ cursor: "pointer" }}
                      >
                        <td>
                          <div className="title-line" style={{ maxWidth: 190 }}>
                            {row.title}
                          </div>
                          <div className="sub-line">
                            <span className={severityClass(row.severity)}>{row.severity || "—"}</span>
                            <span className="muted"> · {row.my_sku || "未绑定"}</span>
                          </div>
                        </td>
                        <td>{row.region}</td>
                        <td className="right num">{money(row.my_price)}</td>
                        <td className="num muted">
                          {row.price_low !== null && row.price_high !== null
                            ? `${row.price_low.toFixed(0)}–${row.price_high.toFixed(0)}`
                            : "—"}
                        </td>
                        <td className={`right num ${(row.delta ?? 0) < 0 ? "delta-down" : "delta-up"}`}>
                          {signedPct(row.delta)}
                        </td>
                        <td>
                          <span className="small">{STRATEGY_TEXT[row.pricing_strategy] || row.pricing_strategy}</span>
                        </td>
                        <td>
                          <Btn
                            size="sm"
                            disabled={busy === row.id}
                            onClick={() => void runAgent(row)}
                          >
                            <Icon name="play" size={12} />
                            研判
                          </Btn>
                        </td>
                      </tr>
                    ))}
              </tbody>
            </table>
          </div>
          {!dash.loading && !rows.length && <Empty>暂无目标</Empty>}
        </Panel>

        <div className="stack">
          <Panel title="目标详情" eyebrow={current?.region || "选定目标"} tone="violet">
            {current ? (
              <div className="stack" style={{ gap: 14 }}>
                <div>
                  <div className="title-line" style={{ fontSize: 14 }}>
                    {current.title}
                  </div>
                  <div className="sub-line">
                    {current.platform} · {current.my_sku || "未绑定"} · 更新 {timeAgo(current.last_ts)}
                  </div>
                </div>

                <PriceLadder
                  myPrice={current.my_price}
                  low={current.price_low}
                  high={current.price_high}
                  severity={current.severity}
                />
                <div className="row small muted spread">
                  <span>我方 {money(current.my_price)}</span>
                  <span>竞品 {money(current.point)}</span>
                </div>

                <div>
                  <span className="eyebrow">近 40 次竞品价</span>
                  <Spark
                    values={(history.data ?? []).map((p) => (p.price_low + p.price_high) / 2)}
                    height={38}
                    tone="violet"
                  />
                </div>

                <div className="row">
                  <select
                    className="select"
                    style={{ width: 150 }}
                    value={current.pricing_strategy}
                    onChange={(e) => void changeStrategy(current, e.target.value)}
                  >
                    {STRATEGIES.map((s) => (
                      <option key={s} value={s}>
                        {STRATEGY_TEXT[s]}
                      </option>
                    ))}
                  </select>
                  <Btn tone="primary" onClick={() => void runAgent(current)}>
                    <Icon name="spark" size={14} />
                    Agent 立即研判
                  </Btn>
                </div>
              </div>
            ) : (
              <Empty>选择左侧目标查看</Empty>
            )}
          </Panel>

          <Panel
            title="异常待确认"
            eyebrow="Exceptions only"
            tone="amber"
            extra={<Chip tone="amber">{exceptions.length}</Chip>}
          >
            <div className="stack" style={{ gap: 10 }}>
              {exceptions.length ? (
                exceptions.slice(0, 4).map((item) => (
                  <div className="alert-card" key={item.id}>
                    <div className="spread">
                      <strong style={{ fontSize: 12.5 }}>{item.target_title}</strong>
                      <span className="small muted">{item.region}</span>
                    </div>
                    <div className="reason">{item.exception_reason || item.guardrail_note}</div>
                    <div className="row small muted">
                      <span>{ACTION_TEXT[item.action] || item.action}</span>
                      <span>· 建议 {money(item.target_price)}</span>
                      <span>· {pct(item.confidence, 0)}</span>
                    </div>
                    <div className="row">
                      <Btn size="sm" tone="primary" disabled={busy === item.id} onClick={() => void resolve(item, true)}>
                        确认
                      </Btn>
                      <Btn size="sm" tone="danger" disabled={busy === item.id} onClick={() => void resolve(item, false)}>
                        驳回
                      </Btn>
                    </div>
                  </div>
                ))
              ) : (
                <Empty>无异常，Agent 自主运行</Empty>
              )}
            </div>
          </Panel>
        </div>
      </div>

      <Panel title="调价流水" eyebrow="Bid ledger">
        <div className="ticker">
          {(ledger.data?.items ?? []).map((item) => (
            <div className="ticker-row" key={item.id}>
              <span className="ticker-time num">{clock(item.ts)}</span>
              <span className="ticker-main">
                <strong>{ACTION_TEXT[item.action] || item.action}</strong>
                <span className="muted">
                  {" "}
                  · {item.region || "全国"} · {item.mode === "auto" ? "自动" : "人工"} ·{" "}
                  {STATUS_TEXT[item.status] || item.status}
                </span>
                {item.reason && <span className="muted"> · {item.reason}</span>}
              </span>
              <span className="ticker-price num">
                {money(item.from_price)} → {money(item.to_price)}
              </span>
              <span className={`num small ${(item.delta_pct ?? 0) < 0 ? "delta-down" : "delta-up"}`}>
                {signedPct(item.delta_pct)}
              </span>
            </div>
          ))}
          {!ledger.data?.items?.length && <Empty>暂无流水</Empty>}
        </div>
      </Panel>

      <Toast message={message} />
    </>
  );
}

function MiniStat({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="row" style={{ gap: 10 }}>
      <span className={`dot ${tone}`} />
      <div>
        <div className="num" style={{ fontSize: 20 }}>
          {value}
        </div>
        <div className="small muted">{label}</div>
      </div>
    </div>
  );
}
