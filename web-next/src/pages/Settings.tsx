import { useEffect, useState } from "react";

import { endpoints } from "../core/api";
import { pct, shortDate } from "../core/format";
import { useAsync, useToast } from "../core/hooks";
import { Btn, Chip, Empty, Field, Panel, Toast, Toggle } from "../ui/atoms";
import { Icon } from "../ui/icons";

export default function Settings() {
  const { message, push } = useToast();
  const models = useAsync(() => endpoints.models(), []);
  const stack = useAsync(() => endpoints.finetuneStack(), []);
  const jobs = useAsync(() => endpoints.finetuneJobs(), [], { pollMs: 30000 });
  const users = useAsync(() => endpoints.users(), []);
  const ops = useAsync(() => endpoints.ops(), [], { pollMs: 20000 });

  const [route, setRoute] = useState<"ollama" | "openai">("ollama");
  const [apiBase, setApiBase] = useState("");
  const [apiModel, setApiModel] = useState("qwen-plus");
  const [apiKey, setApiKey] = useState("");
  const [probe, setProbe] = useState<string | null>(null);
  const [savingModel, setSavingModel] = useState(false);

  const [auto, setAuto] = useState(true);
  const [strategy, setStrategy] = useState("follow");
  const [undercut, setUndercut] = useState(0.02);
  const [maxDelta, setMaxDelta] = useState(0.15);
  const [minConf, setMinConf] = useState(0.8);
  const [savingAuto, setSavingAuto] = useState(false);

  const [jobName, setJobName] = useState("竞价策略 SFT v1");
  const [building, setBuilding] = useState(false);

  useEffect(() => {
    if (!models.data) return;
    setRoute(models.data.route === "openai" ? "openai" : "ollama");
    setApiBase(models.data.api.base_url);
    setApiModel(models.data.api.model);
    setAuto(models.data.autopilot.enabled);
    setStrategy(models.data.autopilot.strategy);
    setUndercut(models.data.autopilot.undercut_pct);
    setMaxDelta(models.data.autopilot.max_delta_pct);
    setMinConf(models.data.autopilot.min_confidence);
  }, [models.data]);

  async function saveModel() {
    setSavingModel(true);
    try {
      await endpoints.setModels({
        backend: "gateway",
        route,
        local_model: models.data?.local.model || "qwen3:4b",
        local_url: models.data?.local.url || "http://127.0.0.1:11434",
        api_base_url: apiBase,
        api_model: apiModel,
        api_key: apiKey || undefined,
      });
      push(route === "ollama" ? "已切换到本地推理通道" : "已切换到云端 API 通道", "ok");
      setApiKey("");
      models.reload();
    } catch (err) {
      push(err instanceof Error ? err.message : "保存失败", "error");
    } finally {
      setSavingModel(false);
    }
  }

  async function probeChannel() {
    try {
      const result = await endpoints.probeModels();
      setProbe(`${result.ok ? "连通" : "不可用"} · ${result.latency_ms}ms`);
      push(result.ok ? "模型通道连通" : "模型通道不可用", result.ok ? "ok" : "warn");
    } catch (err) {
      setProbe("不可用");
      push(err instanceof Error ? err.message : "探测失败", "error");
    }
  }

  async function saveAuto() {
    setSavingAuto(true);
    try {
      await endpoints.autopilotConfig({
        enabled: auto,
        strategy,
        undercut_pct: undercut,
        max_delta_pct: maxDelta,
        min_confidence: minConf,
      });
      push("竞价策略已保存并即时生效", "ok");
      models.reload();
    } catch (err) {
      push(err instanceof Error ? err.message : "保存失败", "error");
    } finally {
      setSavingAuto(false);
    }
  }

  async function buildDataset() {
    setBuilding(true);
    try {
      await endpoints.finetuneDataset(400);
      push("训练数据集已生成", "ok");
      stack.reload();
    } catch (err) {
      push(err instanceof Error ? err.message : "生成失败", "error");
    } finally {
      setBuilding(false);
    }
  }

  async function createJob() {
    try {
      await endpoints.finetuneCreate({
        name: jobName,
        base_model: stack.data?.student || "Qwen/Qwen3-4B",
        method: "lora",
        teacher: stack.data?.teacher || "qwen-plus",
        epochs: 2,
        lr: 2e-4,
      });
      push("微调任务已创建", "ok");
      jobs.reload();
    } catch (err) {
      push(err instanceof Error ? err.message : "创建失败", "error");
    }
  }

  return (
    <>
      <div className="dash">
        <div className="stack">
          <Panel title="模型通道" eyebrow="Inference route" tone="cyan">
            <div className="radio-row">
              <button
                className={`radio-card ${route === "ollama" ? "active" : ""}`}
                onClick={() => setRoute("ollama")}
              >
                <strong>本地部署</strong>
                <span>内网推理节点 · 低延迟 · 数据不出域</span>
              </button>
              <button
                className={`radio-card ${route === "openai" ? "active" : ""}`}
                onClick={() => setRoute("openai")}
              >
                <strong>云端 API</strong>
                <span>Qwen-Plus · 高并发 · 自动扩容</span>
              </button>
            </div>

            <div className="stack mt16" style={{ gap: 12 }}>
              {route === "openai" ? (
                <>
                  <Field label="API 地址">
                    <input className="input" value={apiBase} onChange={(e) => setApiBase(e.target.value)} />
                  </Field>
                  <div className="grid g2">
                    <Field label="模型">
                      <input className="input" value={apiModel} onChange={(e) => setApiModel(e.target.value)} />
                    </Field>
                    <Field label="密钥" hint={models.data?.api.has_key ? "已保存，留空沿用" : "尚未配置"}>
                      <input
                        className="input"
                        type="password"
                        placeholder="sk-..."
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                      />
                    </Field>
                  </div>
                </>
              ) : (
                <div className="row small muted">
                  <Icon name="cpu" size={14} />
                  本地节点 Qwen-Plus 竞价微调权重 · {models.data?.local.url}
                </div>
              )}
              <div className="row">
                <Btn tone="primary" size="sm" disabled={savingModel} onClick={() => void saveModel()}>
                  保存通道
                </Btn>
                <Btn size="sm" onClick={() => void probeChannel()}>
                  连通性探测
                </Btn>
                {probe && <Chip tone={probe.startsWith("连通") ? "green" : "rose"}>{probe}</Chip>}
              </div>
            </div>
          </Panel>

          <Panel title="竞价策略" eyebrow="Autopilot policy" tone="violet">
            <div className="spread">
              <div>
                <strong style={{ fontSize: 13 }}>自主调价</strong>
                <div className="small muted">关闭后所有调价转为人工审批</div>
              </div>
              <Toggle checked={auto} onChange={setAuto} />
            </div>
            <div className="grid g2 mt16">
              <Field label="默认策略">
                <select className="select" value={strategy} onChange={(e) => setStrategy(e.target.value)}>
                  <option value="follow">跟随竞品</option>
                  <option value="undercut">低于竞品</option>
                  <option value="match_band">贴合区间</option>
                  <option value="hold">锁定价格</option>
                </select>
              </Field>
              <Field label={`跟降幅度 ${pct(undercut)}`}>
                <input
                  className="input"
                  type="range"
                  min={0}
                  max={0.1}
                  step={0.005}
                  value={undercut}
                  onChange={(e) => setUndercut(Number(e.target.value))}
                />
              </Field>
              <Field label={`单次最大调价 ${pct(maxDelta)}`}>
                <input
                  className="input"
                  type="range"
                  min={0.02}
                  max={0.4}
                  step={0.01}
                  value={maxDelta}
                  onChange={(e) => setMaxDelta(Number(e.target.value))}
                />
              </Field>
              <Field label={`置信度阈值 ${pct(minConf)}`}>
                <input
                  className="input"
                  type="range"
                  min={0.5}
                  max={0.95}
                  step={0.01}
                  value={minConf}
                  onChange={(e) => setMinConf(Number(e.target.value))}
                />
              </Field>
            </div>
            <div className="row mt16">
              <Btn tone="primary" size="sm" disabled={savingAuto} onClick={() => void saveAuto()}>
                保存策略
              </Btn>
              <span className="small muted">低于阈值的动作会进入人工确认台</span>
            </div>
          </Panel>

          <Panel title="微调" eyebrow="LoRA / SFT" tone="amber">
            <div className="spread">
              <div className="small muted">
                教师 {stack.data?.teacher || "qwen-plus"} → 学生 {stack.data?.student || "Qwen3-4B"}
              </div>
              <Chip tone={stack.data?.installed ? "green" : "amber"}>
                {stack.data?.installed ? "训练环境就绪" : "轻量模式"}
              </Chip>
            </div>
            <div className="row mt16">
              <Btn size="sm" onClick={() => void buildDataset()} disabled={building}>
                {building ? "生成中…" : "生成数据集"}
              </Btn>
              <Chip tone="neutral">
                样本 {stack.data?.latest_dataset?.samples ?? 0} ·{" "}
                {stack.data?.latest_dataset?.name?.slice(0, 22) || "无"}
              </Chip>
            </div>
            <div className="row mt16">
              <input
                className="input"
                style={{ maxWidth: 240 }}
                value={jobName}
                onChange={(e) => setJobName(e.target.value)}
              />
              <Btn tone="soft" size="sm" onClick={() => void createJob()}>
                创建 LoRA 任务
              </Btn>
            </div>
            <div className="rows mt16">
              {(jobs.data ?? []).slice(0, 4).map((job) => (
                <div className="row-item" key={String(job.id)}>
                  <span className="run-status ok">
                    <Icon name="spark" size={14} />
                  </span>
                  <div className="grow">
                    <div className="title-line">{String(job.name)}</div>
                    <div className="sub-line">
                      {String(job.method || "lora")} · {String(job.samples || 0)} 样本 ·{" "}
                      {shortDate(String(job.created_at || ""))}
                    </div>
                  </div>
                  <Chip tone="violet">{String(job.status || "draft")}</Chip>
                </div>
              ))}
              {!jobs.data?.length && <Empty>暂无微调任务</Empty>}
            </div>
          </Panel>
        </div>

        <div className="stack">
          <Panel title="租户成员" eyebrow="5-person tenant" extra={<Chip tone="cyan">{users.data?.length ?? 0}</Chip>}>
            <div className="rows">
              {(users.data ?? []).map((user) => (
                <div className="row-item" key={user.username}>
                  <span className="avatar">{user.display_name.slice(0, 1)}</span>
                  <div className="grow">
                    <div className="title-line">{user.display_name}</div>
                    <div className="sub-line num">{user.username}</div>
                  </div>
                  <Chip tone={user.role === "admin" ? "cyan" : user.role === "manager" ? "violet" : "neutral"}>
                    {user.role_text}
                  </Chip>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="运维任务" eyebrow="Scheduled jobs" tone="green">
            <div className="row">
              {[
                { kind: "autopilot", label: "触发巡检" },
                { kind: "mapping_suggest", label: "商品匹配" },
                { kind: "outcome_review", label: "结果回收" },
              ].map((job) => (
                <Btn
                  key={job.kind}
                  size="sm"
                  onClick={async () => {
                    try {
                      const result = await endpoints.opsRun(job.kind);
                      push(`${job.label}：${result.result || "完成"}`, "ok");
                      ops.reload();
                    } catch (err) {
                      push(err instanceof Error ? err.message : "执行失败", "error");
                    }
                  }}
                >
                  {job.label}
                </Btn>
              ))}
            </div>
            <div className="rows mt16">
              {(ops.data?.scheduler.recent ?? []).slice(0, 6).map((job, i) => (
                <div className="row-item" key={i}>
                  <span className={`dot ${job.status === "ok" ? "green" : "rose"}`} />
                  <div className="grow">
                    <div className="title-line">{job.kind}</div>
                    <div className="sub-line">{job.detail || "—"}</div>
                  </div>
                  <span className="small muted num">{shortDate(job.started_at)}</span>
                </div>
              ))}
            </div>
            <div className="row mt8 small muted">
              <Icon name="clock" size={13} />
              调度器 {ops.data?.scheduler.enabled ? "运行中" : "已停止"} · 模式{" "}
              {ops.data?.scheduler.mode}
            </div>
          </Panel>

          <Panel title="成本与预算" eyebrow="Cost control">
            <dl className="kv">
              <dt>近 24h 调用</dt>
              <dd>{ops.data?.metrics.calls ?? 0}</dd>
              <dt>Token 总量</dt>
              <dd>{(ops.data?.metrics.tokens ?? 0).toLocaleString("zh-CN")}</dd>
              <dt>降级率</dt>
              <dd>{pct(ops.data?.metrics.fallback_rate ?? 0)}</dd>
              <dt>预算消耗</dt>
              <dd>
                {ops.data?.metrics.daily_budget_tokens
                  ? pct(ops.data.metrics.tokens / ops.data.metrics.daily_budget_tokens)
                  : "未设上限"}
              </dd>
            </dl>
          </Panel>
        </div>
      </div>

      <Toast message={message} />
    </>
  );
}
