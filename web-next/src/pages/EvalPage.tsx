import { useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import { Card, Empty, ErrorBox, Loader, Metric, PageHead } from "../components/ui";
import { formatTs, percent } from "../format";
import { useAsync } from "../hooks";
import { ACTION_TEXT } from "../labels";
import type { EvalCase, EvalRun, GateStatus } from "../types";

export default function EvalPage() {
  const { me } = useAuth();
  const canRun = me?.role === "admin" || me?.role === "manager";
  const { data, error, loading, reload } = useAsync(async () => {
    const [cases, gate] = await Promise.all([
      api.get<EvalCase[]>("/api/eval/cases"),
      api.get<GateStatus>("/api/gates"),
    ]);
    return { cases, gate };
  }, []);
  const cases = data?.cases;
  const gate = data?.gate;

  const [run, setRun] = useState<EvalRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function execute() {
    setBusy(true);
    setMessage("");
    try {
      setRun(await api.post<EvalRun>("/api/eval/run"));
      await reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "评测失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHead
        title="评测"
        sub="金标事件跑完整 Agent 链路：事件判定、动作、证据与护栏"
        actions={
          canRun ? (
            <button className="btn" disabled={busy} onClick={() => void execute()}>
              {busy ? "评测中…" : "运行评测"}
            </button>
          ) : undefined
        }
      />

      {message && <div className="notice">{message}</div>}

      {gate && (
        <div className={`gate-banner ${gate.ok ? "ok" : "fail"}`}>
          <div className="gate-main">
            <b>{gate.ok ? "上线门禁通过" : "上线门禁未通过"}</b>
            <span className="hint">
              {gate.enforced ? "已强制执行（研判会被拦截）" : "仅提示，未强制执行"} ·
              通过率阈值 {percent(gate.thresholds.min_accuracy)}
            </span>
          </div>
          <div className="gate-side">
            <span>
              最近评测{" "}
              {gate.latest_eval
                ? `${percent(gate.latest_eval.accuracy)} · ${formatTs(gate.latest_eval.created_at)}`
                : "无记录"}
            </span>
            <span>
              Token {gate.usage.tokens} · 回退率 {percent(gate.usage.fallback_rate)}
            </span>
          </div>
          {gate.reasons.map((reason) => (
            <p className="gate-reason" key={reason}>
              {reason}
            </p>
          ))}
          {gate.warnings.map((warning) => (
            <p className="gate-warning" key={warning}>
              {warning}
            </p>
          ))}
        </div>
      )}

      {run && (
        <>
          <div className="metric-row">
            <Metric
              label="通过率"
              value={`${(run.accuracy * 100).toFixed(0)}%`}
              sub={`${run.passed} / ${run.total}`}
              tone={run.passed === run.total ? "ok" : "danger"}
            />
            <Metric label="用例数" value={run.total} sub="金标 + 自定义" />
            <Metric
              label="失败"
              value={run.total - run.passed}
              sub={run.passed === run.total ? "全部通过" : "需要复盘"}
              tone={run.passed === run.total ? "ok" : "warn"}
            />
            <Metric label="批次" value={run.run_key} sub="评测数据已自动清理" />
          </div>

          <Card title="评测结果" sub="动作必须与金标一致，且证据链不能为空">
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>结果</th>
                    <th>用例</th>
                    <th>事件</th>
                    <th>期望动作</th>
                    <th>实际动作</th>
                    <th>证据</th>
                    <th>耗时</th>
                  </tr>
                </thead>
                <tbody>
                  {run.results.map((item) => (
                    <tr key={item.case}>
                      <td>
                        <span className={`badge ${item.passed ? "run-succeeded" : "run-failed"}`}>
                          {item.passed ? "通过" : "失败"}
                        </span>
                      </td>
                      <td>{item.case}</td>
                      <td>{item.event_type || "—"}</td>
                      <td>{ACTION_TEXT[item.expected_action] ?? item.expected_action}</td>
                      <td>
                        {item.actual_action
                          ? ACTION_TEXT[item.actual_action] ?? item.actual_action
                          : item.error || "—"}
                      </td>
                      <td className="num">{item.evidence_count ?? 0}</td>
                      <td className="num">
                        {item.latency_ms == null ? "—" : `${item.latency_ms}ms`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

      {error && <ErrorBox message={error} />}
      {loading && !cases && <Loader />}
      {cases && cases.length === 0 && <Empty>还没有金标用例。</Empty>}

      {cases && cases.length > 0 && (
        <Card
          title="金标用例"
          sub="每条用例都会在独立目标上执行，结束后自动删除"
        >
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>用例</th>
                  <th>期望事件</th>
                  <th>期望动作</th>
                  <th>说明</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((item) => (
                  <tr key={item.id}>
                    <td>{item.name}</td>
                    <td>{item.expected_event_type || "—"}</td>
                    <td>{ACTION_TEXT[item.expected_action] ?? item.expected_action}</td>
                    <td className="note-cell">{item.notes || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}
