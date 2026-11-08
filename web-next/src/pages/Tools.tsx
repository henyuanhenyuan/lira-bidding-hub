import { useState } from "react";

import { api } from "../core/api";
import { useAsync } from "../core/hooks";
import type { Health, Metrics, ToolSpec } from "../core/types";
import { Badge, Card, Empty, ErrorBox, Field, Page, Spinner, Table } from "../ui/kit";

interface ToolRow extends ToolSpec {
  risk: string;
}

export default function Tools() {
  const { data, error, loading } = useAsync(async () => {
    const [tools, health, metrics] = await Promise.all([
      api.get<ToolRow[]>("/api/tools"),
      api.get<Health>("/api/health"),
      api.get<Metrics>("/api/metrics"),
    ]);
    return { tools, health, metrics };
  }, []);

  const [prompt, setPrompt] = useState("用一句话说明：为什么处置动作不能由模型决定？");
  const [output, setOutput] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

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
        const lines = buffer.split("\n\n");
        buffer = lines.pop() ?? "";
        for (const frame of lines) {
          const dataLine = frame.split("\n").find((line) => line.startsWith("data: "));
          if (!dataLine) continue;
          try {
            const payload = JSON.parse(dataLine.slice(6)) as { text?: string };
            if (payload.text) setOutput((prev) => prev + payload.text);
          } catch {
            /* 忽略无法解析的帧 */
          }
        }
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "流式调用失败");
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  const { tools, health, metrics } = data;
  const models = metrics.by_model ?? [];

  return (
    <Page title="工具与 MCP" desc="Agent 可调用的工具、风险等级，以及模型网关的流式能力">
      <div className="stat-grid">
        <div className="stat">
          <div className="stat-label">工具数</div>
          <div className="stat-value">{tools.length}</div>
          <div className="stat-hint">MCP 暴露同一契约</div>
        </div>
        <div className="stat">
          <div className="stat-label">模型状态</div>
          <div className="stat-value" style={{ fontSize: 20 }}>
            {health.llm_available ? <Badge tone="ok">已连接</Badge> : <Badge tone="warn">走模板</Badge>}
          </div>
          <div className="stat-hint">回退率 {(metrics.fallback_rate * 100).toFixed(0)}%</div>
        </div>
        <div className="stat">
          <div className="stat-label">24h 调用</div>
          <div className="stat-value">{metrics.calls}</div>
          <div className="stat-hint">P95 {metrics.p95_latency_ms ?? "—"}ms</div>
        </div>
        <div className="stat">
          <div className="stat-label">Token / 成本</div>
          <div className="stat-value">{metrics.tokens}</div>
          <div className="stat-hint">¥{metrics.cost}</div>
        </div>
      </div>

      <Card title="工具清单" sub="写类工具默认不进 MCP 暴露集" flush>
        <Table head={["工具", "说明", "风险", "参数"]}>
          {tools.map((tool) => (
            <tr key={tool.name}>
              <td className="mono">{tool.name}</td>
              <td className="sub">{tool.description}</td>
              <td>
                <Badge tone={tool.risk === "read" ? "ok" : "warn"}>{tool.risk}</Badge>
              </td>
              <td className="mono sub">
                {Object.keys((tool.input_schema?.properties as object) ?? {}).join(", ") || "—"}
              </td>
            </tr>
          ))}
        </Table>
      </Card>

      <div className="split">
        <Card title="流式试跑" sub="验证 Provider 的 token 流（SSE）">
          {message && <div className="error-box">{message}</div>}
          <Field label="提示词">
            <textarea
              className="input"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
            />
          </Field>
          <div className="row">
            <button className="btn" disabled={busy || !health.llm_available} onClick={() => void stream()}>
              {busy ? "生成中…" : "开始流式生成"}
            </button>
            {!health.llm_available && <span className="hint">模型未连接，先启动 Ollama 或配置 qwen-plus。</span>}
          </div>
          {output && (
            <pre className="mono" style={{ whiteSpace: "pre-wrap", marginTop: 12, lineHeight: 1.6 }}>
              {output}
            </pre>
          )}
        </Card>

        <Card title="模型分布" flush>
          {models.length === 0 ? (
            <Empty>还没有调用记录。</Empty>
          ) : (
            <Table head={["模型", "调用", "回退", "成本"]}>
              {models.map((row) => (
                <tr key={row.model}>
                  <td className="mono">{row.model}</td>
                  <td className="num">{row.calls}</td>
                  <td className="num">{row.fallback}</td>
                  <td className="num">¥{row.cost}</td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      </div>
    </Page>
  );
}
