import { Link, useParams } from "react-router-dom";

import { api } from "../core/api";
import { num, parseJson, ts } from "../core/format";
import { useAsync } from "../core/hooks";
import type { AgentRunDetail } from "../core/types";
import { Badge, Card, Empty, ErrorBox, Page, Spinner, StatusBadge } from "../ui/kit";

const KIND_LABEL: Record<string, string> = {
  context: "上下文",
  plan: "计划",
  tool: "工具",
  react: "ReAct",
  react_tool: "ReAct 工具",
  steward: "数据门禁",
  handoff: "交接",
  analysis: "归因",
  risk: "风险",
  verify: "校验",
  writer: "文案",
  suggestion: "建议",
  finalize: "完成",
  error: "错误",
};

export default function RunDetail() {
  const { id = "" } = useParams();
  const { data, error, loading } = useAsync(
    () => api.get<AgentRunDetail>(`/api/agent/runs/${encodeURIComponent(id)}`),
    [id],
  );

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  const handoffs = data.steps.filter((step) => step.kind === "handoff");

  return (
    <Page
      title="运行详情"
      desc={`${data.model} · ${ts(data.started_at)} · ${data.step_count ?? data.steps.length} 步`}
      actions={
        <Link className="btn ghost" to={`/events/${data.event_id}`}>
          查看事件
        </Link>
      }
    >
      <div className="stat-grid">
        <div className="stat">
          <div className="stat-label">状态</div>
          <div className="stat-value" style={{ fontSize: 20 }}>
            <StatusBadge value={data.status} />
          </div>
          <div className="stat-hint">触发来源 {data.trigger}</div>
        </div>
        <div className="stat">
          <div className="stat-label">耗时</div>
          <div className="stat-value">{data.latency_ms ?? "—"}ms</div>
        </div>
        <div className="stat">
          <div className="stat-label">Token</div>
          <div className="stat-value">{num((data.prompt_tokens ?? 0) + (data.completion_tokens ?? 0))}</div>
          <div className="stat-hint">成本 ¥{(data.cost ?? 0).toFixed(4)}</div>
        </div>
        <div className="stat">
          <div className="stat-label">交接次数</div>
          <div className="stat-value">{handoffs.length}</div>
          <div className="stat-hint">上限 2 次</div>
        </div>
      </div>

      <Card title="执行步骤" sub="按顺序记录，可作为审计依据" flush>
        {data.steps.length === 0 ? (
          <Empty>没有步骤记录。</Empty>
        ) : (
          <ul className="timeline" style={{ padding: "14px 20px" }}>
            {data.steps.map((step) => {
              const output = parseJson<Record<string, unknown>>(step.output);
              const input = parseJson<Record<string, unknown>>(step.input);
              return (
                <li key={step.id}>
                  <b>
                    #{step.seq} {KIND_LABEL[step.kind] ?? step.kind} · {step.name}
                  </b>
                  <span>
                    {step.status} · {step.latency_ms}ms
                    {step.kind === "handoff" && output ? ` · ${String(output ?? "")}` : ""}
                  </span>
                  {(input || output) && (
                    <details style={{ marginTop: 4 }}>
                      <summary className="hint">查看输入输出</summary>
                      <pre className="mono" style={{ whiteSpace: "pre-wrap", margin: "6px 0 0" }}>
                        {JSON.stringify({ input, output }, null, 2).slice(0, 1400)}
                      </pre>
                    </details>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <Card title="提示">
        <p className="hint" style={{ margin: 0 }}>
          <Badge tone="accent">不变量</Badge> 动作由确定性策略给出（<code>agent._decide_action</code>），
          模型只写解释；证据闭包不通过时整条建议作废。
        </p>
      </Card>
    </Page>
  );
}
