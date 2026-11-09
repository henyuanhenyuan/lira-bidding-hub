import { useState } from "react";

import { endpoints } from "../core/api";
import { clock, STATUS_TEXT, timeAgo } from "../core/format";
import { useAsync } from "../core/hooks";
import type { AgentRun, SpanNode } from "../core/types";
import { Chip, Empty, Panel, Skeleton } from "../ui/atoms";
import { Icon } from "../ui/icons";
import { FlowTopology, Ring } from "../ui/visuals";

const STAGE_TEXT: Record<string, string> = {
  steward: "调度",
  planning: "规划",
  tools: "工具",
  analyst: "研判",
  risk: "风控",
  verification: "校验",
  writer: "输出",
};

export default function Agents() {
  const skills = useAsync(() => endpoints.skills(), [], { pollMs: 60000 });
  const tools = useAsync(() => endpoints.tools(), [], { pollMs: 60000 });
  const runs = useAsync(() => endpoints.runs(12), [], { pollMs: 15000 });
  const traces = useAsync(() => endpoints.traces(12), [], { pollMs: 20000 });
  const [traceId, setTraceId] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);

  const activeTrace = traceId ?? traces.data?.[0]?.trace_id ?? null;
  const trace = useAsync(
    () => (activeTrace ? endpoints.trace(activeTrace) : Promise.resolve(null)),
    [activeTrace],
  );
  const runList = runs.data ?? [];
  const activeRun = runList.find((r) => r.id === (runId ?? runList[0]?.id)) ?? null;

  return (
    <>
      <Panel title="智能体编排" eyebrow="Multi-agent topology" tone="cyan">
        <FlowTopology active />
        <div className="grid g4 mt16">
          <Metric label="技能" value={skills.data?.length ?? 0} />
          <Metric label="MCP 工具" value={tools.data?.length ?? 0} />
          <Metric label="近期运行" value={runList.length} />
          <Metric
            label="成功率"
            value={
              runList.length
                ? `${Math.round(
                    (runList.filter((r) => r.status === "succeeded").length / runList.length) * 100,
                  )}%`
                : "—"
            }
          />
        </div>
      </Panel>

      <div className="dash">
        <div className="stack">
          <Panel title="技能包" eyebrow="Skills / Playbooks" extra={<Chip tone="violet">{skills.data?.length ?? 0}</Chip>}>
            <div className="grid g2">
              {(skills.data ?? []).map((skill) => (
                <div className="glass" key={skill.id} style={{ padding: 16, borderRadius: 18 }}>
                  <div className="spread">
                    <strong style={{ fontSize: 13 }}>{skill.name}</strong>
                    <Chip tone={skill.enabled ? "green" : "neutral"}>
                      {skill.enabled ? "启用" : "停用"}
                    </Chip>
                  </div>
                  <p className="small muted" style={{ marginTop: 6, minHeight: 34 }}>
                    {skill.description}
                  </p>
                  <div className="row" style={{ gap: 5, marginTop: 8 }}>
                    {skill.stages.map((stage) => (
                      <span key={stage} className="chip tone-neutral">
                        {STAGE_TEXT[stage] || stage}
                      </span>
                    ))}
                  </div>
                  <div className="row mt8" style={{ gap: 4 }}>
                    {skill.allowed_tools.slice(0, 4).map((tool) => (
                      <span key={tool} className="small muted">
                        {tool}
                      </span>
                    ))}
                    {skill.allowed_tools.length > 4 && (
                      <span className="small muted">+{skill.allowed_tools.length - 4}</span>
                    )}
                  </div>
                </div>
              ))}
              {!skills.data?.length && <Empty>暂无技能</Empty>}
            </div>
          </Panel>

          <Panel title="运行记录" eyebrow="Agent runs">
            <div className="rows">
              {runList.map((run) => (
                <button
                  key={run.id}
                  className="run-card"
                  style={{ width: "100%", textAlign: "left" }}
                  onClick={() => setRunId(run.id)}
                >
                  <span className={`run-status ${run.status === "succeeded" ? "ok" : "fail"}`}>
                    <Icon name={run.status === "succeeded" ? "check" : "close"} size={16} />
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="title-line">{run.target_title || run.event_id.slice(0, 10)}</div>
                    <div className="sub-line">
                      {run.trigger} · {run.step_count} 步 · {run.latency_ms ?? 0}ms · {timeAgo(run.started_at)}
                    </div>
                  </div>
                  <Chip tone={run.status === "succeeded" ? "green" : "rose"}>
                    {STATUS_TEXT[run.status] || run.status}
                  </Chip>
                </button>
              ))}
              {!runList.length && <Empty>暂无运行记录</Empty>}
            </div>
          </Panel>
        </div>

        <div className="stack">
          <Panel title="工具链" eyebrow="MCP tools" tone="violet" extra={<Chip tone="violet">{tools.data?.length ?? 0}</Chip>}>
            <div className="rows">
              {(tools.data ?? []).map((tool) => (
                <div className="row-item" key={tool.name}>
                  <span className="nav-icon" style={{ width: 28, height: 28 }}>
                    <Icon name="plug" size={14} />
                  </span>
                  <div className="grow">
                    <div className="title-line num" style={{ fontSize: 12 }}>
                      {tool.name}
                    </div>
                    <div className="sub-line">{tool.description}</div>
                  </div>
                  <Chip tone={tool.risk === "write" ? "amber" : "cyan"}>{tool.risk}</Chip>
                </div>
              ))}
              {!tools.data?.length && <Empty>暂无工具</Empty>}
            </div>
          </Panel>

          <Panel
            title="执行计划"
            eyebrow="ReAct trace"
            extra={activeRun && <Chip tone="cyan">{activeRun.id.slice(0, 6)}</Chip>}
          >
            {activeRun?.plan?.length ? (
              <div className="stack" style={{ gap: 8 }}>
                {activeRun.plan.map((step, i) => (
                  <div className="row-item" key={i} style={{ padding: "8px 10px" }}>
                    <Ring value={1} size={30}>
                      {i + 1}
                    </Ring>
                    <div className="grow">
                      <div className="title-line num" style={{ fontSize: 12 }}>
                        {step.tool}
                      </div>
                      <div className="sub-line">{step.reason}</div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <Empty>选择运行查看计划</Empty>
            )}
          </Panel>
        </div>
      </div>

      <Panel
        title="全链路追踪"
        eyebrow="Observability"
        extra={
          <select
            className="select"
            style={{ width: 220, padding: "6px 10px", fontSize: 11 }}
            value={activeTrace ?? ""}
            onChange={(e) => setTraceId(e.target.value)}
          >
            {(traces.data ?? []).map((t) => (
              <option key={t.trace_id} value={t.trace_id}>
                {t.trace_id.slice(0, 8)} · {t.spans} spans · {clock(t.started_at)}
              </option>
            ))}
          </select>
        }
      >
        {trace.loading ? (
          <Skeleton height={80} />
        ) : trace.data && trace.data.roots.length ? (
          <div className="trace-tree">
            {trace.data.roots.map((node) => (
              <TraceNode key={node.id} node={node} depth={0} max={maxDuration(trace.data!.roots)} />
            ))}
          </div>
        ) : (
          <Empty>暂无追踪</Empty>
        )}
      </Panel>
    </>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <div className="num" style={{ fontSize: 22 }}>
        {value}
      </div>
      <div className="small muted">{label}</div>
    </div>
  );
}

function maxDuration(nodes: SpanNode[]): number {
  let max = 1;
  const walk = (list: SpanNode[]) => {
    list.forEach((n) => {
      max = Math.max(max, n.duration_ms ?? 0);
      walk(n.children || []);
    });
  };
  walk(nodes);
  return max;
}

function TraceNode({ node, depth, max }: { node: SpanNode; depth: number; max: number }) {
  const width = Math.max(2, ((node.duration_ms ?? 0) / max) * 100);
  return (
    <>
      <div className="trace-node" style={{ paddingLeft: 8 + Math.min(depth, 6) * 13 }}>
        <span className={`dot ${node.status === "ok" ? "green" : "rose"}`} />
        <span className="trace-name">{node.name}</span>
        <span className="trace-track">
          <span className="trace-bar" style={{ width: `${width}%` }} />
        </span>
        <span className="num small muted" style={{ width: 54, textAlign: "right" }}>
          {node.duration_ms ?? 0}ms
        </span>
      </div>
      {(node.children || []).map((child) => (
        <TraceNode key={child.id} node={child} depth={depth + 1} max={max} />
      ))}
    </>
  );
}
