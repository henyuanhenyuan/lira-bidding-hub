import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { useAuth } from "../auth";
import PriceChart from "../components/PriceChart";
import { Card, Empty, ErrorBox, Loader, Metric, PageHead, SeverityBadge } from "../components/ui";
import { timeAgo } from "../format";
import { useAsync, useStreamEvent } from "../hooks";
import { ACTION_TEXT, TYPE_TEXT } from "../labels";
import type {
  CollectionHealth,
  EventItem,
  Health,
  OpsState,
  PricePoint,
  Suggestion,
  Target,
} from "../types";

function PriceTrend() {
  const targets = useAsync(() => api.get<Target[]>("/api/targets"), []);
  const [targetId, setTargetId] = useState("");

  useEffect(() => {
    if (!targetId && targets.data?.length) {
      setTargetId(targets.data[0].id);
    }
  }, [targets.data, targetId]);

  const series = useAsync(
    () =>
      targetId
        ? api.get<PricePoint[]>(`/api/targets/${targetId}/prices?limit=60`)
        : Promise.resolve([]),
    [targetId],
  );

  const current = targets.data?.find((item) => item.id === targetId);
  const list = series.data ?? [];

  return (
    <Card
      title="价格趋势"
      sub="到手价区间；虚线是我方价格"
      actions={
        <select
          value={targetId}
          onChange={(event) => setTargetId(event.target.value)}
        >
          {(targets.data ?? []).map((target) => (
            <option key={target.id} value={target.id}>
              {target.title}
            </option>
          ))}
        </select>
      }
    >
      {series.error ? (
        <ErrorBox message={series.error} onRetry={series.reload} />
      ) : list.length === 0 ? (
        <Empty>还没有价格序列。导入两次采集后即可看到趋势。</Empty>
      ) : (
        <PriceChart points={list} myPrice={current?.my_price ?? null} />
      )}
    </Card>
  );
}

export default function Overview() {
  const { me } = useAuth();
  const { data, error, loading, reload } = useAsync(async () => {
    const [health, events, approvals] = await Promise.all([
      api.get<Health>("/api/health"),
      api.get<EventItem[]>("/api/events?limit=60"),
      api.get<Suggestion[]>("/api/approvals/inbox"),
    ]);
    const ops =
      me?.role === "admin"
        ? await api.get<OpsState>("/api/ops").catch(() => null)
        : null;
    return { health, events, approvals, ops };
  }, [me?.role]);

  useStreamEvent(["event", "approval", "ingest"], () => void reload());

  if (loading && !data) return <Loader label="正在汇总今日态势…" />;
  if (error && !data) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;

  const { health, events, approvals, ops } = data;
  const urgent = events.filter((event) => event.severity === "L3");
  const freshness = health.freshness;
  const collection: CollectionHealth[] = ops?.collection ?? [];
  const stale = collection.filter((item) => item.stale).length;

  return (
    <>
      <PageHead
        title="总览"
        sub="今天需要你拍板的事，和市场的真实动静"
        actions={
          <Link className="btn ghost" to="/events">
            查看全部事件
          </Link>
        }
      />

      <div className="metric-row">
        <Metric
          label="待审批"
          value={approvals.length}
          sub={approvals.length ? "等待你或主管处理" : "没有积压"}
          tone={approvals.length ? "warn" : "ok"}
        />
        <Metric
          label="L3 事件"
          value={urgent.length}
          sub={urgent.length ? "高优先级，建议优先研判" : "暂无紧急事件"}
          tone={urgent.length ? "danger" : "ok"}
        />
        <Metric
          label="数据新鲜度"
          value={freshness.lag_hours === null ? "—" : `${freshness.lag_hours.toFixed(1)}h`}
          sub={`SLA ${freshness.sla_hours} 小时${freshness.stale ? " · 已超时" : ""}`}
          tone={freshness.stale ? "danger" : "ok"}
        />
        <Metric
          label="采集源"
          value={health.collectors.length}
          sub={
            health.collectors.length
              ? `${health.collectors.map((item) => item.collector).join(" / ")}`
              : "尚无采集记录"
          }
          tone={stale ? "warn" : "ok"}
        />
      </div>

      <PriceTrend />

      <div className="grid-2">
        <Card
          title="需要你决策"
          sub="审批通过后运营才能执行"
          actions={<Link to="/approvals">全部</Link>}
        >
          {approvals.length === 0 ? (
            <Empty>没有待审批的建议。事件研判完成并提交后会出现在这里。</Empty>
          ) : (
            <ul className="decision-list">
              {approvals.slice(0, 5).map((item) => (
                <li key={item.id}>
                  <Link to={`/suggestions/${item.id}`} className="decision-item">
                    <span className={`dot ${item.gate_level}`} />
                    <span className="decision-main">
                      <b>{ACTION_TEXT[item.action] ?? item.action}</b>
                      <span>
                        {item.target_title || item.target_id} · 提交人 {item.submitted_by || "—"}
                      </span>
                    </span>
                    <span className="decision-side">
                      {item.margin_at_target != null
                        ? `毛利 ${(item.margin_at_target * 100).toFixed(1)}%`
                        : "毛利未知"}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          title="最新事件"
          sub="按时间倒序，已抑制的换源事件不展示"
          actions={<Link to="/events">事件流</Link>}
        >
          {events.length === 0 ? (
            <Empty>暂无事件。到「数据导入」载入采集数据后开始监控。</Empty>
          ) : (
            <ul className="feed">
              {events.slice(0, 8).map((event) => (
                <li key={event.id}>
                  <Link to={`/events/${event.id}`} className="feed-item">
                    <SeverityBadge value={event.severity} />
                    <span className="feed-main">
                      <b>{event.target_title || event.target_id}</b>
                      <span>
                        {TYPE_TEXT[event.type] ?? event.type}
                        {event.note ? ` · ${event.note}` : ""}
                      </span>
                    </span>
                    <span className="feed-time">{timeAgo(event.ts)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card
        title="采集健康度"
        sub={`SLA ${freshness.sla_hours} 小时；超时会在事件页标红`}
        actions={
          ops ? (
            <Link to="/collection">系统详情</Link>
          ) : (
            <span className="hint">需要管理员权限查看系统详情</span>
          )
        }
      >
        {collection.length === 0 ? (
          <Empty>还没有采集源记录。RPA 首次投递后这里会出现。</Empty>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>采集源</th>
                  <th>快照数</th>
                  <th>最后成功</th>
                  <th>滞后</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {collection.map((item) => (
                  <tr key={item.collector}>
                    <td>{item.collector}</td>
                    <td className="num">{item.snapshots}</td>
                    <td>{item.last_ts ? timeAgo(item.last_ts) : "—"}</td>
                    <td className="num">
                      {item.lag_hours === null ? "—" : `${item.lag_hours.toFixed(1)}h`}
                    </td>
                    <td>
                      <span className={`badge ${item.stale ? "sev-L2" : "sev-L1"}`}>
                        {item.stale ? "滞后" : "正常"}
                      </span>
                    </td>
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
