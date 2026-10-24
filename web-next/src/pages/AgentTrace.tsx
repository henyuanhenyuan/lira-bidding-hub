import { Link, useParams } from "react-router-dom";

import { api } from "../api";
import {
  Card,
  ErrorBox,
  Loader,
  Metric,
  PageHead,
} from "../components/ui";
import { formatTs } from "../format";
import { useAsync } from "../hooks";
import { STEP_KIND_TEXT } from "../labels";
import type { AgentRunDetail, AgentStep } from "../types";

const RUN_STATUS: Record<string, string> = {
  succeeded: "成功",
  failed: "失败",
  running: "运行中",
};

function Json({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="hint">—</span>;
  const text =
    typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return <pre className="json-block">{text}</pre>;
}

function Step({ step }: { step: AgentStep }) {
  return (
    <li className="trace-step">
      <div className="trace-seq">{step.seq}</div>
      <div className="trace-main">
        <div className="trace-head">
          <span className={`badge kind-${step.kind}`}>
            {STEP_KIND_TEXT[step.kind] ?? step.kind}
          </span>
          <b>{step.name}</b>
          <span className={`badge run-${step.status === "ok" ? "succeeded" : "failed"}`}>
            {step.status === "ok" ? "成功" : "失败"}
          </span>
          <span className="hint">
            {step.latency_ms == null ? "" : `${step.latency_ms}ms`} ·{" "}
            {formatTs(step.created_at)}
          </span>
        </div>
        <details className="trace-io">
          <summary>输入 / 输出</summary>
          <div className="trace-io-grid">
            <div>
              <span className="hint">input</span>
              <Json value={step.input} />
            </div>
            <div>
              <span className="hint">output</span>
              <Json value={step.output} />
            </div>
          </div>
        </details>
      </div>
    </li>
  );
}

export default function AgentTrace() {
  const { id } = useParams<{ id: string }>();
  const { data, error, loading, reload } = useAsync(
    () => api.get<AgentRunDetail>(`/api/agent/runs/${id}`),
    [id],
  );

  if (loading && !data) return <Loader label="载入运行轨迹…" />;
  if (error && !data) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;

  return (
    <>
      <PageHead
        title="Agent 轨迹"
        sub={`${data.target_title || data.event_id} · ${formatTs(data.started_at, true)} · ${data.id.slice(0, 10)}`}
        actions={
          <>
            <Link className="btn ghost" to={`/events/${data.event_id}`}>
              来源事件
            </Link>
            {data.suggestion_id && (
              <Link className="btn ghost" to={`/suggestions/${data.suggestion_id}`}>
                查看建议
              </Link>
            )}
          </>
        }
      />

      <div className="metric-row">
        <Metric
          label="运行状态"
          value={RUN_STATUS[data.status] ?? data.status}
          sub={data.error || "无错误"}
          tone={data.status === "failed" ? "danger" : "ok"}
        />
        <Metric label="步骤" value={data.step_count} sub="每次工具调用都单独记录" />
        <Metric
          label="耗时"
          value={data.latency_ms == null ? "—" : `${data.latency_ms}ms`}
          sub="包含模型与工具"
        />
        <Metric
          label="模型"
          value={data.model || "deterministic"}
          sub={`${data.prompt_tokens ?? 0}+${data.completion_tokens ?? 0} tokens · ¥${(data.cost ?? 0).toFixed(4)} · 触发 ${data.trigger}`}
        />
      </div>

      <Card title="执行计划" sub="计划可被模型提出，但证据与动作仍由确定性策略把关">
        <Json value={data.plan} />
      </Card>

      <Card title="步骤时间线" sub="点击任意步骤展开输入与输出">
        {data.steps.length === 0 ? (
          <div className="empty">没有步骤记录</div>
        ) : (
          <ol className="trace-list">
            {data.steps.map((step) => (
              <Step step={step} key={step.id} />
            ))}
          </ol>
        )}
      </Card>
    </>
  );
}
