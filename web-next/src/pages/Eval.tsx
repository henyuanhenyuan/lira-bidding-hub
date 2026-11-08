import { useState } from "react";

import { api, qs } from "../core/api";
import { pct, ts } from "../core/format";
import { useAsync } from "../core/hooks";
import type { EvalBadcase, EvalRunSummary } from "../core/types";
import { Badge, Card, Empty, ErrorBox, Page, Spinner, Stat, Table } from "../ui/kit";

const TIERS = [
  { value: "smoke", label: "冒烟（easy，37 条）" },
  { value: "core", label: "核心（easy+medium）" },
  { value: "full", label: "全量（120 条）" },
];

interface RunResult {
  run_key: string;
  total: number;
  passed: number;
  accuracy: number;
  metrics: Record<string, number>;
}

export default function Eval() {
  const { data, error, loading, reload } = useAsync(async () => {
    const [runs, badcases, cases] = await Promise.all([
      api.get<EvalRunSummary[]>("/api/eval/runs" + qs({ limit: 10 })),
      api.get<EvalBadcase[]>("/api/eval/badcases" + qs({ limit: 20 })),
      api.get<unknown[]>("/api/eval/cases"),
    ]);
    return { runs, badcases, cases };
  }, []);

  const [tier, setTier] = useState("smoke");
  const [run, setRun] = useState<RunResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function execute() {
    setBusy(true);
    setMessage("");
    try {
      const result = await api.post<RunResult>("/api/eval/run" + qs({ tier }));
      setRun(result);
      await reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "评测失败");
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  return (
    <Page
      title="评测"
      desc="金标事件跑完整 Agent 链路；动作、证据、轨迹与检索指标同时校验"
      actions={
        <div className="row">
          <select className="input" value={tier} onChange={(event) => setTier(event.target.value)}>
            {TIERS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
          <button className="btn" disabled={busy} onClick={() => void execute()}>
            {busy ? "评测中…" : "运行评测"}
          </button>
        </div>
      }
    >
      {message && <div className="notice">{message}</div>}

      {run && (
        <div className="stat-grid">
          <Stat
            label="通过率"
            value={pct(run.accuracy)}
            hint={`${run.passed} / ${run.total}`}
            tone={run.passed === run.total ? "ok" : "danger"}
          />
          <Stat label="动作准确率" value={pct(run.metrics.action_accuracy ?? 0)} hint="确定性策略 vs 金标" />
          <Stat
            label="证据闭包率"
            value={pct(run.metrics.evidence_closure_rate ?? 0)}
            hint="无证据即整条作废"
          />
          <Stat
            label="检索 Recall@5"
            value={pct(run.metrics.retrieval_recall_at_k ?? 0)}
            hint={`MRR ${(run.metrics.retrieval_mrr ?? 0).toFixed(2)}`}
          />
        </div>
      )}

      <div className="split">
        <Card title="历史批次" sub="按 tier 记录，可回看分维度分数" flush>
          {data.runs.length === 0 ? (
            <Empty>还没有评测记录。</Empty>
          ) : (
            <Table head={["批次", "Tier", "通过", "动作", "证据", "检索", "时间"]}>
              {data.runs.map((item) => {
                const m = (item.metrics ?? {}) as Record<string, number>;
                return (
                  <tr key={item.run_key}>
                    <td className="mono">{item.run_key}</td>
                    <td>{item.tier ?? "legacy"}</td>
                    <td className="num">
                      {item.passed}/{item.total}
                    </td>
                    <td className="num">{pct(m.action_accuracy ?? 0)}</td>
                    <td className="num">{pct(m.evidence_closure_rate ?? 0)}</td>
                    <td className="num">{pct(m.retrieval_recall_at_k ?? 0)}</td>
                    <td className="sub">{ts(item.created_at)}</td>
                  </tr>
                );
              })}
            </Table>
          )}
        </Card>

        <Card title="坏例库" sub="每次失败自动归档，便于复盘" flush>
          {data.badcases.length === 0 ? (
            <Empty>暂无坏例。</Empty>
          ) : (
            <Table head={["用例", "场景", "原因"]}>
              {data.badcases.map((item, index) => (
                <tr key={`${item.case_name}-${index}`}>
                  <td>{item.case_name}</td>
                  <td>
                    <Badge tone="neutral">{item.segment}</Badge>
                  </td>
                  <td className="sub">{item.reason}</td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      </div>

      <Card title="金标规模" sub="smoke ⊆ core ⊆ full">
        <div className="kv">
          <dt>用例总数</dt>
          <dd>{data.cases.length} 条</dd>
          <dt>场景</dt>
          <dd>价格事件 / 护栏 / 注入对抗 / 低置信 / SOP 边界</dd>
          <dt>门禁</dt>
          <dd className="hint">
            命令行 <code>python scripts/eval_gate.py --tier smoke</code>，floor + delta 双门限
          </dd>
        </div>
      </Card>
    </Page>
  );
}
