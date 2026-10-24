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
import type { OpsState } from "../types";

export default function Collection() {
  const { me } = useAuth();
  const isAdmin = me?.role === "admin";
  const { data, error, loading, reload } = useAsync(
    () => (isAdmin ? api.get<OpsState>("/api/ops") : Promise.resolve(null)),
    [isAdmin],
  );

  useStreamEvent(["ingest", "event"], () => void reload());

  if (!isAdmin) {
    return (
      <>
        <PageHead title="采集健康" sub="仅管理员可见" />
        <Empty>当前账号没有查看系统与采集详情的权限。</Empty>
      </>
    );
  }

  if (loading && !data) return <Loader label="载入系统状态…" />;
  if (error && !data) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;

  const { collection, freshness, inbox, scheduler, metrics, backups, connector } = data;
  const stale = collection.filter((item) => item.stale).length;

  async function scan() {
    await api.post("/api/ops/inbox-scan");
    await reload();
  }

  return (
    <>
      <PageHead
        title="采集健康"
        sub="数据新不新、RPA 有没有断、失败文件在哪里"
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
        <Metric
          label="Token / 成本 · 24h"
          value={metrics.tokens ?? 0}
          sub={`¥${(metrics.cost ?? 0).toFixed(4)}${
            metrics.daily_budget_tokens
              ? ` · 预算 ${metrics.daily_budget_tokens}`
              : " · 未设预算"
          }`}
          tone={(metrics.budget_used_ratio ?? 0) >= 1 ? "danger" : ""}
        />
      </div>

      <Card title="采集源" sub="超时会在事件页与总览标红">
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
              ["后台调度", scheduler.enabled ? "运行中" : "已关闭"],
              ["启动时间", scheduler.started_at ? formatTs(scheduler.started_at) : "—"],
              ["三方连接器", connector.configured ? "已配置" : "未配置"],
              ["消息推送", data.webhook ? "已配置" : "未配置"],
              ["登录鉴权", data.auth_enabled ? "已启用" : "未启用"],
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
