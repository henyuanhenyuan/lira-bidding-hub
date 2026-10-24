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

export default function Events() {
  const [severity, setSeverity] = useState("");
  const { data, error, loading, reload } = useAsync(
    () => api.get<EventItem[]>(`/api/events${query({ severity, limit: 100 })}`),
    [severity],
  );

  useStreamEvent(["event", "ingest"], () => void reload());

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
          {loading ? "刷新中…" : `${data?.length ?? 0} 条事件`}
        </span>
      </div>

      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !data && <Loader />}
      {data && data.length === 0 && (
        <Empty>当前筛选下没有事件。换个级别，或先导入采集数据。</Empty>
      )}

      {data && data.length > 0 && (
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
              {data.map((event) => (
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
