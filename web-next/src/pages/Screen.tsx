import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { endpoints } from "../core/api";
import { ACTION_TEXT, clock, money, pct, signedPct } from "../core/format";
import { useAsync } from "../core/hooks";
import { useLive } from "../core/live";
import { Chip, Empty, Stat } from "../ui/atoms";
import { Icon } from "../ui/icons";
import { RegionMosaic, Spark } from "../ui/visuals";

export default function Screen() {
  const navigate = useNavigate();
  const [now, setNow] = useState(new Date());
  const [region, setRegion] = useState("");
  const dash = useAsync(() => endpoints.dashboard(7, region || undefined), [region], { pollMs: 15000 });
  const exc = useAsync(() => endpoints.exceptions(), [], { pollMs: 15000 });
  const { events, connected } = useLive(10);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!events.length) return;
    dash.reload();
    exc.reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events[0]?.id]);

  const data = dash.data;
  const exceptions = exc.data?.items ?? [];
  const trend = (data?.trend ?? []).map((t) => t.count);
  const autoCount = (data?.status.executed ?? 0) + (data?.autopilot?.auto_executed ?? 0);

  return (
    <div className="screen">
      <div className="aurora" aria-hidden="true">
        <span className="a1" />
        <span className="a2" />
        <span className="a3" />
      </div>
      <div className="grain" aria-hidden="true" />

      <button className="btn ghost sm exit-btn" onClick={() => navigate("/")}>
        <Icon name="close" size={14} />
        退出大屏
      </button>

      <header className="screen-head">
        <div>
          <p>Lira · Autonomous Bidding Command</p>
          <h1>竞价智能中枢 · 实时大屏</h1>
        </div>
        <div className="row">
          <Chip tone={connected ? "green" : "amber"}>{connected ? "实时链路" : "重连中"}</Chip>
          <Chip tone="neutral">{region || "全部地区"}</Chip>
          <span className="num" style={{ fontSize: 15, letterSpacing: "0.06em" }}>
            {now.toLocaleTimeString("zh-CN", { hour12: false })}
          </span>
        </div>
      </header>

      <div className="screen-kpis">
        <Stat label="自主成交" accent="cyan" value={autoCount} hint="Agent 全自动闭环">
          <Spark values={trend.length ? trend : [1, 2, 2, 3, 4]} height={38} />
        </Stat>
        <Stat label="待人工确认" accent="amber" value={exceptions.length} hint="仅异常人工介入" />
        <Stat
          label="高危事件"
          accent="rose"
          value={data?.severity.L3 ?? 0}
          hint={`关注 ${data?.severity.L2 ?? 0} · 轻微 ${data?.severity.L1 ?? 0}`}
        />
        <Stat
          label="覆盖目标"
          accent="violet"
          value={data?.compare?.length ?? 0}
          hint={`${data?.regions?.length ?? 0} 个地区在跑`}
        />
      </div>

      <div className="screen-grid">
        <div className="stack">
          <section className="glass panel" style={{ flex: 1 }}>
            <header className="panel-head">
              <div className="panel-heading">
                <span className="eyebrow">Live bidding board</span>
                <h2 className="panel-title">竞价实况</h2>
              </div>
              <div className="panel-extra">
                <Chip tone="cyan">{data?.compare?.length ?? 0} 目标</Chip>
              </div>
            </header>
            <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {(data?.compare ?? []).slice(0, 7).map((row) => (
                <div className="run-card" key={row.id} style={{ padding: "14px 16px" }}>
                  <span className={`sev ${row.severity === "L3" ? "l3" : row.severity === "L2" ? "l2" : "l1"}`}>
                    {row.severity}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="title-line" style={{ fontSize: 14 }}>
                      {row.title}
                    </div>
                    <div className="sub-line">
                      {row.region} · {row.pricing_strategy}
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div className="num" style={{ fontSize: 16 }}>
                      {money(row.my_price)}
                    </div>
                    <div className="small muted num">
                      {row.price_low?.toFixed(0)}–{row.price_high?.toFixed(0)}
                    </div>
                  </div>
                  <span
                    className={`num ${(row.delta ?? 0) < 0 ? "delta-down" : "delta-up"}`}
                    style={{ width: 62, textAlign: "right" }}
                  >
                    {signedPct(row.delta)}
                  </span>
                </div>
              ))}
              {!data?.compare?.length && <Empty>等待数据</Empty>}
            </div>
          </section>

          <section className="glass panel">
            <header className="panel-head">
              <div className="panel-heading">
                <span className="eyebrow">Region matrix</span>
                <h2 className="panel-title">区域分布</h2>
              </div>
            </header>
            <div className="panel-body">
              <RegionMosaic
                regions={data?.regions ?? []}
                active={region}
                onPick={(value) => setRegion(value === region ? "" : value)}
              />
            </div>
          </section>
        </div>

        <div className="stack">
          <section className="glass panel" style={{ flex: 1 }}>
            <header className="panel-head">
              <div className="panel-heading">
                <span className="eyebrow">Needs attention</span>
                <h2 className="panel-title">异常待确认</h2>
              </div>
              <Chip tone="amber">{exceptions.length}</Chip>
            </header>
            <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {exceptions.slice(0, 4).map((item) => (
                <div className="alert-card" key={item.id}>
                  <div className="spread">
                    <strong>{item.target_title}</strong>
                    <span className="small muted">{item.region}</span>
                  </div>
                  <div className="reason">{item.exception_reason || item.guardrail_note}</div>
                  <div className="row small muted">
                    <span>{money(item.target_price)}</span>
                    <span>· {pct(item.confidence, 0)}</span>
                  </div>
                </div>
              ))}
              {!exceptions.length && <Empty>Agent 全自动运行中</Empty>}
            </div>
          </section>

          <section className="glass panel" style={{ flex: 1 }}>
            <header className="panel-head">
              <div className="panel-heading">
                <span className="eyebrow">Bid ledger</span>
                <h2 className="panel-title">实时流水</h2>
              </div>
            </header>
            <div className="panel-body">
              <div className="ticker">
                {(data?.autopilot?.ledger ?? []).slice(0, 8).map((item) => (
                  <div className="ticker-row" key={item.id}>
                    <span className="ticker-time num">{clock(item.ts)}</span>
                    <span className="ticker-main">
                      <strong>{ACTION_TEXT[item.action] || item.action}</strong>
                      <span className="muted"> · {item.region}</span>
                    </span>
                    <span className="ticker-price num">
                      {money(item.from_price)} → {money(item.to_price)}
                    </span>
                  </div>
                ))}
                {!data?.autopilot?.ledger?.length && <Empty>暂无流水</Empty>}
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
