import { type FormEvent, useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import {
  Card,
  Empty,
  ErrorBox,
  KV,
  Loader,
  Metric,
  PageHead,
} from "../components/ui";
import { formatTs, timeAgo } from "../format";
import { useAsync, useStreamEvent } from "../hooks";
import { CHANNEL_TEXT, COLLECT_STATUS_TEXT } from "../labels";
import type { CollectTask, OpsState, Target } from "../types";

const CHANNELS: CollectTask["channel"][] = ["rpa", "api", "manual"];
const EMPTY_TASKS: CollectTask[] = [];

export default function Collection() {
  const { me } = useAuth();
  const isAdmin = me?.role === "admin";

  const [targetId, setTargetId] = useState("");
  const [channel, setChannel] = useState<CollectTask["channel"]>("rpa");
  const [intervalMin, setIntervalMin] = useState(60);
  const [priority, setPriority] = useState(0);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const { data, error, loading, reload } = useAsync(async () => {
    if (!isAdmin) return null;
    const [ops, taskList, targets] = await Promise.all([
      api.get<OpsState>("/api/ops"),
      api.get<{ tasks: CollectTask[] }>("/api/collect/tasks"),
      api.get<Target[]>("/api/targets"),
    ]);
    return { ops, tasks: taskList.tasks ?? EMPTY_TASKS, targets };
  }, [isAdmin]);

  useStreamEvent(["ingest", "event"], () => void reload());

  if (!isAdmin) {
    return (
      <>
        <PageHead title="监控任务管理" sub="仅管理员可见" />
        <Empty>当前账号没有配置采集任务的权限。</Empty>
      </>
    );
  }

  if (loading && !data) return <Loader label="载入采集状态…" />;
  if (error && !data) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;

  const { ops, tasks, targets } = data;
  const { collection, freshness, inbox, scheduler, metrics, backups, connector } = ops;
  const stale = collection.filter((item) => item.stale).length;
  const titleOf = (id: string) =>
    targets.find((item) => item.id === id)?.title ?? id;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!targetId) {
      setFormError("先选择一个竞品目标");
      return;
    }
    setBusy(true);
    setFormError(null);
    try {
      await api.post("/api/collect/tasks", {
        target_id: targetId,
        channel,
        interval_s: Math.max(0, Math.round(intervalMin * 60)),
        priority,
      });
      await reload();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "创建失败");
    } finally {
      setBusy(false);
    }
  }

  async function cancel(taskId: string) {
    await api.delete(`/api/collect/tasks/${taskId}`);
    await reload();
  }

  async function scan() {
    await api.post("/api/ops/inbox-scan");
    await reload();
  }

  return (
    <>
      <PageHead
        title="监控任务管理"
        sub="配置采什么、多久采一次，以及采集是否正常"
        actions={
          <>
            <button className="btn ghost" onClick={() => void scan()}>
              立即扫描收件箱
            </button>
            <button className="btn ghost" onClick={() => void reload()}>
              刷新
            </button>
          </>
        }
      />

      <div className="metric-row">
        <Metric
          label="数据新鲜度"
          value={freshness.lag_hours === null ? "—" : `${freshness.lag_hours.toFixed(1)}h`}
          sub={`SLA ${freshness.sla_hours}h · ${freshness.stale ? "已超时" : "正常"}`}
          tone={freshness.stale ? "danger" : "ok"}
        />
        <Metric
          label="监控任务"
          value={tasks.filter((task) => task.status !== "cancelled").length}
          sub={`${tasks.filter((task) => task.status === "failed").length} 个失败`}
          tone={tasks.some((task) => task.status === "failed") ? "warn" : "ok"}
        />
        <Metric
          label="采集源"
          value={collection.length}
          sub={stale ? `${stale} 个滞后` : "全部正常"}
          tone={stale ? "warn" : "ok"}
        />
        <Metric
          label="待处理文件"
          value={inbox.pending}
          sub={`失败 ${inbox.failed} 个`}
          tone={inbox.failed ? "danger" : "ok"}
        />
        <Metric
          label="模型调用 · 24h"
          value={metrics.calls}
          sub={`回退率 ${(metrics.fallback_rate * 100).toFixed(0)}% · P95 ${
            metrics.p95_latency_ms ?? "—"
          }ms`}
        />
      </div>

      <Card title="新建监控任务" sub="选目标、选通道、定频率；频率为 0 表示只跑一次">
        <form className="form-grid" onSubmit={submit}>
          <label>
            <span>竞品目标</span>
            <select
              value={targetId}
              onChange={(event) => setTargetId(event.target.value)}
            >
              <option value="">请选择</option>
              {targets.map((target) => (
                <option key={target.id} value={target.id}>
                  {target.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>采集通道</span>
            <select
              value={channel}
              onChange={(event) =>
                setChannel(event.target.value as CollectTask["channel"])
              }
            >
              {CHANNELS.map((item) => (
                <option key={item} value={item}>
                  {CHANNEL_TEXT[item]}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>频率（分钟）</span>
            <input
              type="number"
              min={0}
              step={5}
              value={intervalMin}
              onChange={(event) => setIntervalMin(Number(event.target.value))}
            />
          </label>
          <label>
            <span>优先级</span>
            <input
              type="number"
              min={0}
              max={100}
              value={priority}
              onChange={(event) => setPriority(Number(event.target.value))}
            />
          </label>
          <div className="form-actions">
            <button className="btn" type="submit" disabled={busy}>
              {busy ? "创建中…" : "创建任务"}
            </button>
            {formError && <span className="hint danger">{formError}</span>}
          </div>
        </form>
      </Card>

      <Card title="任务列表" sub="停止后不再下发，历史仍可在采集日志里查">
        {tasks.length === 0 ? (
          <Empty>还没有采集任务。选一个竞品目标创建第一条。</Empty>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>目标</th>
                  <th>通道</th>
                  <th>频率</th>
                  <th>状态</th>
                  <th>下次运行</th>
                  <th>尝试</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((task) => (
                  <tr key={task.id}>
                    <td>{titleOf(task.target_id)}</td>
                    <td>{CHANNEL_TEXT[task.channel] ?? task.channel}</td>
                    <td className="num">
                      {task.interval_s > 0
                        ? `${Math.round(task.interval_s / 60)} 分钟`
                        : "单次"}
                    </td>
                    <td>
                      <span className={`badge status-${task.status}`}>
                        {COLLECT_STATUS_TEXT[task.status] ?? task.status}
                      </span>
                    </td>
                    <td className="num">
                      {task.next_run_at ? formatTs(task.next_run_at, true) : "—"}
                    </td>
                    <td className="num">
                      {task.attempts}/{task.max_attempts}
                    </td>
                    <td>
                      {task.status === "cancelled" ? (
                        <span className="hint">已停止</span>
                      ) : (
                        <button
                          className="btn ghost small"
                          onClick={() => void cancel(task.id)}
                        >
                          停止
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="采集源健康度" sub="超时会在事件页与总览标红">
        {collection.length === 0 ? (
          <Empty>还没有采集记录。</Empty>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>采集源</th>
                  <th>快照数</th>
                  <th>最后成功</th>
                  <th>滞后</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {collection.map((item) => (
                  <tr key={item.collector}>
                    <td>{item.collector}</td>
                    <td className="num">{item.snapshots}</td>
                    <td>{formatTs(item.last_ts, true)}</td>
                    <td className="num">
                      {item.lag_hours === null ? "—" : `${item.lag_hours.toFixed(1)}h`}
                    </td>
                    <td>
                      <span className={`badge ${item.stale ? "sev-L2" : "sev-L1"}`}>
                        {item.stale ? "滞后" : "正常"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="detail-grid">
        <Card title="失败文件" sub="data/inbox/failed">
          {inbox.failed_files.length === 0 ? (
            <Empty>没有失败文件</Empty>
          ) : (
            <ul className="file-list">
              {inbox.failed_files.map((file) => (
                <li key={file.name}>
                  <code>{file.name}</code>
                  <span className="hint">
                    {Math.round(file.size / 1024)} KB · {timeAgo(file.mtime)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="运行状态">
          <KV
            rows={[
              [
                "后台调度",
                scheduler.enabled ? `运行中 · ${scheduler.mode ?? "celery"}` : "已关闭",
              ],
              ["启动时间", scheduler.started_at ? formatTs(scheduler.started_at) : "—"],
              ["三方连接器", connector.configured ? "已配置" : "未配置"],
              ["消息推送", ops.webhook ? "已配置" : "未配置"],
              ["登录鉴权", ops.auth_enabled ? "已启用" : "未启用"],
              ["备份", backups[0] || "暂无"],
            ]}
          />
        </Card>
      </div>

      <Card title="最近任务" sub="只保留最近 500 条">
        {scheduler.recent.length === 0 ? (
          <Empty>暂无任务记录</Empty>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>任务</th>
                  <th>状态</th>
                  <th>开始</th>
                  <th>结果</th>
                </tr>
              </thead>
              <tbody>
                {scheduler.recent.map((job) => (
                  <tr key={job.id}>
                    <td>{job.kind}</td>
                    <td>{job.status === "ok" ? "成功" : "失败"}</td>
                    <td className="num">{formatTs(job.started_at)}</td>
                    <td className="hint">{job.detail || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
