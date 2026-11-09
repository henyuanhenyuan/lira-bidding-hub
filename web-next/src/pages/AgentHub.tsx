import { useEffect, useMemo, useState, type FormEvent } from "react";

import { api, ApiError, qs } from "../core/api";
import { canManage, useAuth } from "../core/auth";
import { num, pct, ts } from "../core/format";
import { useAsync } from "../core/hooks";
import type {
  AgentRun,
  AgentRunDetail,
  CaseItem,
  DocHit,
  DocItem,
  EvalBadcase,
  EvalRun,
  FinetuneDataset,
  FinetuneJob,
  FinetuneStack,
  FinetuneValidation,
  GateStatus,
  Health,
  Metrics,
  Skill,
  ToolSpec,
  TraceNode,
  TraceSummary,
} from "../core/types";
import {
  CopyButton,
  Empty,
  ErrorBox,
  Loading,
  Panel,
  Seg,
  StatusBadge,
} from "../ui/kit";

interface EvalCaseRow {
  id: string;
  name: string;
  expected_action: string;
  expected_event_type?: string | null;
  created_at: string;
}

interface DocDetail extends DocItem {
  chunks: { id: string; chunk_no: number; content: string; level: string }[];
}

interface Bundle {
  runs: AgentRun[];
  skills: Skill[];
  tools: ToolSpec[];
  docs: DocItem[];
  cases: CaseItem[];
  traces: TraceSummary[];
  evals: EvalRun[];
  badcases: EvalBadcase[];
  evalCases: EvalCaseRow[];
  gates: GateStatus | null;
  metrics: Metrics | null;
  health: Health | null;
  finetune: FinetuneStack | null;
  jobs: FinetuneJob[];
}

type Tab = "runs" | "capability" | "knowledge" | "eval" | "finetune";

function preview(value: unknown, limit = 180) {
  if (value == null) return "—";
  const text = typeof value === "string" ? value : JSON.stringify(value);
  if (!text) return "—";
  return text.length > limit ? `${text.slice(0, limit)}…` : text;
}

