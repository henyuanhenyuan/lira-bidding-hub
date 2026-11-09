import { useState } from "react";

import { api, qs } from "../core/api";
import { money, ts } from "../core/format";
import { useAsync } from "../core/hooks";
import { Badge, Card, Empty, ErrorBox, Field, Page, Spinner, StatusBadge, Table } from "../ui/kit";

interface Product {
  sku: string;
  title: string;
  price: number | null;
  cost: number | null;
  margin_floor: number | null;
  active: number;
}

interface Mapping {
  id: string;
  target_id: string;
  target_title?: string | null;
  my_sku: string;
  my_title?: string | null;
  score: number;
  status: string;
}

interface Task {
  id: string;
  target_id: string;
  channel: string;
  status: string;
  interval_s: number;
  attempts: number;
  max_attempts: number;
  created_at: string;
}

interface Freshness {
  latest_ts?: string | null;
  lag_hours: number | null;
  stale: boolean;
  sla_hours: number;
}

interface DueRow {
  id: string;
  action: string;
  status: string;
  target_title?: string | null;
  due_at: string;
  days_overdue: number;
  due: boolean;
}

interface Review {
  id: string;
  channel: string;
  target_id?: string | null;
  reason: string;
  created_at: string;
}

interface Holdout {
  treatment: { results: Record<string, number>; improvement_rate: number | null };
  control: { results: Record<string, number>; improvement_rate: number | null };
  holdout_targets: { id: string; title: string }[];
  note: string;
}

interface Gate {
  ok: boolean;
  reasons?: string[];
  warnings?: string[];
  latest_eval?: { accuracy: number; passed: number; total: number } | null;
}

interface Dashboard {
  compare: { id: string; title: string }[];
}

