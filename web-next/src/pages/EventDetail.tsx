import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api";
import PriceChart from "../components/PriceChart";
import SuggestionActions from "../components/SuggestionActions";
import {
  Card,
  Empty,
  ErrorBox,
  GateBadge,
  GuardrailBadge,
  KV,
  Loader,
  PageHead,
  SeverityBadge,
  StatusBadge,
} from "../components/ui";
import { formatTs, money, percent } from "../format";
import { useAsync } from "../hooks";
import { ACTION_TEXT, TYPE_TEXT } from "../labels";
import type { EventDetail as EventDetailType, PricePoint } from "../types";

export default function EventDetail() {
  const { id } = useParams<{ id: string }>();
  const [analyzing, setAnalyzing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, error, loading, reload } = useAsync(async () => {
    const event = await api.get<EventDetailType>(`/api/events/${id}`);
    const prices = await api.get<PricePoint[]>(
      `/api/targets/${encodeURIComponent(event.target_id)}/prices`,
    );
    return { event, prices };
  }, [id]);

  if (loading && !data) return <Loader label="载入事件…" />;
  if (error && !data) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;

  const { event, prices } = data;
  const suggestion = event.suggestion;
  const latest = prices[0];
  const observe = event.gate_level === "observe";

  async function analyze() {
    setAnalyzing(true);
    setActionError(null);
    try {
      await api.post(`/api/events/${id}/analyze`);
      await reload();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "研判失败");
    } finally {
      setAnalyzing(false);
    }
  }

  return (
    <>
      <PageHead
        title={event.target_title || event.target_id}
        sub={`${TYPE_TEXT[event.type] ?? event.type} · ${formatTs(event.ts)} · 规则 ${event.rule_version}`}
        actions={
          <Link className="btn ghost" to="/events">
            返回事件流
          </Link>
        }
      />

      <div className="detail-grid">
        <Card title="事实" sub="只呈现服务端算出的数字与采集到的字段">
          <KV
            rows={[
              [
                "级别",
                <span className="kv-inline">
                  <SeverityBadge value={event.severity} />
                  <GateBadge value={event.gate_level} />
                </span>,
              ],
              ["竞品", <Link to={`/competitors/${event.target_id}`}>{event.target_title || event.target_id}</Link>],
              ["我方价", money(event.my_price)],
              ["到手价置信", latest ? percent(latest.confidence) : "—"],
              [
                "缺失字段",
                latest?.missing_fields?.length ? (
                  <span className="tag-row">
                    {latest.missing_fields.map((field) => (
                      <span className="tag" key={field}>
                        缺 {field}
                      </span>
                    ))}
                  </span>
                ) : (
                  <span className="ok-text">完整</span>
                ),
              ],
              ["说明", event.note || "—"],
            ]}
          />
        </Card>

        <Card title="价格序列" sub="阴影为到手价区间，虚线为我方价格">
          <PriceChart points={prices} myPrice={event.my_price} />
        </Card>
      </div>

      <Card
        title="建议"
        sub={
          suggestion
            ? `由 ${suggestion.generated_by} 生成 · 置信 ${percent(suggestion.confidence)}`
            : observe
              ? "数据置信度不足，系统只提供观察"
              : "尚未研判"
        }
        actions={
          suggestion ? <StatusBadge value={suggestion.status} /> : undefined
        }
      >
        {actionError && (
          <div className="error-box">
            <strong>研判失败</strong>
            <span>{actionError}</span>
          </div>
        )}
        {suggestion ? (
          <div className="suggestion-panel">
            <div className="suggestion-title">
              <strong>{ACTION_TEXT[suggestion.action] ?? suggestion.action}</strong>
              <GuardrailBadge value={suggestion.guardrail} />
              <Link className="hint" to={`/suggestions/${suggestion.id}`}>
                查看完整详情
              </Link>
              {suggestion.agent_run_id && (
                <Link className="hint" to={`/agent/${suggestion.agent_run_id}`}>
                  Agent 轨迹
                </Link>
              )}
            </div>
            <p className="narrative">{suggestion.narrative}</p>
            {suggestion.impact_low != null && suggestion.impact_high != null && (
              <p className="hint">
                每件价差 ¥{suggestion.impact_low.toFixed(2)} ~ ¥
                {suggestion.impact_high.toFixed(2)}（正数表示竞品更便宜）
              </p>
            )}
            {suggestion.guardrail_note && (
              <p className="guardrail-note">{suggestion.guardrail_note}</p>
            )}
            <SuggestionActions suggestion={suggestion} onChange={reload} />
          </div>
        ) : observe ? (
          <div className="warn-box">
            数据置信度不足，系统不给出动作建议。补齐我方价格或等待更完整的观测后再研判。
          </div>
        ) : (
          <button className="btn" disabled={analyzing} onClick={() => void analyze()}>
            {analyzing ? "研判中…" : "生成建议"}
          </button>
        )}
      </Card>

      <div className="detail-grid">
        <Card title="证据链" sub="每个 ID 都能回溯到快照或案例">
          {event.evidence.length === 0 ? (
            <Empty>没有证据 ID</Empty>
          ) : (
            <div className="tag-row">
              {event.evidence.map((item) => (
                <code className="evidence" key={item}>
                  {item}
                </code>
              ))}
            </div>
          )}
        </Card>

        <Card title="相似历史案例" sub="检索结果参与证据闭包">
          {event.similar_cases.length === 0 ? (
            <Empty>没有检索到相似案例</Empty>
          ) : (
            <ul className="case-list">
              {event.similar_cases.map((item) => (
                <li key={item.id}>
                  <div className="case-line">
                    <b>{item.summary}</b>
                    <span className="tag">价格带 {item.price_band}</span>
                  </div>
                  <p>归因：{item.attribution}</p>
                  {item.outcome_7d && <p className="ok-text">7 日结果：{item.outcome_7d}</p>}
                  <code className="evidence">case:{item.id}</code>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
