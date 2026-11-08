import { Link } from "react-router-dom";

import { api } from "../core/api";
import { pct, ts } from "../core/format";
import { useAsync } from "../core/hooks";
import type { EventRow, Health, Metrics, Suggestion } from "../core/types";
import { Badge, Card, Empty, ErrorBox, Page, SeverityBadge, Spinner, Stat, StatusBadge, Table, actionText } from "../ui/kit";

export default function Overview() {
  const { data, error, loading } = useAsync(async () => {
    const [health, events, l3rows, inbox, metrics, suggestions] = await Promise.all([
      api.get<Health>("/api/health"),
      api.get<EventRow[]>("/api/events?limit=8"),
      api.get<EventRow[]>("/api/events?limit=200&severity=L3"),
      api.get<Suggestion[]>("/api/approvals/inbox"),
      api.get<Metrics>("/api/metrics"),
      api.get<Suggestion[]>("/api/suggestions?limit=6"),
    ]);
    return { health, events, l3rows, inbox, metrics, suggestions };
  }, []);

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  const { health, events, l3rows, inbox, metrics, suggestions } = data;
  const l3 = l3rows.length;

  return (
    <Page
      title="总览"
      desc="今天需要你拍板的事，和 Agent 的实际运行状态"
      actions={
        <Link className="btn ghost" to="/events">
          查看全部事件
        </Link>
      }
    >
      <div className="stat-grid">
        <Stat
          label="待审批"
          value={inbox.length}
          hint="等待你或主管处理"
          tone={inbox.length > 0 ? "warn" : undefined}
        />
        <Stat label="L3 事件（近期）" value={l3} hint="高优先级，建议优先研判" tone={l3 > 0 ? "danger" : undefined} />
        <Stat
          label="数据新鲜度"
          value={health.freshness?.lag_hours != null ? `${Math.round(health.freshness.lag_hours)}h` : "—"}
          hint={
            health.freshness?.stale
              ? `SLA ${health.freshness.sla_hours ?? 12}h · 已超时`
              : "在 SLA 内"
          }
          tone={health.freshness?.stale ? "danger" : "ok"}
        />
        <Stat
          label="模型回退率"
          value={pct(metrics.fallback_rate)}
          hint={`24h 调用 ${metrics.calls} 次 · 成本 ¥${metrics.cost}`}
          tone={metrics.fallback_rate > 0.6 ? "warn" : "ok"}
        />
      </div>

      <div className="split">
        <Card title="最新事件" sub="点击查看事实与证据" flush>
          {events.length === 0 ? (
            <Empty>还没有事件。先导入一次采集数据。</Empty>
          ) : (
            <Table head={["级别", "竞品", "类型", "说明", "时间"]}>
              {events.map((item) => (
                <tr key={item.id} className="click">
                  <td>
                    <SeverityBadge value={item.severity} />
                  </td>
                  <td>
                    <Link to={`/events/${item.id}`}>{item.target_title ?? item.target_id}</Link>
                  </td>
                  <td>{item.type}</td>
                  <td className="sub">{item.note}</td>
                  <td className="sub">{ts(item.ts)}</td>
                </tr>
              ))}
            </Table>
          )}
        </Card>

        <div>
          <Card title="系统状态">
            <dl className="kv">
              <dt>模型</dt>
              <dd>{health.llm_available ? <Badge tone="ok">可用</Badge> : <Badge tone="warn">未连接</Badge>}</dd>
              <dt>向量索引</dt>
              <dd>
                {health.vector_index.indexed} / {health.vector_index.cases}
                {health.vector_index.stale && <span className="sub"> · 待重建</span>}
              </dd>
              <dt>采集源</dt>
              <dd>{health.collectors.map((item) => item.collector).join(" / ") || "—"}</dd>
              <dt>目标数</dt>
              <dd>{health.counts.targets ?? 0}</dd>
              <dt>近 24h 调用</dt>
              <dd>
                {metrics.calls} 次 · P95 {metrics.p95_latency_ms ?? "—"}ms
              </dd>
            </dl>
          </Card>

          <Card title="最新建议" flush>
            {suggestions.length === 0 ? (
              <Empty>还没有建议。</Empty>
            ) : (
              <Table head={["动作", "状态", "置信度"]}>
                {suggestions.map((item) => (
                  <tr key={item.id} className="click">
                    <td>
                      <Link to={`/suggestions/${item.id}`}>{actionText(item.action)}</Link>
                    </td>
                    <td>
                      <StatusBadge value={item.status} />
                    </td>
                    <td className="num">{pct(item.confidence)}</td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
        </div>
      </div>
    </Page>
  );
}
