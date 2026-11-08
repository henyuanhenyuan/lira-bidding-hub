import { useState } from "react";
import { Link } from "react-router-dom";

import { api, ApiError } from "../core/api";
import { money, pct } from "../core/format";
import { useAsync } from "../core/hooks";
import type { Suggestion } from "../core/types";
import { Badge, Card, Empty, ErrorBox, Page, Spinner, Table, actionText } from "../ui/kit";

export default function Approvals() {
  const { data, error, loading, reload } = useAsync(
    () => api.get<Suggestion[]>("/api/approvals/inbox"),
    [],
  );
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");

  async function approve(item: Suggestion) {
    setBusy(item.id);
    setMessage("");
    try {
      await api.post(`/api/suggestions/${item.id}/approve`, {});
      setMessage(`已批准：${item.target_title ?? item.event_id}`);
      await reload();
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "审批失败");
    } finally {
      setBusy("");
    }
  }

  return (
    <Page title="待审批" desc="提交后的建议进入这里，必须由有权角色确认才能执行">
      {message && <div className="notice">{message}</div>}
      {error && <ErrorBox message={error} />}

      <Card flush>
        {loading && !data ? (
          <Spinner />
        ) : (data ?? []).length === 0 ? (
          <Empty>没有待审批的建议。</Empty>
        ) : (
          <Table head={["动作", "竞品", "置信度", "护栏", "目标价", "操作"]}>
            {(data ?? []).map((item) => (
              <tr key={item.id}>
                <td>
                  <Link to={`/suggestions/${item.id}`}>
                    <b>{actionText(item.action)}</b>
                  </Link>
                  <div className="sub">{item.narrative.slice(0, 40)}…</div>
                </td>
                <td>{item.target_title ?? "—"}</td>
                <td className="num">{pct(item.confidence)}</td>
                <td>
                  <Badge tone={item.guardrail === "blocked" ? "danger" : "ok"}>{item.guardrail}</Badge>
                </td>
                <td className="num">{money(item.target_price)}</td>
                <td>
                  <button
                    className="btn sm"
                    disabled={busy === item.id}
                    onClick={() => void approve(item)}
                  >
                    {busy === item.id ? "处理中…" : "批准"}
                  </button>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </Page>
  );
}
