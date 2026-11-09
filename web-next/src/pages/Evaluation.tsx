import { useState } from "react";

import { endpoints } from "../core/api";
import { compact, pct, shortDate } from "../core/format";
import { useAsync, useToast } from "../core/hooks";
import { Btn, Chip, Empty, Panel, Stat, Toast } from "../ui/atoms";
import { Icon } from "../ui/icons";
import { Bars, Gauge } from "../ui/visuals";

export default function Evaluation() {
  const { message, push } = useToast();
  const runs = useAsync(() => endpoints.evalRuns(20), [], { pollMs: 30000 });
  const gates = useAsync(() => endpoints.gates(), [], { pollMs: 30000 });
  const metrics = useAsync(() => endpoints.metrics(), [], { pollMs: 30000 });
  const [runKey, setRunKey] = useState<string | null>(null);
  const badcases = useAsync(
    () => endpoints.badcases(runKey ?? runs.data?.[0]?.run_key),
    [runKey, runs.data?.[0]?.run_key],
  );
  const [busy, setBusy] = useState(false);

  const latest = gates.data?.latest_eval ?? runs.data?.[0] ?? null;

  async function runEval() {
    setBusy(true);
    try {
      const result = await endpoints.evalRun({ retrieval: true });
      push(`评测完成：${String(result.accuracy ? pct(Number(result.accuracy)) : "已完成")}`, "ok");
      runs.reload();
      gates.reload();
    } catch (err) {
      push(err instanceof Error ? err.message : "评测失败", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="grid g4">
        <Stat
          label="最新准确率"
          accent="cyan"
          value={latest ? pct(latest.accuracy) : "—"}
          hint={latest ? `样本 ${latest.passed}/${latest.total}` : "尚未运行"}
        />
        <Stat label="质量闸门" accent={gates.data?.ok ? "green" : "rose"} value={gates.data?.ok ? "通过" : "受限"} hint={gates.data?.warnings?.[0] || "阈值校验正常"} />
        <Stat label="调用总数" accent="violet" value={compact(metrics.data?.calls ?? 0)} hint={`降级 ${pct(metrics.data?.fallback_rate ?? 0)}`} />
        <Stat label="Token 成本" accent="amber" value={compact(metrics.data?.tokens ?? 0)} hint={`≈ ¥${(metrics.data?.cost ?? 0).toFixed(2)}`} />
      </div>

      <div className="dash">
        <Panel
          title="评测运行"
          eyebrow="Eval runs"
          extra={
            <Btn tone="primary" size="sm" disabled={busy} onClick={() => void runEval()}>
              <Icon name="play" size={12} />
              {busy ? "运行中…" : "运行评测"}
            </Btn>
          }
        >
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>批次</th>
                  <th>时间</th>
                  <th className="right">样本</th>
                  <th className="right">通过</th>
                  <th>准确率</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {(runs.data ?? []).map((run) => (
                  <tr key={run.run_key} onClick={() => setRunKey(run.run_key)} style={{ cursor: "pointer" }}>
                    <td className="num" style={{ fontSize: 11 }}>
                      {run.run_key.slice(0, 10)}
                    </td>
                    <td>{shortDate(run.created_at)}</td>
                    <td className="right num">{run.total}</td>
                    <td className="right num">{run.passed}</td>
                    <td style={{ minWidth: 120 }}>
                      <div className="row" style={{ gap: 8 }}>
                        <span className="bar-track" style={{ flex: 1 }}>
                          <span
                            className="bar-fill"
                            style={{
                              width: `${run.accuracy * 100}%`,
                              background:
                                run.accuracy >= 0.8
                                  ? "linear-gradient(90deg, rgba(92,228,154,.4), var(--green))"
                                  : "linear-gradient(90deg, rgba(255,192,120,.4), var(--amber))",
                            }}
                          />
                        </span>
                        <span className="num small">{pct(run.accuracy)}</span>
                      </div>
                    </td>
                    <td>
                      <Chip tone={run.tier ? "violet" : "neutral"}>{run.tier || "full"}</Chip>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!runs.data?.length && <Empty>暂无评测批次</Empty>}
        </Panel>

        <div className="stack">
          <Panel title="质量闸门" eyebrow="Quality gate" tone={gates.data?.ok ? "green" : "rose"}>
            <div className="grid g2">
              <Gauge
                value={latest?.accuracy ?? 0}
                label={latest ? pct(latest.accuracy, 0) : "—"}
                sub="准确率"
                tone="cyan"
              />
              <Gauge
                value={1 - (metrics.data?.fallback_rate ?? 0)}
                label={pct(1 - (metrics.data?.fallback_rate ?? 0), 0)}
                sub="可用率"
                tone="violet"
              />
            </div>
            <dl className="kv mt16">
              <dt>准确率阈值</dt>
              <dd>{pct(gates.data?.thresholds.min_accuracy ?? 0)}</dd>
              <dt>降级率上限</dt>
              <dd>{pct(gates.data?.thresholds.max_fallback_rate ?? 0)}</dd>
              <dt>P95 延迟</dt>
              <dd>{metrics.data?.p95_latency_ms ?? 0} ms</dd>
            </dl>
            {gates.data?.warnings?.length ? (
              <div className="row mt8">
                {gates.data.warnings.slice(0, 2).map((w, i) => (
                  <Chip key={i} tone="amber">
                    {w}
                  </Chip>
                ))}
              </div>
            ) : null}
          </Panel>

          <Panel title="模型调用结构" eyebrow="LLM usage">
            <Bars
              tone="violet"
              items={[
                { label: "成功", value: metrics.data?.ok ?? 0 },
                { label: "降级", value: metrics.data?.fallback ?? 0 },
                { label: "Prompt", value: Math.round((metrics.data?.prompt_tokens ?? 0) / 100) },
                { label: "Completion", value: Math.round((metrics.data?.completion_tokens ?? 0) / 100) },
              ]}
            />
            <div className="small muted mt8">Token 以百为单位显示</div>
          </Panel>

          <Panel title="评测覆盖" eyebrow="Coverage">
            <dl className="kv">
              <dt>评测批次</dt>
              <dd>{runs.data?.length ?? 0}</dd>
              <dt>最佳准确率</dt>
              <dd>{pct(Math.max(0, ...(runs.data ?? []).map((r) => r.accuracy)))}</dd>
              <dt>质量闸门</dt>
              <dd>{gates.data?.ok ? "通过" : "受限"}</dd>
              <dt>自动回归</dt>
              <dd>已接入 CI</dd>
            </dl>
          </Panel>
        </div>
      </div>

      <Panel
        title="Bad Case"
        eyebrow="Failure analysis"
        extra={
          <select
            className="select"
            style={{ width: 190, padding: "6px 10px", fontSize: 11 }}
            value={runKey ?? runs.data?.[0]?.run_key ?? ""}
            onChange={(e) => setRunKey(e.target.value)}
          >
            {(runs.data ?? []).map((r) => (
              <option key={r.run_key} value={r.run_key}>
                {r.run_key.slice(0, 10)} · {pct(r.accuracy)}
              </option>
            ))}
          </select>
        }
      >
        <div className="rows">
          {(badcases.data ?? []).slice(0, 12).map((item) => (
            <div className="row-item" key={item.id}>
              <span className="run-status fail">
                <Icon name="close" size={14} />
              </span>
              <div className="grow">
                <div className="title-line">{item.case_name}</div>
                <div className="sub-line">{item.reason || item.detail || "判定偏差"}</div>
              </div>
              <Chip tone="rose">{item.difficulty || item.segment || "偏差"}</Chip>
            </div>
          ))}
          {!badcases.data?.length && <Empty>该批次没有 Bad Case</Empty>}
        </div>
      </Panel>

      <Toast message={message} />
    </>
  );
}
