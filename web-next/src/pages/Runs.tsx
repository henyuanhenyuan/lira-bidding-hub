import { useNavigate } from "react-router-dom";

import { api } from "../core/api";
import { num, ts } from "../core/format";
import { useAsync } from "../core/hooks";
import { Card, Empty, ErrorBox, Page, SeverityBadge, Spinner, StatusBadge, Table } from "../ui/kit";

interface RunRow {
  id: string;
  event_id: string;
  trigger: string;
  status: string;
  model: string;
  started_at: string;
  latency_ms?: number | null;
  step_count?: number;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  target_title?: string | null;
  event_type?: string | null;
  severity?: string | null;
}

export default function Runs() {
  const navigate = useNavigate();
  const { data, error, loading } = useAsync(
    () => api.get<RunRow[]>("/api/agent/runs?limit=100"),
    [],
  );

  return (
    <Page title="运行轨迹" desc="每次研判的完整步骤、工具调用与交接记录">
      {error && <ErrorBox message={error} />}
      <Card flush>
        {loading && !data ? (
          <Spinner />
        ) : (data ?? []).length === 0 ? (
          <Empty>还没有 Agent 运行记录。去事件详情点「生成研判」。</Empty>
        ) : (
          <Table head={["竞品", "事件", "状态", "模型", "步骤", "Token", "耗时", "开始"]}>
            {(data ?? []).map((row) => (
              <tr key={row.id} className="click" onClick={() => navigate(`/runs/${row.id}`)}>
                <td>{row.target_title ?? row.event_id}</td>
                <td>
                  <div className="row">
                    {row.severity && <SeverityBadge value={row.severity} />}
                    <span className="sub">{row.event_type}</span>
                  </div>
                </td>
                <td>
                  <StatusBadge value={row.status} />
                </td>
                <td className="mono sub">{row.model}</td>
                <td className="num">{row.step_count ?? 0}</td>
                <td className="num">
                  {num((row.prompt_tokens ?? 0) + (row.completion_tokens ?? 0))}
                </td>
                <td className="num">{row.latency_ms ?? "—"}ms</td>
                <td className="sub">{ts(row.started_at)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </Page>
  );
}
