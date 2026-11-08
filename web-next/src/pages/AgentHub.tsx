import { useState } from "react";

import { api } from "../core/api";
import { num, pct } from "../core/format";
import { useAsync } from "../core/hooks";
import type { Health, Metrics } from "../core/types";
import { Cabinet, ItemShelf, PipelineFlow } from "../ui/viz";
import { Badge, Card, Empty, ErrorBox, Field, Page, Spinner } from "../ui/kit";

interface ToolRow {
  name: string;
  description: string;
  risk: string;
  input_schema: Record<string, unknown>;
}

interface Skill {
  id: string;
  name: string;
  description?: string | null;
  event_types?: string[];
  min_severity?: string;
  allowed_tools?: string[];
  enabled?: number;
  version?: number;
}

interface SopResult {
  format: string;
  valid: boolean;
  errors: string[];
  steps: number;
}

const PIPELINE = [
  { key: "load", label: "加载" },
  { key: "planning", label: "计划" },
  { key: "tools", label: "取证" },
  { key: "react", label: "ReAct" },
  { key: "steward", label: "门禁" },
  { key: "analysis", label: "归因" },
  { key: "risk", label: "风险" },
  { key: "verification", label: "校验" },
  { key: "writer", label: "文案" },
  { key: "suggest", label: "建议" },
];

export default function AgentHub() {
  const { data, error, loading, reload } = useAsync(async () => {
    const [tools, skills, metrics, health] = await Promise.all([
      api.get<ToolRow[]>("/api/tools"),
      api.get<Skill[]>("/api/skills"),
      api.get<Metrics>("/api/metrics"),
      api.get<Health>("/api/health"),
    ]);
    return { tools, skills, metrics, health };
  }, []);

  const [prompt, setPrompt] = useState("用一句话说明：为什么处置动作不能由模型决定？");
  const [output, setOutput] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [sop, setSop] = useState<Record<string, SopResult>>({});

  async function stream() {
    setBusy(true);
    setOutput("");
    setMessage("");
    try {
      const res = await fetch("/api/llm/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          const line = frame.split("\n").find((item) => item.startsWith("data: "));
          if (!line) continue;
          try {
            const payload = JSON.parse(line.slice(6)) as { text?: string };
            if (payload.text) setOutput((prev) => prev + payload.text);
          } catch {
            /* ignore */
          }
        }
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "流式调用失败");
    } finally {
      setBusy(false);
    }
  }

  async function validate(skill: Skill) {
    setMessage("");
    try {
      const result = await api.post<SopResult>(`/api/skills/${skill.id}/validate`);
      setSop((prev) => ({ ...prev, [skill.id]: result }));
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "校验失败");
    }
  }

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  const { tools, skills, metrics, health } = data;

  return (
    <Page
      title="Agent"
      desc="研判流水线、工具契约与 Skill 剧本；MCP 暴露同一套工具"
      actions={
        <button className="btn ghost" onClick={() => void reload()}>
          刷新
        </button>
      }
    >
      {message && <div className="notice">{message}</div>}

      <div className="stat-grid">
        <div className="stat">
          <div className="stat-label">工具</div>
          <div className="stat-value">{tools.length}</div>
          <div className="stat-hint">站内与 MCP 共用</div>
        </div>
        <div className="stat">
          <div className="stat-label">Skill</div>
          <div className="stat-value">{skills.length}</div>
          <div className="stat-hint">按事件与严重度触发</div>
        </div>
        <div className="stat">
          <div className="stat-label">模型</div>
          <div className="stat-value" style={{ fontSize: 20 }}>
            {health.llm_available ? <Badge tone="ok">在线</Badge> : <Badge tone="warn">模板</Badge>}
          </div>
          <div className="stat-hint">回退率 {pct(metrics.fallback_rate)}</div>
        </div>
        <div className="stat">
          <div className="stat-label">24h 调用</div>
          <div className="stat-value">{metrics.calls}</div>
          <div className="stat-hint">Token {num(metrics.tokens)}</div>
        </div>
      </div>

      <Card title="研判流水线" sub="LangGraph 状态机；react 节点提供有界 ReAct">
        <PipelineFlow steps={PIPELINE} />
      </Card>

      <Card title="工具货架" sub="每件工具是一件商品，高度是参数数量，颜色是风险等级">
        <Cabinet title="工具商品" tag={`${tools.length} 件`}>
        <ItemShelf
          items={tools.map((tool) => ({
            id: tool.name,
            title: tool.name,
            value: Math.max(1, Object.keys((tool.input_schema?.properties as object) ?? {}).length),
            label: tool.risk,
            tone: tool.risk === "read" ? "#22d3ee" : "#fbbf24",
          }))}
        />
        </Cabinet>
      </Card>

      <Card title="Skill 货架" sub="高度是可用工具数量">
        <Cabinet title="Skill 商品" tag={`${skills.length} 件`}>
        <ItemShelf
          items={skills.map((skill) => ({
            id: skill.id,
            title: skill.name,
            value: Math.max(1, (skill.allowed_tools ?? []).length),
            label: `v${skill.version ?? 1}`,
            tone: skill.enabled ? "#8b5cf6" : "#64748b",
          }))}
        />
        </Cabinet>
      </Card>

      <div className="split">
        <Card title="Skill 剧本" sub="playbook 支持结构化 SOP">
          {skills.length === 0 ? (
            <Empty>还没有 Skill。</Empty>
          ) : (
            <div className="skill-list">
              {skills.map((skill) => {
                const result = sop[skill.id];
                return (
                  <div className="skill" key={skill.id}>
                    <div className="skill-head">
                      <b>{skill.name}</b>
                      <Badge tone={skill.enabled ? "ok" : "neutral"}>
                        {skill.enabled ? "启用" : "停用"}
                      </Badge>
                      <span className="sub">v{skill.version ?? 1}</span>
                      <span className="sub">{skill.min_severity ?? "L1"}+</span>
                      <button className="btn ghost sm" onClick={() => void validate(skill)}>
                        校验 SOP
                      </button>
                    </div>
                    {skill.description && (
                      <p className="hint" style={{ margin: "4px 0 6px" }}>
                        {skill.description}
                      </p>
                    )}
                    <div className="row">
                      {(skill.event_types ?? []).map((type) => (
                        <span className="badge accent" key={type}>
                          {type}
                        </span>
                      ))}
                      {(skill.allowed_tools ?? []).slice(0, 6).map((tool) => (
                        <span className="badge neutral mono" key={tool}>
                          {tool}
                        </span>
                      ))}
                    </div>
                    {result && (
                      <p className={`sop ${result.valid ? "ok" : "bad"}`}>
                        {result.valid ? "SOP 有效" : "SOP 有问题"} · {result.format} · {result.steps} 步
                        {result.errors.length > 0 ? ` · ${result.errors.join("；")}` : ""}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        <Card title="流式试跑" sub="验证 Provider 的 token 流（SSE）">
          <Field label="提示词">
            <textarea className="input" value={prompt} onChange={(event) => setPrompt(event.target.value)} />
          </Field>
          <div className="row">
            <button className="btn" disabled={busy || !health.llm_available} onClick={() => void stream()}>
              {busy ? "生成中…" : "开始流式生成"}
            </button>
            {!health.llm_available && <span className="hint">模型未连接，去设置里切换。</span>}
          </div>
          {output && (
            <pre className="mono" style={{ whiteSpace: "pre-wrap", marginTop: 12, lineHeight: 1.6 }}>
              {output}
            </pre>
          )}
        </Card>
      </div>
    </Page>
  );
}
