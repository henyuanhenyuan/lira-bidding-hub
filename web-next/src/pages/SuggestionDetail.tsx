import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, ApiError } from "../core/api";
import { money, pct } from "../core/format";
import { useAsync } from "../core/hooks";
import type { EventRow, Suggestion } from "../core/types";
import {
  Badge,
  Card,
  Empty,
  ErrorBox,
  Field,
  Page,
  Spinner,
  StatusBadge,
  actionText,
} from "../ui/kit";

interface Detail extends Suggestion {
  event: EventRow | null;
  evidence_docs: { id: string; doc_title: string; content: string; chunk_no: number }[];
}

interface Risk {
  level: string;
  roles: string[];
  reason: string;
}

interface Execution {
  id: string;
  mode: string;
  status: string;
  executed_price?: number | null;
  created_at: string;
}

export default function SuggestionDetail() {
  const { id = "" } = useParams();
  const { data, error, loading, reload } = useAsync(
    () => api.get<Detail>(`/api/suggestions/${encodeURIComponent(id)}`),
    [id],
  );
  const [note, setNote] = useState("");
  const [price, setPrice] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [risk, setRisk] = useState<Risk | null>(null);
  const [executions, setExecutions] = useState<Execution[]>([]);

  async function act(label: string, fn: () => Promise<unknown>) {
    setBusy(true);
    setMessage("");
    try {
      await fn();
      setMessage(`${label}成功`);
      await reload();
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : `${label}失败`);
    } finally {
      setBusy(false);
    }
  }

  async function loadRisk() {
    setRisk(await api.get<Risk>(`/api/suggestions/${encodeURIComponent(id)}/risk`));
  }

  async function loadExecutions() {
    setExecutions(
      await api.get<Execution[]>(`/api/suggestions/${encodeURIComponent(id)}/executions`),
    );
  }

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  const s = data;
  const done = s.status === "executed";

  return (
    <Page
      title={actionText(s.action)}
      desc={`${s.target_title ?? s.event_id} · 生成方式 ${s.generated_by}`}
      actions={
        <div className="row">
          <button className="btn ghost" onClick={() => void loadRisk()}>
            风险等级
          </button>
          <button className="btn ghost" onClick={() => void loadExecutions()}>
            执行记录
          </button>
          {s.event_id && (
            <Link className="btn ghost" to={`/events/${s.event_id}`}>
              查看事件
            </Link>
          )}
        </div>
      }
    >
      {message && <div className="notice">{message}</div>}
      {risk && (
        <div className="notice">
          风险 {risk.level} · 需 {risk.roles.join(" / ")} 审批 · {risk.reason}
        </div>
      )}

      <div className="split">
        <div>
          <Card title="建议内容">
            <p style={{ marginTop: 0 }}>{s.narrative}</p>
            <dl className="kv">
              <dt>状态</dt>
              <dd>
                <StatusBadge value={s.status} />
              </dd>
              <dt>置信度</dt>
              <dd>{pct(s.confidence)}</dd>
              <dt>护栏</dt>
              <dd>
                <Badge tone={s.guardrail === "blocked" ? "danger" : s.guardrail === "ok" ? "ok" : "neutral"}>
                  {s.guardrail}
                </Badge>{" "}
                <span className="sub">{s.guardrail_note ?? ""}</span>
              </dd>
              <dt>目标价</dt>
              <dd>{money(s.target_price)}</dd>
              <dt>目标毛利率</dt>
              <dd>{pct(s.margin_at_target)}</dd>
            </dl>
          </Card>

          <Card title="引用的规则" sub="来自知识库，可作为审批依据">
            {data.evidence_docs.length === 0 ? (
              <Empty>本次建议没有引用文档。</Empty>
            ) : (
              <ul className="timeline">
                {data.evidence_docs.map((item) => (
                  <li key={item.id}>
                    <b>{item.doc_title}</b>
                    <span>{item.content}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {executions.length > 0 && (
            <Card title="执行记录" flush>
              <ul className="timeline" style={{ padding: "12px 18px" }}>
                {executions.map((item) => (
                  <li key={item.id}>
                    <b>
                      {item.mode} · {item.status}
                    </b>
                    <span>
                      成交价 {money(item.executed_price)} · {item.created_at}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>

        <div>
          <Card title="审批动作" sub="人工审批是唯一执行入口">
            <Field label="备注（审批/驳回时填写）">
              <textarea
                className="input"
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="说明判断依据"
              />
            </Field>
            {s.status === "pending" && (
              <button
                className="btn"
                disabled={busy}
                onClick={() =>
                  void act("提交", () =>
                    api.post(`/api/suggestions/${s.id}/submit`, { note: note || null }),
                  )
                }
              >
                提交审批
              </button>
            )}
            {s.status === "submitted" && (
              <div className="row">
                <button
                  className="btn"
                  disabled={busy}
                  onClick={() =>
                    void act("批准", () =>
                      api.post(`/api/suggestions/${s.id}/approve`, { note: note || null }),
                    )
                  }
                >
                  批准
                </button>
                <button
                  className="btn ghost"
                  disabled={busy}
                  onClick={() =>
                    void act("驳回", () =>
                      api.post(`/api/suggestions/${s.id}/reject`, { note: note || null }),
                    )
                  }
                >
                  驳回
                </button>
              </div>
            )}
            {s.status === "approved" && (
              <>
                <Field label="实际成交价（可选）">
                  <input
                    className="input"
                    value={price}
                    onChange={(event) => setPrice(event.target.value)}
                    placeholder={s.target_price ? String(s.target_price) : "如 289"}
                  />
                </Field>
                <button
                  className="btn"
                  disabled={busy}
                  onClick={() =>
                    void act("执行", () =>
                      api.post(`/api/suggestions/${s.id}/execute`, {
                        executed_price: price.trim() ? Number(price) : null,
                        note: note || null,
                      }),
                    )
                  }
                >
                  标记已执行
                </button>
              </>
            )}
            {done && (
              <p className="hint">
                已执行。7 日后请回到「结果回收」记录 <Link to="/suggestions">实际效果</Link>。
              </p>
            )}
            {s.status === "rejected" && <p className="hint">已驳回，流程结束。</p>}
          </Card>
        </div>
      </div>
    </Page>
  );
}