export default function AgentHub() {
  const { me } = useAuth();
  const editable = canManage(me);
  const { data, error, loading, reload } = useAsync<Bundle>(async () => {
    const [runs, skills, tools, docs, cases, traces, evals, badcases, evalCases, gates, metrics, health, finetune, jobs] =
      await Promise.all([
        api.get<AgentRun[]>("/api/agent/runs?limit=60"),
        api.get<Skill[]>("/api/skills"),
        api.get<ToolSpec[]>("/api/tools"),
        api.get<DocItem[]>("/api/docs"),
        api.get<CaseItem[]>("/api/cases?limit=60"),
        api.get<TraceSummary[]>("/api/observability/traces?limit=30").catch(() => []),
        api.get<EvalRun[]>("/api/eval/runs?limit=12").catch(() => []),
        api.get<EvalBadcase[]>("/api/eval/badcases?limit=12").catch(() => []),
        api.get<EvalCaseRow[]>("/api/eval/cases").catch(() => []),
        api.get<GateStatus>("/api/gates").catch(() => null),
        api.get<Metrics>("/api/metrics?hours=24").catch(() => null),
        api.get<Health>("/api/health").catch(() => null),
        api.get<FinetuneStack>("/api/finetune/stack").catch(() => null),
        api.get<FinetuneJob[]>("/api/finetune/jobs?limit=20").catch(() => []),
      ]);
    return { runs, skills, tools, docs, cases, traces, evals, badcases, evalCases, gates, metrics, health, finetune, jobs };
  }, []);

  const [tab, setTab] = useState<Tab>("runs");
  const [runId, setRunId] = useState("");
  const [run, setRun] = useState<AgentRunDetail | null>(null);
  const [traceId, setTraceId] = useState("");
  const [spans, setSpans] = useState<(TraceNode & { depth: number })[]>([]);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [docQuery, setDocQuery] = useState("");
  const [docHits, setDocHits] = useState<DocHit[] | null>(null);
  const [docDetail, setDocDetail] = useState<DocDetail | null>(null);
  const [caseQuery, setCaseQuery] = useState("");
  const [caseHits, setCaseHits] = useState<CaseItem[] | null>(null);
  const [dataset, setDataset] = useState<FinetuneDataset | null>(null);
  const [validation, setValidation] = useState<FinetuneValidation | null>(null);
  const [streamPrompt, setStreamPrompt] = useState("用一句话解释价格带击穿的判定标准。");
  const [streamText, setStreamText] = useState("");
  const [streamBusy, setStreamBusy] = useState(false);

  const runs = data?.runs ?? [];
  const selectedRunId = runId || runs[0]?.id || "";

  useEffect(() => {
    if (!selectedRunId) {
      setRun(null);
      return;
    }
    let alive = true;
    void api
      .get<AgentRunDetail>(`/api/agent/runs/${selectedRunId}`)
      .then((row) => alive && setRun(row))
      .catch(() => alive && setRun(null));
    return () => {
      alive = false;
    };
  }, [selectedRunId]);

  useEffect(() => {
    const tid = traceId || data?.traces[0]?.trace_id;
    if (!tid) {
      setSpans([]);
      return;
    }
    let alive = true;
    void api
      .get<{ roots: TraceNode[] }>(`/api/observability/traces/${tid}`)
      .then((detail) => alive && setSpans(flatten(detail.roots).slice(0, 24)))
      .catch(() => alive && setSpans([]));
    return () => {
      alive = false;
    };
  }, [traceId, data?.traces[0]?.trace_id]);

  const stats = useMemo(() => {
    const total = runs.length || 1;
    const ok = runs.filter((item) => item.status === "succeeded").length;
    const latency = runs.filter((item) => item.latency_ms != null).map((item) => item.latency_ms as number);
    return {
      success: ok / total,
      steps: runs.reduce((sum, item) => sum + (item.step_count ?? 0), 0) / total,
      latency: latency.length ? latency.reduce((a, b) => a + b, 0) / latency.length : 0,
      tokens: runs.reduce((sum, item) => sum + (item.prompt_tokens ?? 0) + (item.completion_tokens ?? 0), 0),
      cost: runs.reduce((sum, item) => sum + (item.cost ?? 0), 0),
    };
  }, [runs]);

  const gates = data?.gates;
  const metrics = data?.metrics;
  const latestDataset = dataset ?? data?.finetune?.latest_dataset ?? null;
  const docs = docHits ?? data?.docs.map((doc) => ({
    id: doc.id,
    doc_id: doc.id,
    doc_title: doc.title,
    chunk_no: 0,
    content: `${doc.category ?? "知识"} · ${doc.chunk_count} 个切片`,
    score: 0,
  })) ?? [];
  const cases = caseHits ?? data?.cases ?? [];

  function flash(text: string) {
    setNotice(text);
    window.setTimeout(() => setNotice(""), 2800);
  }

  async function runEval() {
    setBusy("eval");
    try {
      const result = await api.post<{ accuracy?: number; passed?: number; total?: number }>(
        "/api/eval/run?tier=smoke&retrieval=false",
      );
      flash(`评测完成：${result.passed ?? "—"}/${result.total ?? "—"} · ${pct(result.accuracy ?? null)}`);
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "评测失败");
    } finally {
      setBusy("");
    }
  }

  async function reanalyze(eventId: string) {
    setBusy("analyze");
    try {
      await api.post(`/api/events/${encodeURIComponent(eventId)}/analyze`);
      flash("已重新研判");
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "研判失败");
    } finally {
      setBusy("");
    }
  }

  async function toggleSkill(skill: Skill) {
    try {
      await api.patch(`/api/skills/${skill.id}`, { enabled: !skill.enabled });
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "更新失败");
    }
  }

  async function validateSkill(skill: Skill) {
    try {
      const result = await api.post<{ ok?: boolean; errors?: string[] }>(`/api/skills/${skill.id}/validate`);
      flash(result.ok === false ? `剧本问题：${result.errors?.join("；") ?? "未知"}` : `${skill.name} 校验通过`);
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "校验失败");
    }
  }

  async function createSkill(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget.elements;
    const name = (form.namedItem("name") as HTMLInputElement).value.trim();
    const playbook = (form.namedItem("playbook") as HTMLTextAreaElement).value.trim();
    if (!name || !playbook) return;
    setBusy("skill");
    try {
      await api.post("/api/skills", { name, playbook, event_types: ["price_drop", "band_breach"], description: "控制台创建" });
      event.currentTarget.reset();
      flash("Skill 已创建");
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "创建失败");
    } finally {
      setBusy("");
    }
  }

  async function openDoc(id: string) {
    try {
      setDocDetail(await api.get<DocDetail>(`/api/docs/${id}`));
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "读取失败");
    }
  }

  async function searchDocs() {
    const query = docQuery.trim();
    if (!query) return;
    try {
      setDocHits(await api.get<DocHit[]>(`/api/docs/search${qs({ query, limit: 6 })}`));
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "检索失败");
    }
  }

  async function createDoc(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget.elements;
    const title = (form.namedItem("title") as HTMLInputElement).value.trim();
    const content = (form.namedItem("content") as HTMLTextAreaElement).value.trim();
    if (!title || !content) return;
    setBusy("doc");
    try {
      await api.post("/api/docs", { title, content, category: (form.namedItem("category") as HTMLInputElement).value || "规则", source: "console" });
      event.currentTarget.reset();
      flash("知识已入库并切片");
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "入库失败");
    } finally {
      setBusy("");
    }
  }

  async function searchCases() {
    const query = caseQuery.trim();
    if (!query) return;
    try {
      setCaseHits(await api.get<CaseItem[]>(`/api/cases/search${qs({ q: query, limit: 8 })}`));
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "检索失败");
    }
  }

  async function seedCases() {
    setBusy("seed");
    try {
      const result = await api.post<{ added: number; total: number }>("/api/cases/seed");
      flash(`补充 ${result.added} 条示例案例，共 ${result.total} 条`);
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "写入失败");
    } finally {
      setBusy("");
    }
  }

  async function createCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget.elements;
    const summary = (form.namedItem("summary") as HTMLInputElement).value.trim();
    const attribution = (form.namedItem("attribution") as HTMLTextAreaElement).value.trim();
    if (!summary || !attribution) return;
    setBusy("case");
    try {
      await api.post("/api/cases", {
        category: (form.namedItem("category") as HTMLInputElement).value || "价格战",
        event_type: "price_drop",
        price_band: "100-300",
        summary,
        attribution,
        decision: "hold",
        outcome_7d: "unchanged",
      });
      event.currentTarget.reset();
      flash("案例已写入");
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "写入失败");
    } finally {
      setBusy("");
    }
  }

  async function streamTest() {
    const prompt = streamPrompt.trim();
    if (!prompt || streamBusy) return;
    setStreamBusy(true);
    setStreamText("");
    try {
      const response = await fetch("/api/llm/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });
      if (!response.ok || !response.body) throw new Error(response.status === 403 ? "需要管理员权限" : `HTTP ${response.status}`);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() ?? "";
        for (const block of blocks) {
          const lines = block.split("\n");
          const event = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
          const payload = lines.find((line) => line.startsWith("data:"))?.slice(5).trim();
          if (event !== "token" || !payload) continue;
          try {
            const parsed = JSON.parse(payload) as { text?: string };
            if (parsed.text) setStreamText((value) => value + parsed.text);
          } catch {
            /* 忽略半截分片 */
          }
        }
      }
    } catch (err) {
      flash(err instanceof Error ? err.message : "流式试跑失败");
    } finally {
      setStreamBusy(false);
    }
  }

  async function buildDataset() {
    setBusy("dataset");
    try {
      const result = await api.post<FinetuneDataset>("/api/finetune/dataset", { limit: 400 });
      setDataset(result);
      flash(`数据集已生成：${result.samples} 条`);
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "生成失败");
    } finally {
      setBusy("");
    }
  }

  async function createJob(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget.elements;
    const name = (form.namedItem("name") as HTMLInputElement).value.trim();
    if (!name) return;
    setBusy("job");
    try {
      await api.post<FinetuneJob>("/api/finetune/jobs", {
        name,
        base_model: (form.namedItem("base_model") as HTMLInputElement).value || "Qwen/Qwen3-4B",
        method: (form.namedItem("method") as HTMLSelectElement).value,
        teacher: "qwen-plus",
        epochs: Number((form.namedItem("epochs") as HTMLInputElement).value || 2),
      });
      flash("训练任务已创建");
      setValidation(null);
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "创建失败");
    } finally {
      setBusy("");
    }
  }

  async function validateJob(job: FinetuneJob) {
    setBusy(`validate-${job.id}`);
    try {
      const result = await api.post<FinetuneValidation>(`/api/finetune/jobs/${job.id}/validate`);
      setValidation(result);
      flash(result.ok ? "数据与配置校验通过" : `校验未通过：${result.errors.join("；")}`);
      await reload();
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "校验失败");
    } finally {
      setBusy("");
    }
  }

  if (loading && !data) return <Loading rows={5} />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  return (
    <div className="stack gap-16 fade-in">
      {notice && (
        <div className="badge mint" style={{ whiteSpace: "normal", padding: "9px 12px", alignSelf: "flex-start" }}>
          {notice}
        </div>
      )}

      <Seg
        value={tab}
        onChange={setTab}
        items={[
          { key: "runs", label: "运行轨迹", sub: `${runs.length} 次` },
          { key: "capability", label: "能力矩阵", sub: `${data.skills.length} Skill` },
          { key: "knowledge", label: "知识与案例", sub: `${data.docs.length} 篇` },
          { key: "eval", label: "评测门禁", sub: `${data.evals.length} 次` },
          { key: "finetune", label: "LoRA / SFT", sub: `${data.jobs.length} 任务` },
        ]}
      />

      {tab === "runs" && (
        <>
          <div className="grid g6">
            {[
              ["运行记录", runs.length],
              ["成功率", pct(stats.success)],
              ["平均步数", stats.steps.toFixed(1)],
              ["平均耗时", `${Math.round(stats.latency)}ms`],
              ["Token", num(stats.tokens)],
              ["评测", gates?.latest_eval ? pct(gates.latest_eval.accuracy) : "—"],
            ].map(([label, value]) => (
              <div className="kpi" key={label as string}>
                <span className="kpi-label">{label as string}</span>
                <span className="kpi-value" style={{ fontSize: 22 }}>{value}</span>
              </div>
            ))}
          </div>

          <div className="split-2">
            <Panel title="运行历史" sub="最近 60 次" right={<button className="btn sm ghost" onClick={() => void reload()}>刷新</button>}>
              {runs.length === 0 ? (
                <Empty text="还没有运行记录" />
              ) : (
                <div className="stack gap-6" style={{ maxHeight: 560, overflowY: "auto" }}>
                  {runs.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className="driver"
                      style={{
                        gridTemplateColumns: "1fr auto",
                        textAlign: "left",
                        cursor: "pointer",
                        borderColor: item.id === selectedRunId ? "rgba(91,225,255,.4)" : undefined,
                      }}
                      onClick={() => setRunId(item.id)}
                    >
                      <span className="stack" style={{ lineHeight: 1.3, minWidth: 0 }}>
                        <span style={{ fontSize: 12.5, fontWeight: 600 }}>{item.target_title ?? item.event_id.slice(0, 8)}</span>
                        <span className="muted" style={{ fontSize: 10.5 }}>
                          {item.model || "规则"} · {item.step_count ?? 0} 步 · {item.latency_ms ?? "—"}ms · {ts(item.started_at)}
                        </span>
                      </span>
                      <StatusBadge value={item.status} />
                    </button>
                  ))}
                </div>
              )}
            </Panel>

            <Panel
              title="执行轨迹"
              sub={run ? `${run.target_title ?? run.event_id} · ${run.status}` : "选择一次运行"}
              right={run?.event_id && (
                <button className="btn sm ghost" disabled={busy === "analyze"} onClick={() => void reanalyze(run.event_id)}>
                  {busy === "analyze" ? "研判中…" : "重新研判"}
                </button>
              )}
            >
              {!run ? (
                <Empty text="选择左侧一次运行" />
              ) : (
                <div className="stack gap-12">
                  <div className="grid g4" style={{ gap: 8 }}>
                    {[
                      ["状态", run.status],
                      ["模型", run.model || "规则"],
                      ["步数", run.step_count ?? 0],
                      ["耗时", `${run.latency_ms ?? "—"}ms`],
                      ["Token", num((run.prompt_tokens ?? 0) + (run.completion_tokens ?? 0))],
                      ["Skill", run.skill_id || "默认"],
                    ].map(([label, value]) => (
                      <div className="driver" key={label as string} style={{ gridTemplateColumns: "1fr auto" }}>
                        <span className="muted" style={{ fontSize: 10 }}>{label}</span>
                        <span className="mono" style={{ fontSize: 10.5 }}>{value}</span>
                      </div>
                    ))}
                  </div>

                  <div className="timeline">
                    {run.steps.map((step) => (
                      <div className={`tl-item ${step.kind === "tool" ? "tool" : ""}`} key={step.id}>
                        <div className="row between">
                          <span style={{ fontSize: 12.5, fontWeight: 600 }}>
                            {step.seq}. {step.name}
                            <span className="badge" style={{ marginLeft: 8, fontSize: 9 }}>{step.kind}</span>
                          </span>
                          <span className="muted mono" style={{ fontSize: 9.5 }}>{step.latency_ms}ms</span>
                        </div>
                        <div className="muted" style={{ fontSize: 10.5, marginTop: 2 }}>
                          {preview(step.output ?? step.input)}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Panel>
          </div>

          <Panel
            title="执行脉冲"
            sub="span 追踪 · 检索 / 工具 / 模型"
            right={
              <div className="row gap-6 wrap">
                {data.traces.slice(0, 4).map((trace) => (
                  <button
                    key={trace.trace_id}
                    className={`btn sm ${(traceId || data.traces[0]?.trace_id) === trace.trace_id ? "primary" : "ghost"}`}
                    onClick={() => setTraceId(trace.trace_id)}
                  >
                    {trace.trace_id.slice(0, 6)}
                  </button>
                ))}
              </div>
            }
          >
            {spans.length === 0 ? (
              <Empty text="还没有 trace" />
            ) : (
              <div className="stack gap-6">
                {spans.map((span) => {
                  const max = Math.max(...spans.map((item) => item.duration_ms), 1);
                  return (
                    <div className="driver" key={span.id} style={{ gridTemplateColumns: "1fr auto", paddingLeft: 12 + span.depth * 12 }}>
                      <span className="stack" style={{ lineHeight: 1.2 }}>
                        <span style={{ fontSize: 11.5 }}>{span.name}</span>
                        <span className="bar" style={{ marginTop: 5 }}>
                          <i style={{ width: `${Math.max(4, (span.duration_ms / max) * 100)}%` }} />
                        </span>
                      </span>
                      <span className="mono muted" style={{ fontSize: 9.5 }}>{span.duration_ms}ms</span>
                    </div>
                  );
                })}
              </div>
            )}
          </Panel>
        </>
      )}

      {tab === "capability" && (
        <>
          <div className="grid g2">
            {[
              ["Python + FastAPI", "服务层", "领域路由、异步摄取与静态交付", data.health?.counts.events ?? 0, "事件"],
              ["LangGraph", "编排", "Steward → Analyst → Risk → Writer 状态机", data.skills.length, "Skill"],
              ["ReAct", "工具循环", "步数 / 时长 / 无进展三重上限", data.tools.length, "工具"],
              ["RAG · pgvector", "检索", "父子块 + 向量/关键词 RRF + 重排", data.health?.vector_index.indexed ?? 0, "向量"],
              ["MCP", "协议", "工具契约与 MCP 服务共用", data.tools.filter((tool) => tool.risk === "read").length, "只读工具"],
              ["多智能体", "协作", "结构化 handoff ≤2 次，有界上下文", 4, "角色"],
              ["评测集", "质量", "金标 + LLM-as-Judge + 门禁", gates?.latest_eval?.total ?? 0, "用例"],
              ["PostgreSQL", "统一存储", "业务表 + 向量表 + 评测库同一后端", data.health?.counts.snapshots ?? 0, "快照"],
            ].map(([title, tag, desc, value, unit]) => (
              <div className="kpi tilt" key={title as string}>
                <div className="row between">
                  <span className="badge cyan" style={{ fontSize: 9.5 }}>{tag as string}</span>
                  <span className="muted" style={{ fontSize: 10 }}>{unit as string}</span>
                </div>
                <span style={{ fontSize: 14, fontWeight: 600 }}>{title as string}</span>
                <span className="muted" style={{ fontSize: 11.5 }}>{desc as string}</span>
                <span className="kpi-value" style={{ fontSize: 21 }}>{num(value as number)}</span>
              </div>
            ))}
          </div>

          <div className="split-2">
            <Panel title="MCP 工具库" sub="每个工具标注风险等级" right={<span className="badge violet">MCP Server</span>}>
              <div className="grid g2" style={{ gap: 8 }}>
                {data.tools.map((tool) => (
                  <div className="kpi" key={tool.name} style={{ gap: 5 }}>
                    <div className="row between">
                      <span className="mono" style={{ fontSize: 12, color: "var(--cyan)" }}>{tool.name}</span>
                      <span className={`badge ${tool.risk === "read" ? "mint" : tool.risk === "reversible_write" ? "amber" : "rose"}`} style={{ fontSize: 9 }}>
                        {tool.risk}
                      </span>
                    </div>
                    <span className="muted" style={{ fontSize: 10.5 }}>{tool.description}</span>
                  </div>
                ))}
              </div>
            </Panel>

            <Panel title="Skill 货架" sub="剧本 + 允许工具 + 最低严重度">
              <div className="stack gap-6" style={{ maxHeight: 380, overflowY: "auto" }}>
                {data.skills.map((skill) => (
                  <div className="driver" key={skill.id} style={{ gridTemplateColumns: "1fr auto" }}>
                    <span className="stack" style={{ lineHeight: 1.3 }}>
                      <span style={{ fontSize: 12, fontWeight: 600 }}>
                        {skill.name}
                        <span className="badge cyan" style={{ marginLeft: 7, fontSize: 9 }}>{skill.enabled ? `v${skill.version}` : "停用"}</span>
                      </span>
                      <span className="muted" style={{ fontSize: 10 }}>{skill.event_types.join(" / ") || "全部事件"} · ≥ {skill.min_severity ?? "L1"}</span>
                    </span>
                    <span className="row gap-4">
                      <button className="btn sm ghost" onClick={() => void validateSkill(skill)}>校验</button>
                      <button className="btn sm ghost" disabled={!editable} onClick={() => void toggleSkill(skill)}>
                        {skill.enabled ? "停用" : "启用"}
                      </button>
                    </span>
                  </div>
                ))}
              </div>
              {editable && (
                <form className="stack gap-8 mt-16" onSubmit={(event) => void createSkill(event)}>
                  <div className="divider" />
                  <span className="eyebrow">新建 Skill</span>
                  <input className="input" name="name" placeholder="名称" required />
                  <textarea className="input" name="playbook" rows={3} placeholder="剧本：步骤 + 允许工具" required />
                  <button className="btn sm primary" disabled={busy === "skill"}>创建</button>
                </form>
              )}
            </Panel>
          </div>

          <Panel title="流式试跑" sub="验证多 Provider 网关 token 流" right={<span className="badge amber">仅管理员</span>}>
            <div className="row gap-8" style={{ alignItems: "flex-start" }}>
              <textarea className="input" rows={3} value={streamPrompt} onChange={(event) => setStreamPrompt(event.target.value)} style={{ flex: 1 }} />
              <button className="btn primary" disabled={me?.role !== "admin" || streamBusy} onClick={() => void streamTest()}>
                {streamBusy ? "流式中…" : "开始"}
              </button>
            </div>
            <pre className="muted" style={{ marginTop: 10, fontSize: 11, whiteSpace: "pre-wrap", minHeight: 60 }}>
              {streamText || (me?.role === "admin" ? "等待调用…" : "仅管理员可用")}
            </pre>
          </Panel>
        </>
      )}

      {tab === "knowledge" && (
        <div className="split-2">
          <Panel
            title="知识库"
            sub="规则文档切片后进入 pgvector"
            right={<span className="badge cyan">{data.docs.length} 篇</span>}
          >
            <div className="row gap-8">
              <input className="input" value={docQuery} onChange={(event) => setDocQuery(event.target.value)} placeholder="检索知识…" onKeyDown={(event) => event.key === "Enter" && void searchDocs()} />
              <button className="btn sm ghost" onClick={() => void searchDocs()}>检索</button>
            </div>
            {docDetail && (
              <div className="stack gap-6 mt-12">
                <div className="row between">
                  <span style={{ fontSize: 12, fontWeight: 600 }}>{docDetail.title}</span>
                  <button className="btn sm ghost" onClick={() => setDocDetail(null)}>关闭</button>
                </div>
                {docDetail.chunks.slice(0, 3).map((chunk) => (
                  <div className="driver" key={chunk.id} style={{ gridTemplateColumns: "1fr" }}>
                    <span className="muted mono" style={{ fontSize: 9 }}>#{chunk.chunk_no} · {chunk.level}</span>
                    <span className="muted" style={{ fontSize: 10.5 }}>{chunk.content.slice(0, 220)}</span>
                  </div>
                ))}
              </div>
            )}
            <div className="stack gap-6 mt-12" style={{ maxHeight: 360, overflowY: "auto" }}>
              {docs.map((doc) => (
                <button
                  key={doc.id}
                  type="button"
                  className="driver"
                  style={{ gridTemplateColumns: "1fr auto", textAlign: "left", cursor: "pointer" }}
                  onClick={() => void openDoc(doc.doc_id)}
                >
                  <span className="stack" style={{ lineHeight: 1.3 }}>
                    <span style={{ fontSize: 12, fontWeight: 600 }}>{doc.doc_title ?? doc.id}</span>
                    <span className="muted" style={{ fontSize: 10 }}>{doc.content.slice(0, 100)}</span>
                  </span>
                  {doc.score > 0 && <span className="badge cyan" style={{ fontSize: 9 }}>{doc.score.toFixed(2)}</span>}
                </button>
              ))}
              {docs.length === 0 && <Empty text="知识库为空" />}
            </div>
            {editable && (
              <form className="stack gap-8 mt-16" onSubmit={(event) => void createDoc(event)}>
                <div className="divider" />
                <span className="eyebrow">新增知识</span>
                <input className="input" name="title" placeholder="标题" required />
                <input className="input" name="category" placeholder="分类（规则 / SOP）" />
                <textarea className="input" name="content" rows={4} placeholder="正文" required />
                <button className="btn sm primary" disabled={busy === "doc"}>入库并切片</button>
              </form>
            )}
          </Panel>

          <Panel
            title="案例库"
            sub="按价格带与事件类型召回"
            right={<span className="badge violet">{data.cases.length} 条</span>}
          >
            <div className="row gap-8">
              <input className="input" value={caseQuery} onChange={(event) => setCaseQuery(event.target.value)} placeholder="检索案例…" onKeyDown={(event) => event.key === "Enter" && void searchCases()} />
              <button className="btn sm ghost" onClick={() => void searchCases()}>检索</button>
            </div>
            <div className="stack gap-6 mt-12" style={{ maxHeight: 360, overflowY: "auto" }}>
              {cases.map((item) => (
                <div className="driver" key={item.id} style={{ gridTemplateColumns: "1fr auto" }}>
                  <span className="stack" style={{ lineHeight: 1.3 }}>
                    <span style={{ fontSize: 12, fontWeight: 600 }}>{item.summary}</span>
                    <span className="muted" style={{ fontSize: 10 }}>{item.category} · {item.price_band} · {item.attribution.slice(0, 40)}</span>
                  </span>
                  <span className="badge" style={{ fontSize: 9 }}>{item.outcome_7d ?? "—"}</span>
                </div>
              ))}
              {cases.length === 0 && (
                <Empty text="案例库为空，可载入示例" />
              )}
            </div>
            <div className="row gap-6 mt-12">
              {editable && cases.length === 0 && (
                <button className="btn sm ghost" disabled={busy === "seed"} onClick={() => void seedCases()}>
                  {busy === "seed" ? "写入中…" : "载入示例案例"}
                </button>
              )}
            </div>
            {editable && (
              <form className="stack gap-8 mt-16" onSubmit={(event) => void createCase(event)}>
                <div className="divider" />
                <span className="eyebrow">新增案例</span>
                <input className="input" name="category" placeholder="分类" />
                <input className="input" name="summary" placeholder="摘要" required />
                <textarea className="input" name="attribution" rows={3} placeholder="归因" required />
                <button className="btn sm primary" disabled={busy === "case"}>写入案例</button>
              </form>
            )}
          </Panel>
        </div>
      )}

      {tab === "eval" && (
        <>
          <div className="grid g6">
            {[
              ["准确率", gates?.latest_eval ? pct(gates.latest_eval.accuracy) : "—"],
              ["通过", gates?.latest_eval ? `${gates.latest_eval.passed}/${gates.latest_eval.total}` : "—"],
              ["回退率", pct(gates?.usage.fallback_rate ?? 0)],
              ["Token", num(gates?.usage.tokens ?? 0)],
              ["坏例", data.badcases.length],
              ["门禁", gates?.ok ? "通过" : "未达标"],
            ].map(([label, value]) => (
              <div className="kpi" key={label as string}>
                <span className="kpi-label">{label as string}</span>
                <span className="kpi-value" style={{ fontSize: 21 }}>{value}</span>
              </div>
            ))}
          </div>

          <Panel
            title="评测记录"
            sub="floor + delta 双门限"
            right={<button className="btn sm primary" disabled={!editable || busy === "eval"} onClick={() => void runEval()}>{busy === "eval" ? "评测中…" : "运行 smoke 评测"}</button>}
          >
            {data.evals.length === 0 ? (
              <Empty text="还没有评测记录" />
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>批次</th><th className="num">通过率</th><th className="num">用例</th><th>档位</th><th>时间</th><th>报告</th></tr></thead>
                  <tbody>
                    {data.evals.map((item) => (
                      <tr key={item.run_key}>
                        <td className="mono" style={{ fontSize: 10.5 }}>{item.run_key.slice(0, 14)}</td>
                        <td className="num mono">{pct(item.accuracy)}</td>
                        <td className="num mono">{item.passed}/{item.total}</td>
                        <td><span className="badge cyan" style={{ fontSize: 9 }}>{item.tier ?? "legacy"}</span></td>
                        <td className="muted" style={{ fontSize: 10.5 }}>{ts(item.created_at)}</td>
                        <td><a className="mono" style={{ color: "var(--cyan)", fontSize: 10.5 }} href={`/api/eval/runs/${item.run_key}/report`} target="_blank" rel="noreferrer">查看</a></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          <div className="split-2">
            <Panel title="坏例" sub="最近失败用例">
              {data.badcases.length === 0 ? <Empty text="暂无坏例" /> : (
                <div className="stack gap-6">
                  {data.badcases.map((item) => (
                    <div className="driver" key={`${item.case_name}-${item.created_at}`} style={{ gridTemplateColumns: "1fr auto" }}>
                      <span className="stack" style={{ lineHeight: 1.3 }}>
                        <span style={{ fontSize: 12 }}>{item.case_name}</span>
                        <span className="muted" style={{ fontSize: 10 }}>{item.reason}</span>
                      </span>
                      <span className="badge rose" style={{ fontSize: 9 }}>{item.difficulty}</span>
                    </div>
                  ))}
                </div>
              )}
            </Panel>

            <Panel title="金标用例" sub="动作分布">
              <div className="row wrap gap-6">
                {data.evalCases.slice(0, 20).map((item) => (
                  <span className="evidence" key={item.id}>{item.name} · {item.expected_action}</span>
                ))}
                {data.evalCases.length === 0 && <Empty text="暂无金标" />}
              </div>
            </Panel>
          </div>
        </>
      )}

      {tab === "finetune" && (
        <>
          <Panel
            title="训练链路"
            sub="qwen-plus 教师 → SFT 数据 → PEFT/TRL → Qwen3-4B 学生"
            right={<span className={`badge ${data.finetune?.installed ? "mint" : "amber"}`}>{data.finetune?.installed ? "训练依赖齐全" : "训练依赖未安装"}</span>}
          >
            <div className="row wrap gap-10" style={{ alignItems: "center" }}>
              <span className="badge violet" style={{ padding: "8px 14px" }}>qwen-plus 教师</span>
              <span className="muted">→</span>
              <span className="badge cyan" style={{ padding: "8px 14px" }}>{latestDataset?.samples ?? 0} 条 SFT</span>
              <span className="muted">→</span>
              <span className="badge amber" style={{ padding: "8px 14px" }}>{data.finetune?.framework.trainer ?? "trl.SFTTrainer"}</span>
              <span className="muted">→</span>
              <span className="badge mint" style={{ padding: "8px 14px" }}>{data.finetune?.student ?? "Qwen/Qwen3-4B"}</span>
            </div>
            <div className="grid g4 mt-16" style={{ gap: 8 }}>
              {[
                ["样本", latestDataset?.samples ?? 0],
                ["估算 tokens", latestDataset?.estimated_tokens ? num(latestDataset.estimated_tokens) : "—"],
                ["真实建议", latestDataset?.from_suggestions ?? "—"],
                ["金标", latestDataset?.from_golden ?? "—"],
              ].map(([label, value]) => (
                <div className="driver" key={label as string} style={{ gridTemplateColumns: "1fr auto" }}>
                  <span className="muted" style={{ fontSize: 10.5 }}>{label}</span>
                  <span className="mono" style={{ fontSize: 12 }}>{value}</span>
                </div>
              ))}
            </div>
            {latestDataset && (
              <div className="row between gap-8 mt-12">
                <span className="mono muted" style={{ fontSize: 9.5, overflow: "hidden", textOverflow: "ellipsis" }}>{latestDataset.path}</span>
                <CopyButton text={latestDataset.path} />
              </div>
            )}
            <div className="row wrap gap-8 mt-16">
              <button className="btn primary" disabled={!editable || busy === "dataset"} onClick={() => void buildDataset()}>
                {busy === "dataset" ? "导出中…" : "导出数据集"}
              </button>
              <span className="muted" style={{ fontSize: 11 }}>{data.finetune?.note}</span>
            </div>
          </Panel>

          <Panel
            title="训练任务"
            sub="PEFT + TRL 配置，生成即校验"
            right={<span className="badge cyan">{data.jobs.length} 个</span>}
          >
            {editable && (
              <form className="row gap-8 wrap" style={{ alignItems: "flex-end" }} onSubmit={(event) => void createJob(event)}>
                <div className="field" style={{ width: 220 }}>
                  <label>任务名</label>
                  <input className="input" name="name" defaultValue="qwen3-4b-lora-bid-v1" required />
                </div>
                <div className="field" style={{ width: 180 }}>
                  <label>基座</label>
                  <input className="input" name="base_model" defaultValue="Qwen/Qwen3-4B" />
                </div>
                <div className="field" style={{ width: 110 }}>
                  <label>方法</label>
                  <select className="input" name="method" defaultValue="lora">
                    <option value="lora">LoRA</option>
                    <option value="qlora">QLoRA</option>
                    <option value="sft">SFT</option>
                  </select>
                </div>
                <div className="field" style={{ width: 90 }}>
                  <label>Epochs</label>
                  <input className="input" name="epochs" type="number" min={1} max={6} defaultValue={2} />
                </div>
                <button className="btn primary" disabled={busy === "job" || !latestDataset}>创建任务</button>
              </form>
            )}
            <div className="table-wrap mt-16">
              <table className="table">
                <thead><tr><th>任务</th><th>基座</th><th>方法</th><th className="num">样本</th><th>状态</th><th>操作</th></tr></thead>
                <tbody>
                  {data.jobs.map((job) => (
                    <tr key={job.id}>
                      <td><span style={{ fontSize: 12 }}>{job.name}</span><div className="muted mono" style={{ fontSize: 9.5 }}>{ts(job.created_at)}</div></td>
                      <td className="mono" style={{ fontSize: 10.5 }}>{job.base_model}</td>
                      <td><span className="badge cyan" style={{ fontSize: 9 }}>{job.method.toUpperCase()}</span></td>
                      <td className="num mono">{job.samples}</td>
                      <td><StatusBadge value={job.status} /></td>
                      <td><button className="btn sm ghost" disabled={!editable || busy === `validate-${job.id}`} onClick={() => void validateJob(job)}>校验</button></td>
                    </tr>
                  ))}
                  {data.jobs.length === 0 && <tr><td colSpan={6}><Empty text="还没有微调任务" /></td></tr>}
                </tbody>
              </table>
            </div>
            {validation && (
              <div className="stack gap-6 mt-16">
                <div className="row between">
                  <span style={{ fontSize: 12, fontWeight: 600 }}>{validation.ok ? "校验通过" : "校验未通过"}</span>
                  <span className={`badge ${validation.deps_ready ? "mint" : "amber"}`}>{validation.deps_ready ? "依赖齐全" : "依赖未安装"}</span>
                </div>
                {validation.checks.map((check) => (
                  <div className="row between" key={check.name} style={{ fontSize: 10.5 }}>
                    <span className={check.ok ? "soft" : "muted"}>{check.name} · {check.detail ?? (check.ok ? "通过" : "失败")}</span>
                    <span className={check.ok ? "delta up" : "delta down"}>{check.ok ? "OK" : "FAIL"}</span>
                  </div>
                ))}
                <div className="row between gap-8">
                  <span className="mono muted" style={{ fontSize: 9.5, overflow: "hidden", textOverflow: "ellipsis" }}>{validation.train_command}</span>
                  <CopyButton text={validation.train_command} />
                </div>
              </div>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}

function flatten(nodes: TraceNode[], depth = 0): (TraceNode & { depth: number })[] {
  return nodes.flatMap((node) => [{ ...node, depth }, ...flatten(node.children ?? [], depth + 1)]);
}
