import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, ApiError } from "../core/api";
import { money, pct, ts } from "../core/format";
import { useAsync } from "../core/hooks";
import type { EventDetail as EventDetailType, Suggestion } from "../core/types";
import { Badge, Card, Empty, ErrorBox, Page, SeverityBadge, Spinner, StatusBadge, actionText } from "../ui/kit";

export default function EventDetail() {
  const { id = "" } = useParams();
  const { data, error, loading, reload } = useAsync(
    () => api.get<EventDetailType>(`/api/events/${encodeURIComponent(id)}`),
    [id],
  );
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function analyze() {
    setBusy(true);
    setMessage("");
    try {
      const suggestion = await api.post<Suggestion>(`/api/events/${encodeURIComponent(id)}/analyze`);
      setMessage(`研判完成：${actionText(suggestion.action)}（${suggestion.generated_by}）`);
      await reload();
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "研判失败");
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  const suggestion = data.suggestion;

  return (
    <Page
      title={data.target_title ?? data.target_id}
      desc={`${data.type} · ${ts(data.ts)} · ${data.gate_level}`}
      actions={
        <button className="btn" onClick={() => void analyze()} disabled={busy}>
          {busy ? "研判中…" : suggestion ? "重新研判" : "生成研判"}
        </button>
      }
    >
      {message && <div className="notice">{message}</div>}

      <div className="split">
        <div>
          <Card title="事实" sub="到手价由服务端计算，采集端只上报原始观测">
            <dl className="kv">
              <dt>严重度</dt>
              <dd>
                <SeverityBadge value={data.severity} /> <span className="sub">{data.gate_level}</span>
              </dd>
              <dt>到手价估算</dt>
              <dd>{data.note ?? money(data.point)}</dd>
              <dt>我方价</dt>
              <dd>{money(data.my_price)}</dd>
              <dt>置信度</dt>
              <dd>{pct(data.suggestion?.confidence ?? data.confidence)}</dd>
              <dt>事件 ID</dt>
              <dd className="mono sub">{data.id}</dd>
            </dl>
          </Card>

          <Card title="证据" sub="建议必须引用允许集合内的证据，否则整条作废">
            {data.evidence.length === 0 ? (
              <Empty>没有证据 ID。</Empty>
            ) : (
              <div className="row">
                {data.evidence.map((item) => (
                  <span className="badge neutral mono" key={item}>
                    {item}
                  </span>
                ))}
              </div>
            )}
          </Card>

          <Card title="相似案例" sub="检索自历史归因与 7 日结果">
            {data.similar_cases.length === 0 ? (
              <Empty>暂无相似案例。</Empty>
            ) : (
              <ul className="timeline">
                {data.similar_cases.map((item) => (
                  <li key={item.id}>
                    <b>{item.summary}</b>
                    <span>
                      {item.attribution}
                      {item.outcome_7d ? ` · 7 日结果 ${item.outcome_7d}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div>
          <Card title="建议">
            {!suggestion ? (
              <Empty>还没有研判结果，点右上角「生成研判」。</Empty>
            ) : (
              <>
                <div className="row" style={{ marginBottom: 10 }}>
                  <Badge tone="accent">{actionText(suggestion.action)}</Badge>
                  <StatusBadge value={suggestion.status} />
                  <span className="sub">置信 {pct(suggestion.confidence)}</span>
                </div>
                <p style={{ margin: "0 0 10px" }}>{suggestion.narrative}</p>
                <dl className="kv">
                  <dt>护栏</dt>
                  <dd>{suggestion.guardrail}</dd>
                  <dt>目标价</dt>
                  <dd>{money(suggestion.target_price)}</dd>
                  <dt>生成方式</dt>
                  <dd className="mono">{suggestion.generated_by}</dd>
                </dl>
                <div className="row" style={{ marginTop: 14 }}>
                  <Link className="btn ghost sm" to={`/suggestions/${suggestion.id}`}>
                    打开建议
                  </Link>
                  {suggestion.agent_run_id && (
                    <Link className="btn ghost sm" to={`/runs/${suggestion.agent_run_id}`}>
                      查看轨迹
                    </Link>
                  )}
                </div>
              </>
            )}
          </Card>
        </div>
      </div>
    </Page>
  );
}
