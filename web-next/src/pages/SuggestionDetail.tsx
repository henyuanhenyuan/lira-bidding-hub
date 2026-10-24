import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api";
import { canApprove, useAuth } from "../auth";
import SuggestionActions from "../components/SuggestionActions";
import {
  Card,
  ErrorBox,
  GuardrailBadge,
  KV,
  Loader,
  PageHead,
  StatusBadge,
} from "../components/ui";
import { formatTs, money, percent } from "../format";
import { useAsync } from "../hooks";
import { ACTION_TEXT, GUARDRAIL_TEXT, STEP_KIND_TEXT, WF_TEXT } from "../labels";
import type {
  AgentRunDetail,
  Execution,
  SuggestionDetail as SuggestionDetailType,
  TimelineRow,
} from "../types";

const EXEC_MODE: Record<string, string> = {
  off: "仅记录",
  preview: "预演",
  webhook: "外部执行",
};

const EXEC_STATUS: Record<string, string> = {
  pending: "执行中",
  recorded: "已记录",
  preview: "已预演",
  succeeded: "成功",
  failed: "失败",
  rolled_back: "已回滚",
};

interface OutcomeRow {
  result: string;
  note?: string | null;
  recorded_at: string;
  recorded_by?: string | null;
}

export default function SuggestionDetail() {
  const { id } = useParams<{ id: string }>();
  const { me } = useAuth();
  const [execError, setExecError] = useState<string | null>(null);
  const [confirmRollback, setConfirmRollback] = useState<string | null>(null);

  const { data, error, loading, reload } = useAsync(async () => {
    const suggestion = await api.get<SuggestionDetailType>(`/api/suggestions/${id}`);
    const timeline = await api.get<TimelineRow[]>(`/api/suggestions/${id}/timeline`);
    const outcome = await api
      .get<OutcomeRow | null>(`/api/suggestions/${id}/outcome`)
      .catch(() => null);
    const run = suggestion.agent_run_id
      ? await api
          .get<AgentRunDetail>(`/api/agent/runs/${suggestion.agent_run_id}`)
          .catch(() => null)
      : null;
    const executions = await api.get<Execution[]>(
      `/api/suggestions/${id}/executions`,
    );
    return { suggestion, timeline, outcome, run, executions };
  }, [id]);

  if (loading && !data) return <Loader label="载入建议…" />;
  if (error && !data) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;

  const { suggestion, timeline, outcome, run, executions } = data;
  const event = suggestion.event;

  async function recordOutcome(result: string) {
    await api.post(`/api/suggestions/${id}/outcome`, { result });
    await reload();
  }

  async function rollbackExecution(executionId: string) {
    setExecError(null);
    try {
      await api.post(`/api/executions/${executionId}/rollback`);
      await reload();
    } catch (err) {
      setExecError(err instanceof Error ? err.message : "回滚失败");
    }
  }

  return (
    <>
      <PageHead
        title={ACTION_TEXT[suggestion.action] ?? suggestion.action}
        sub={`${suggestion.target_title || event?.target_title || event?.target_id || "—"} · ${formatTs(suggestion.created_at)}`}
        actions={
          event ? (
            <Link className="btn ghost" to={`/events/${event.id}`}>
              查看来源事件
            </Link>
          ) : undefined
        }
      />

      <div className="detail-grid">
        <Card title="决策摘要">
          <div className="suggestion-title">
            <StatusBadge value={suggestion.status} />
            <GuardrailBadge value={suggestion.guardrail} />
            <span className="hint">
              置信 {percent(suggestion.confidence)} · {suggestion.generated_by}
            </span>
          </div>
          <p className="narrative">{suggestion.narrative}</p>
          {suggestion.impact_low != null && suggestion.impact_high != null && (
            <p className="hint">
              每件价差 {money(suggestion.impact_low)} ~ {money(suggestion.impact_high)}
            </p>
          )}
          <SuggestionActions suggestion={suggestion} onChange={reload} />
        </Card>

        <Card title="毛利护栏" sub={suggestion.guardrail_note || undefined}>
          <KV
            rows={[
              ["目标价", money(suggestion.target_price)],
              [
                "毛利率",
                suggestion.margin_at_target == null
                  ? "—"
                  : percent(suggestion.margin_at_target, 1),
              ],
              [
                "下限",
                suggestion.margin_floor == null
                  ? "—"
                  : percent(suggestion.margin_floor, 0),
              ],
              [
                "判定",
                suggestion.guardrail
                  ? GUARDRAIL_TEXT[suggestion.guardrail]
                  : "—",
              ],
              [
                "执行价",
                suggestion.executed_price == null
                  ? "未执行"
                  : money(suggestion.executed_price),
              ],
              [
                "执行时间",
                suggestion.executed_at ? formatTs(suggestion.executed_at) : "未执行",
              ],
            ]}
          />
        </Card>
      </div>

      {run && (
        <Card
          title="Agent 轨迹"
          sub={`${run.step_count} 步 · ${run.latency_ms ?? "—"}ms · ${run.model || "deterministic"}`}
          actions={<Link to={`/agent/${run.id}`}>查看完整轨迹</Link>}
        >
          <div className="trace-mini">
            {run.steps.map((step) => (
              <span
                className={`trace-chip ${step.status}`}
                key={step.id}
                title={step.name}
              >
                {step.seq}. {STEP_KIND_TEXT[step.kind] ?? step.kind}
              </span>
            ))}
          </div>
          <p className="hint" style={{ marginTop: 10 }}>
            计划、工具输入输出、证据与校验结果都可以在轨迹页回放。
          </p>
        </Card>
      )}

      <Card
        title="执行记录"
        sub="外部/本地执行都留痕；成功或已记录的执行可回滚"
      >
        {execError && <div className="error-text">{execError}</div>}
        {executions.length === 0 ? (
          <div className="empty">还没有执行记录</div>
        ) : (
          <ul className="exec-list">
            {executions.map((item) => (
              <li key={item.id}>
                <div className="exec-line">
                  <span
                    className={`badge ${
                      item.status === "failed"
                        ? "run-failed"
                        : item.status === "rolled_back"
                          ? "status-cancelled"
                          : "run-succeeded"
                    }`}
                  >
                    {EXEC_STATUS[item.status] ?? item.status}
                  </span>
                  <span className="hint">{EXEC_MODE[item.mode] ?? item.mode}</span>
                  {item.external_id && (
                    <code className="evidence">ext:{item.external_id}</code>
                  )}
                  <span className="exec-time">{formatTs(item.created_at)}</span>
                </div>
                {item.error && <p className="error-text">{item.error}</p>}
                {item.rolled_back_at && (
                  <p className="hint">回滚于 {formatTs(item.rolled_back_at)}</p>
                )}
                {canApprove(me?.role) &&
                  ["succeeded", "recorded", "preview"].includes(item.status) && (
                    <button
                      className="btn ghost small"
                      onClick={() => {
                        if (confirmRollback === item.id) {
                          setConfirmRollback(null);
                          void rollbackExecution(item.id);
                        } else {
                          setConfirmRollback(item.id);
                        }
                      }}
                    >
                      {confirmRollback === item.id ? "确认回滚" : "回滚"}
                    </button>
                  )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="审批时间线" sub="每次流转都不可跳过，且记录操作者">
        {timeline.length === 0 ? (
          <div className="empty">还没有流转记录</div>
        ) : (
          <ol className="timeline">
            {timeline.map((row) => (
              <li key={row.id}>
                <span className={`timeline-dot ${row.action}`} />
                <div>
                  <b>{WF_TEXT[row.action] ?? row.action}</b>
                  <span className="hint">
                    {row.actor} · {formatTs(row.at)}
                  </span>
                  {row.note && <p>{row.note}</p>}
                </div>
              </li>
            ))}
          </ol>
        )}
      </Card>

      {["executed", "accepted"].includes(suggestion.status) && (
        <Card
          title="7 日结果回收"
          sub="记录真实结果后会沉淀为案例，参与下一次检索"
        >
          {outcome ? (
            <KV
              rows={[
                ["结果", outcome.result],
                ["记录人", outcome.recorded_by || "—"],
                ["记录时间", formatTs(outcome.recorded_at)],
                ["备注", outcome.note || "—"],
              ]}
            />
          ) : (
            <div className="actions">
              <button className="btn ghost" onClick={() => void recordOutcome("improved")}>
                改善
              </button>
              <button className="btn ghost" onClick={() => void recordOutcome("unchanged")}>
                无变化
              </button>
              <button className="btn ghost" onClick={() => void recordOutcome("worse")}>
                变差
              </button>
            </div>
          )}
        </Card>
      )}

      {suggestion.evidence_docs && suggestion.evidence_docs.length > 0 && (
        <Card title="引用规则" sub="每条都能回到规则库切片">
          <ul className="citation-list">
            {suggestion.evidence_docs.map((doc) => (
              <li key={doc.id}>
                <div className="citation-head">
                  <b>{doc.doc_title || "规则文档"}</b>
                  <span className="hint">切片 #{doc.chunk_no + 1}</span>
                  <code className="evidence">doc:{doc.id}</code>
                </div>
                <p>{doc.content}</p>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {event && (
        <Card
          title="来源事件"
          sub={`${event.type} · ${formatTs(event.ts)}`}
          actions={<Link to={`/events/${event.id}`}>打开事件</Link>}
        >
          <KV
            rows={[
              ["说明", event.note || "—"],
              ["我方价", money(event.my_price)],
              [
                "证据",
                <span className="tag-row">
                  {event.evidence.map((item) => (
                    <code className="evidence" key={item}>
                      {item}
                    </code>
                  ))}
                </span>,
              ],
            ]}
          />
        </Card>
      )}
    </>
  );
}
