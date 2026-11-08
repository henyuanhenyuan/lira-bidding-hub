import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../core/api";
import { pct, ts } from "../core/format";
import { useAsync } from "../core/hooks";
import type { Suggestion } from "../core/types";
import { Badge, Card, Empty, ErrorBox, Page, Spinner, StatusBadge, Table, actionText } from "../ui/kit";

const FILTERS = [
  { key: "all", label: "全部" },
  { key: "pending", label: "待提交" },
  { key: "submitted", label: "待审批" },
  { key: "approved", label: "已批准" },
  { key: "executed", label: "已执行" },
];

export default function Suggestions() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState("all");
  const { data, error, loading } = useAsync(
    () => api.get<Suggestion[]>("/api/suggestions?limit=200"),
    [],
  );

  const rows = (data ?? []).filter((item) => filter === "all" || item.status === filter);

  return (
    <Page title="建议" desc="Agent 给出的处置建议，动作由确定性策略决定，模型只写解释">
      <div className="chipbar">
        {FILTERS.map((item) => (
          <button
            key={item.key}
            className={`chip${filter === item.key ? " on" : ""}`}
            onClick={() => setFilter(item.key)}
          >
            {item.label}
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
          <Empty>没有符合条件的建议。</Empty>
        ) : (
          <Table head={["动作", "竞品", "状态", "护栏", "置信度", "生成方式", "时间"]}>
            {rows.map((item) => (
              <tr
                key={item.id}
                className="click"
                onClick={() => navigate(`/suggestions/${item.id}`)}
              >
                <td>
                  <b>{actionText(item.action)}</b>
                </td>
                <td>{item.target_title ?? "—"}</td>
                <td>
                  <StatusBadge value={item.status} />
                </td>
                <td>
                  <Badge tone={item.guardrail === "blocked" ? "danger" : item.guardrail === "ok" ? "ok" : "neutral"}>
                    {item.guardrail}
                  </Badge>
                </td>
                <td className="num">{pct(item.confidence)}</td>
                <td className="mono sub">{item.generated_by}</td>
                <td className="sub">{ts(item.created_at)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </Page>
  );
}
