import { useState } from "react";
import { Link } from "react-router-dom";

import { api, query } from "../api";
import { Empty, ErrorBox, Loader, PageHead, SeverityBadge } from "../components/ui";
import { formatTs } from "../format";
import { useAsync, useStreamEvent } from "../hooks";
import { TYPE_TEXT } from "../labels";
import type { EventItem } from "../types";

const FILTERS = [
  { value: "", label: "全部" },
  { value: "L3", label: "L3 紧急" },
  { value: "L2", label: "L2 关注" },
  { value: "L1", label: "L1 信息" },
];

const TYPE_GROUPS: { key: string; label: string; types: string[] }[] = [
  { key: "", label: "全部类型", types: [] },
  {
    key: "price",
    label: "价格变动",
    types: ["price_drop", "price_rise", "band_breach"],
  },
  {
    key: "content",
    label: "标题与主图",
    types: ["title_change", "image_change"],
  },
  { key: "review", label: "差评突增", types: ["review_spike"] },
  { key: "source", label: "采集源切换", types: ["source_switch"] },
];

export default function Events() {
  const [severity, setSeverity] = useState("");
  const [group, setGroup] = useState("");
  const { data, error, loading, reload } = useAsync(
    () => api.get<EventItem[]>(`/api/events${query({ severity, limit: 100 })}`),
    [severity],
  );

  useStreamEvent(["event", "ingest"], () => void reload());

  const activeGroup = TYPE_GROUPS.find((item) => item.key === group);
  const events = (data ?? []).filter(
    (event) =>
      !activeGroup?.types.length || activeGroup.types.includes(event.type),
  );

  return (
    <>
      <PageHead
        title="事件"
        sub="价格、标题、主图与评论的变化都在这里，按严重级别筛选"
        actions={
          <button className="btn ghost" onClick={() => void reload()}>
            刷新
          </button>
        }
      />

      <div className="toolbar">
        <div className="chips">
          {FILTERS.map((item) => (
            <button
              key={item.value}
              className={`chip${severity === item.value ? " active" : ""}`}
              onClick={() => setSeverity(item.value)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <span className="hint">
          {loading ? "刷新中…" : `${events.length} 条事件`}
        </span>
      </div>

      <div className="toolbar">
        <div className="chips">
          {TYPE_GROUPS.map((item) => (
            <button
              key={item.key}
              className={`chip${group === item.key ? " active" : ""}`}
              onClick={() => setGroup(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !data && <Loader />}
      {events.length === 0 && (
        <Empty>当前筛选下没有事件。换个级别或类型，或先导入采集数据。</Empty>
      )}

      {events.length > 0 && (
        <div className="table-wrap card">
          <table className="table hoverable">
            <thead>
              <tr>
                <th>级别</th>
                <th>竞品</th>
                <th>类型</th>
                <th>说明</th>
                <th>时间</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.id}>
                  <td>
                    <SeverityBadge value={event.severity} />
                  </td>
                  <td>
                    <Link className="strong-link" to={`/events/${event.id}`}>
                      {event.target_title || event.target_id}
                    </Link>
                    <span className="sub">{event.target_id}</span>
                  </td>
                  <td>{TYPE_TEXT[event.type] ?? event.type}</td>
                  <td className="note-cell">{event.note || "—"}</td>
                  <td className="num">{formatTs(event.ts)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