function rate(value: number | null): string {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

export default function Data() {
  const { data, error, loading, reload } = useAsync(async () => {
    const [products, mappings, tasks, freshness, due, holdout, gate, reviews, dash] =
      await Promise.all([
        api.get<Product[]>("/api/my-products"),
        api.get<Mapping[]>("/api/mappings"),
        api.get<{ tasks: Task[] }>("/api/collect/tasks"),
        api.get<Freshness>("/api/freshness"),
        api.get<DueRow[]>("/api/outcomes/due"),
        api.get<Holdout>("/api/experiments/holdout"),
        api.get<Gate>("/api/gates"),
        api.get<{ reviews: Review[] }>("/api/collect/reviews").catch(() => ({ reviews: [] })),
        api.get<Dashboard>("/api/dashboard"),
      ]);
    return { products, mappings, tasks: tasks.tasks, freshness, due, holdout, gate, reviews: reviews.reviews, dash };
  }, []);

  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [sku, setSku] = useState("");
  const [title, setTitle] = useState("");
  const [price, setPrice] = useState("");
  const [cost, setCost] = useState("");
  const [targetId, setTargetId] = useState("");
  const [interval, setInterval] = useState("3600");

  async function act(fn: () => Promise<unknown>, done: string) {
    setBusy(true);
    setMessage("");
    try {
      await fn();
      setMessage(done);
      await reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  const pendingMappings = data.mappings.filter((item) => item.status === "pending");
  const openTasks = data.tasks.filter((item) => item.status !== "done" && item.status !== "cancelled");
  const dueCount = data.due.filter((item) => item.due).length;
  const targets = data.dash.compare;

  return (
    <Page title="数据" desc="商品、映射、采集与回收：后端已有的数据面都在这里">
      {message && <div className="notice">{message}</div>}

      <div className="stat-grid">
        <div className="stat">
          <div className="stat-label">我方商品</div>
          <div className="stat-value">{data.products.length}</div>
          <div className="stat-hint">SKU 与毛利护栏</div>
        </div>
        <div className="stat">
          <div className="stat-label">待确认映射</div>
          <div className="stat-value">{pendingMappings.length}</div>
          <div className="stat-hint">竞品 ↔ 我方 SKU</div>
        </div>
        <div className="stat">
          <div className="stat-label">采集任务</div>
          <div className="stat-value">{openTasks.length}</div>
          <div className="stat-hint">排队与运行中</div>
        </div>
        <div className="stat">
          <div className="stat-label">待回收</div>
          <div className="stat-value" style={{ color: dueCount ? "#fbbf24" : undefined }}>
            {dueCount}
          </div>
          <div className="stat-hint">7 日结果</div>
        </div>
      </div>

      <div className="workspace-grid">
        <Card
          title="商品与映射"
          sub="先有我方 SKU，再把竞品映射过来"
          extra={
            <div className="row">
              <button
                className="btn ghost sm"
                disabled={busy}
                onClick={() => act(() => api.post("/api/my-products/seed"), "示例商品已就绪")}
              >
                示例商品
              </button>
              <button
                className="btn ghost sm"
                disabled={busy}
                onClick={() =>
                  act(() => api.post("/api/mappings/suggest"), "已生成待确认映射")
                }
              >
                自动匹配
              </button>
            </div>
          }
        >
          <form
            className="row"
            style={{ marginBottom: 12, flexWrap: "wrap" }}
            onSubmit={(event) => {
              event.preventDefault();
              if (!sku.trim() || !title.trim()) return;
              void act(
                () =>
                  api.post("/api/my-products", {
                    sku: sku.trim(),
                    title: title.trim(),
                    price: price ? Number(price) : null,
                    cost: cost ? Number(cost) : null,
                  }),
                "商品已保存",
              );
              setSku("");
              setTitle("");
              setPrice("");
              setCost("");
            }}
          >
            <Field label="SKU">
              <input className="input" value={sku} onChange={(e) => setSku(e.target.value)} />
            </Field>
            <Field label="标题">
              <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
            </Field>
            <Field label="售价">
              <input className="input" value={price} onChange={(e) => setPrice(e.target.value)} />
            </Field>
            <Field label="成本">
              <input className="input" value={cost} onChange={(e) => setCost(e.target.value)} />
            </Field>
            <button className="btn sm" disabled={busy} type="submit">
              保存
            </button>
          </form>

          {data.products.length === 0 ? (
            <Empty>还没有我方商品，先生成示例或添加一条。</Empty>
          ) : (
            <Table head={["SKU", "商品", "售价", "成本 / 底线"]}>
              {data.products.map((item) => (
                <tr key={item.sku}>
                  <td className="mono">{item.sku}</td>
                  <td>{item.title}</td>
                  <td>{money(item.price)}</td>
                  <td>
                    {money(item.cost)}
                    <span className="sub">
                      {" "}
                      / {item.margin_floor == null ? "—" : `${Math.round(item.margin_floor * 100)}%`}
                    </span>
                  </td>
                </tr>
              ))}
            </Table>
          )}

          <h3 style={{ margin: "16px 0 8px", fontSize: 13 }}>映射</h3>
          {data.mappings.length === 0 ? (
            <Empty>还没有映射，点“自动匹配”生成候选。</Empty>
          ) : (
            <Table head={["竞品", "对应我方", "分数", "状态", "操作"]}>
              {data.mappings.slice(0, 12).map((item) => (
                <tr key={item.id}>
                  <td>{item.target_title ?? item.target_id}</td>
                  <td>{item.my_title ?? item.my_sku}</td>
                  <td className="mono">{item.score?.toFixed(2)}</td>
                  <td>
                    <Badge tone={item.status === "confirmed" ? "ok" : item.status === "rejected" ? "danger" : "neutral"}>
                      {item.status}
                    </Badge>
                  </td>
                  <td>
                    {item.status === "pending" && (
                      <div className="row">
                        <button
                          className="btn sm"
                          disabled={busy}
                          onClick={() =>
                            act(
                              () => api.post(`/api/mappings/${item.id}/decide`, { decision: "confirmed" }),
                              "映射已确认",
                            )
                          }
                        >
                          确认
                        </button>
                        <button
                          className="btn ghost sm"
                          disabled={busy}
                          onClick={() =>
                            act(
                              () => api.post(`/api/mappings/${item.id}/decide`, { decision: "rejected" }),
                              "已拒绝",
                            )
                          }
                        >
                          拒绝
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </Table>
          )}
        </Card>

        <Card
          title="采集与回收"
          sub={
            data.freshness.stale
              ? `数据已滞后 ${data.freshness.lag_hours ?? "—"} 小时`
              : `数据新鲜，滞后 ${data.freshness.lag_hours ?? 0} 小时`
          }
          extra={
            <Badge tone={data.freshness.stale ? "danger" : "ok"}>
              {data.freshness.stale ? "已过期" : "正常"}
            </Badge>
          }
        >
          <form
            className="row"
            style={{ marginBottom: 12, flexWrap: "wrap" }}
            onSubmit={(event) => {
              event.preventDefault();
              if (!targetId) return;
              void act(
                () =>
                  api.post("/api/collect/tasks", {
                    target_id: targetId,
                    interval_s: Number(interval) || 0,
                  }),
                "采集任务已创建",
              );
            }}
          >
            <Field label="竞品">
              <select className="input" value={targetId} onChange={(e) => setTargetId(e.target.value)}>
                <option value="">选择竞品</option>
                {targets.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="间隔（秒）">
              <input className="input" value={interval} onChange={(e) => setInterval(e.target.value)} />
            </Field>
            <button className="btn sm" disabled={busy || !targetId} type="submit">
              创建任务
            </button>
          </form>

          {data.tasks.length === 0 ? (
            <Empty>暂无采集任务。</Empty>
          ) : (
            <Table head={["竞品", "渠道", "状态", "间隔", "操作"]}>
              {data.tasks.slice(0, 8).map((item) => (
                <tr key={item.id}>
                  <td>{targets.find((t) => t.id === item.target_id)?.title ?? item.target_id}</td>
                  <td>{item.channel}</td>
                  <td>
                    <StatusBadge value={item.status} />
                  </td>
                  <td className="mono">{item.interval_s ? `${item.interval_s}s` : "单次"}</td>
                  <td>
                    <button
                      className="btn ghost sm"
                      disabled={busy}
                      onClick={() => act(() => api.del(`/api/collect/tasks/${item.id}`), "任务已取消")}
                    >
                      取消
                    </button>
                  </td>
                </tr>
              ))}
            </Table>
          )}

          <h3 style={{ margin: "16px 0 8px", fontSize: 13 }}>待回收结果</h3>
          {data.due.length === 0 ? (
            <Empty>没有到期的回收项。</Empty>
          ) : (
            <Table head={["竞品", "动作", "到期", "结果"]}>
              {data.due.slice(0, 8).map((item) => (
                <tr key={item.id}>
                  <td>{item.target_title ?? item.id.slice(0, 6)}</td>
                  <td>{item.action}</td>
                  <td className="sub">
                    {item.due ? `逾期 ${item.days_overdue} 天` : ts(item.due_at)}
                  </td>
                  <td>
                    <div className="row">
                      {[
                        ["improved", "变好"],
                        ["unchanged", "持平"],
                        ["worse", "变差"],
                      ].map(([value, label]) => (
                        <button
                          key={value}
                          className="chip"
                          disabled={busy}
                          onClick={() =>
                            act(
                              () => api.post(`/api/suggestions/${item.id}/outcome`, { result: value }),
                              "结果已记录",
                            )
                          }
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </Table>
          )}

          {data.reviews.length > 0 && (
            <>
              <h3 style={{ margin: "16px 0 8px", fontSize: 13 }}>人工复核</h3>
              <Table head={["竞品", "原因", "操作"]}>
                {data.reviews.slice(0, 6).map((item) => (
                  <tr key={item.id}>
                    <td>{item.target_id ?? "—"}</td>
                    <td className="sub">{item.reason}</td>
                    <td>
                      <div className="row">
                        <button
                          className="btn sm"
                          disabled={busy}
                          onClick={() =>
                            act(
                              () => api.post(`/api/collect/reviews/${item.id}/resolve${qs({ decision: "released" })}`),
                              "已放行",
                            )
                          }
                        >
                          放行
                        </button>
                        <button
                          className="btn ghost sm"
                          disabled={busy}
                          onClick={() =>
                            act(
                              () => api.post(`/api/collect/reviews/${item.id}/resolve${qs({ decision: "discarded" })}`),
                              "已丢弃",
                            )
                          }
                        >
                          丢弃
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </Table>
            </>
          )}
        </Card>

        <Card
          title="实验与门禁"
          sub="上线前看评测与回退率"
          extra={
            <Badge tone={data.gate.ok ? "ok" : "danger"}>{data.gate.ok ? "门禁通过" : "门禁未过"}</Badge>
          }
        >
          <dl className="kv">
            <dt>最近评测</dt>
            <dd>
              {data.gate.latest_eval
                ? `${rate(data.gate.latest_eval.accuracy)} · ${data.gate.latest_eval.passed}/${data.gate.latest_eval.total}`
                : "暂无"}
            </dd>
            <dt>已执行提升率</dt>
            <dd>{rate(data.holdout.treatment.improvement_rate)}</dd>
            <dt>对照组提升率</dt>
            <dd>{rate(data.holdout.control.improvement_rate)}</dd>
            <dt>观察组</dt>
            <dd>{data.holdout.holdout_targets.length} 个竞品</dd>
          </dl>
          {(data.gate.reasons?.length || data.gate.warnings?.length) ? (
            <ul className="insight-list" style={{ marginTop: 10 }}>
              {[...(data.gate.reasons ?? []), ...(data.gate.warnings ?? [])].map((item, index) => (
                <li key={index}>
                  <i />
                  {item}
                </li>
              ))}
            </ul>
          ) : null}
          <p className="hint" style={{ marginTop: 10 }}>{data.holdout.note}</p>
          <div className="row" style={{ marginTop: 10, flexWrap: "wrap" }}>
            <button
              className="btn ghost sm"
              disabled={busy}
              onClick={() => act(() => api.post("/api/ops/run?kind=mapping_suggest"), "映射任务已触发")}
            >
              跑映射建议
            </button>
            <button
              className="btn ghost sm"
              disabled={busy}
              onClick={() => act(() => api.post("/api/ops/run?kind=outcome_review"), "回收巡检已触发")}
            >
              跑回收巡检
            </button>
            <button
              className="btn ghost sm"
              disabled={busy}
              onClick={() => act(() => api.post("/api/ops/run?kind=backup"), "备份已触发")}
            >
              立即备份
            </button>
          </div>
        </Card>
      </div>
    </Page>
  );
}
