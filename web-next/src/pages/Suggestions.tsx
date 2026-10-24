import { Link } from "react-router-dom";

import { api } from "../api";
import { Empty, ErrorBox, Loader, PageHead, StatusBadge } from "../components/ui";
import { formatTs, percent } from "../format";
import { useAsync, useStreamEvent } from "../hooks";
import { ACTION_TEXT } from "../labels";
import type { Suggestion } from "../types";

export default function Suggestions() {
  const { data, error, loading, reload } = useAsync(
    () => api.get<Suggestion[]>("/api/suggestions?limit=100"),
    [],
  );
  useStreamEvent(["event", "approval"], () => void reload());

  return (
    <>
      <PageHead
        title="建议"
        sub="每一条都带动作、置信度与毛利护栏，可按状态追踪"
        actions={
          <button className="btn ghost" onClick={() => void reload()}>
            刷新
          </button>
        }
      />

      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !data && <Loader />}
      {data && data.length === 0 && <Empty>还没有建议。先到事件详情页做一次研判。</Empty>}

      {data && data.length > 0 && (
        <div className="table-wrap card">
          <table className="table hoverable">
            <thead>
              <tr>
                <th>状态</th>
                <th>动作</th>
                <th>竞品</th>
                <th>说明</th>
                <th>置信</th>
                <th>时间</th>
              </tr>
            </thead>
            <tbody>
              {data.map((item) => (
                <tr key={item.id}>
                  <td>
                    <StatusBadge value={item.status} />
                  </td>
                  <td>
                    <Link className="strong-link" to={`/suggestions/${item.id}`}>
                      {ACTION_TEXT[item.action] ?? item.action}
                    </Link>
                  </td>
                  <td>{item.target_title || item.target_id || "—"}</td>
                  <td className="note-cell">{item.narrative}</td>
                  <td className="num">{percent(item.confidence)}</td>
                  <td className="num">{formatTs(item.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
