import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, qs } from "../core/api";
import { ts } from "../core/format";
import { useAsync } from "../core/hooks";
import type { EventRow } from "../core/types";
import { Card, Empty, ErrorBox, Page, SeverityBadge, Spinner, Table } from "../ui/kit";

const LEVELS = ["全部", "L3", "L2", "L1"];

export default function Events() {
  const navigate = useNavigate();
  const [level, setLevel] = useState("全部");
  const [keyword, setKeyword] = useState("");
  const { data, error, loading } = useAsync(
    () => api.get<EventRow[]>("/api/events" + qs({ limit: 200, severity: level === "全部" ? undefined : level })),
    [level],
  );

  const rows = (data ?? []).filter((item) => {
    if (!keyword.trim()) return true;
    const text = `${item.target_title ?? ""}${item.target_id}${item.type}${item.note ?? ""}`;
    return text.toLowerCase().includes(keyword.trim().toLowerCase());
  });

  return (
    <Page
      title="事件与研判"
      desc="价格、标题、主图与采集变化都在这里，按严重级别筛选"
      actions={
        <input
          className="input"
          placeholder="搜索竞品或说明"
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
        />
      }
    >
      <div className="chipbar">
        {LEVELS.map((item) => (
          <button
            key={item}
            className={`chip${level === item ? " on" : ""}`}
            onClick={() => setLevel(item)}
          >
            {item}
          </button>
        ))}
        <span className="hint" style={{ marginLeft: "auto" }}>
          共 {rows.length} 条
        </span>
      </div>

      {error && <ErrorBox message={error} />}

      <Card flush>
        {loading && !data ? (
          <Spinner />
        ) : rows.length === 0 ? (
          <Empty>没有符合条件的事件。</Empty>
        ) : (
          <Table head={["级别", "竞品", "类型", "门禁", "说明", "时间"]}>
            {rows.map((item) => (
              <tr key={item.id} className="click" onClick={() => navigate(`/events/${item.id}`)}>
                <td>
                  <SeverityBadge value={item.severity} />
                </td>
                <td>
                  <b>{item.target_title ?? item.target_id}</b>
                  <div className="sub">{item.target_id}</div>
                </td>
                <td>{item.type}</td>
                <td className="sub">{item.gate_level}</td>
                <td className="sub" style={{ maxWidth: 360 }}>{item.note}</td>
                <td className="sub">{ts(item.ts)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </Page>
  );
}
