import { Link } from "react-router-dom";

import { api } from "../api";
import { Empty, ErrorBox, Loader, PageHead, SeverityBadge } from "../components/ui";
import { formatTs, timeAgo } from "../format";
import { useAsync, useStreamEvent } from "../hooks";
import type { AgentRun } from "../types";

const RUN_STATUS: Record<string, string> = {
  succeeded: "成功",
  failed: "失败",
  running: "运行中",
};

export default function AgentRuns() {
  const { data, error, loading, reload } = useAsync(
    () => api.get<AgentRun[]>("/api/agent/runs?limit=100"),
    [],
  );
  useStreamEvent(["agent"], () => void reload());

  return (
    <>
      <PageHead
        title="Agent 轨迹"
        sub="每次研判的计划、工具调用、校验和产出，都可回放"
        actions={
          <button className="btn ghost" onClick={() => void reload()}>
            刷新
          </button>
        }
      />

      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !data && <Loader />}
      {data && data.length === 0 && (
        <Empty>还没有运行记录。到事件详情页点「生成建议」会留下完整轨迹。</Empty>
      )}

      {data && data.length > 0 && (
        <div className="table-wrap card">
          <table className="table hoverable">
            <thead>
              <tr>
                <th>状态</th>
                <th>竞品 / 事件</th>
                <th>触发</th>
                <th>步数</th>
                <th>耗时</th>
                <th>开始</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.map((run) => (
                <tr key={run.id}>
                  <td>
                    <span className={`badge run-${run.status}`}>
                      {RUN_STATUS[run.status] ?? run.status}
                    </span>
                  </td>
                  <td>
                    <Link className="strong-link" to={`/agent/${run.id}`}>
                      {run.target_title || run.event_id}
                    </Link>
                    <span className="sub">
                      {run.severity ? <SeverityBadge value={run.severity} /> : null}
                      {run.event_type || run.event_id}
                    </span>
                  </td>
                  <td>{run.trigger}</td>
                  <td className="num">{run.step_count}</td>
                  <td className="num">
                    {run.latency_ms == null ? "—" : `${run.latency_ms}ms`}
                  </td>
                  <td className="num">{timeAgo(run.started_at)}</td>
                  <td>
                    <Link className="hint" to={`/agent/${run.id}`}>
                      查看轨迹
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="hint">
        最近一次运行为 {data?.length ? formatTs(data[0].started_at, true) : "—"}；失败运行会保留错误步骤。
      </p>
    </>
  );
}
