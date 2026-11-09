import { useRef, useState } from "react";

import { endpoints } from "../core/api";
import { clock, num } from "../core/format";
import { useAsync, useToast } from "../core/hooks";
import { Btn, Chip, Empty, Field, Panel, Toast } from "../ui/atoms";
import { Icon } from "../ui/icons";

const LABEL: Record<string, { name: string; desc: string; tone: "cyan" | "violet" | "amber" | "green" }> = {
  yingren: { name: "影刃 / 八爪鱼", desc: "外部采集平台，回传标准化快照", tone: "cyan" },
  native: { name: "自有爬虫", desc: "自建采集服务，或 Playwright 直采", tone: "violet" },
  api: { name: "开放 API", desc: "合作方或内部系统推送", tone: "amber" },
  manual: { name: "人工录入", desc: "运营手动补录观测", tone: "green" },
};

export default function Sources() {
  const { message, push } = useToast();
  const channels = useAsync(() => endpoints.channels(), [], { pollMs: 30000 });
  const integration = useAsync(() => endpoints.integration(), [], { pollMs: 30000 });
  const logs = useAsync(() => endpoints.crawlLogs(12), [], { pollMs: 20000 });
  const summary = useAsync(() => endpoints.collectSummary(), [], { pollMs: 30000 });

  const [form, setForm] = useState({ yingren_base_url: "", yingren_token: "", native_crawler_url: "", native_crawler_token: "" });
  const [saving, setSaving] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [upload, setUpload] = useState<{ ok: boolean; rows_ok: number; rows_dup: number; rows_rejected: number } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const items = channels.data?.items ?? [];
  const byName = Object.fromEntries(items.map((c) => [c.channel, c]));

  async function saveConfig() {
    setSaving(true);
    try {
      const payload = Object.fromEntries(Object.entries(form).filter(([, v]) => v));
      await endpoints.crawlConfig(payload);
      push("采集通道配置已保存", "ok");
      channels.reload();
    } catch (err) {
      push(err instanceof Error ? err.message : "保存失败", "error");
    } finally {
      setSaving(false);
    }
  }

  async function run(channel: string) {
    try {
      await endpoints.crawlRun({ channel, dispatch_now: true, interval_s: 0 });
      push(`${LABEL[channel]?.name || channel} 已派发采集任务`, "ok");
      logs.reload();
    } catch (err) {
      push(err instanceof Error ? err.message : "派发失败", "error");
    }
  }

  async function handleFile(file: File | undefined) {
    if (!file) return;
    try {
      const result = await endpoints.importFile(file);
      setUpload(result);
      push(
        result.ok
          ? `导入完成：${result.rows_ok} 行有效`
          : `导入被拒绝：${result.errors.length} 个错误`,
        result.ok ? "ok" : "warn",
      );
      summary.reload();
    } catch (err) {
      push(err instanceof Error ? err.message : "上传失败", "error");
    }
  }

  return (
    <>
      <div className="grid g2">
        {(["yingren", "native"] as const).map((key) => {
          const info = LABEL[key];
          const channel = byName[key];
          return (
            <Panel
              key={key}
              title={info.name}
              eyebrow={key === "yingren" ? "External platform" : "Own crawler"}
              tone={info.tone}
              extra={
                <Chip tone={channel?.configured ? "green" : "amber"}>
                  {channel?.configured ? "已配置" : "待配置"}
                </Chip>
              }
            >
              <p className="small muted" style={{ marginBottom: 12 }}>
                {info.desc}
              </p>
              <div className="stack" style={{ gap: 10 }}>
                {key === "yingren" ? (
                  <>
                    <Field label="服务地址">
                      <input
                        className="input"
                        placeholder="https://api.yingren.example.com"
                        value={form.yingren_base_url}
                        onChange={(e) => setForm({ ...form, yingren_base_url: e.target.value })}
                      />
                    </Field>
                    <Field label="访问令牌">
                      <input
                        className="input"
                        type="password"
                        placeholder="Bearer token"
                        value={form.yingren_token}
                        onChange={(e) => setForm({ ...form, yingren_token: e.target.value })}
                      />
                    </Field>
                  </>
                ) : (
                  <>
                    <Field label="服务地址" hint="留空则使用 Playwright 直采">
                      <input
                        className="input"
                        placeholder="http://127.0.0.1:9100"
                        value={form.native_crawler_url}
                        onChange={(e) => setForm({ ...form, native_crawler_url: e.target.value })}
                      />
                    </Field>
                    <Field label="访问令牌">
                      <input
                        className="input"
                        type="password"
                        placeholder="Bearer token"
                        value={form.native_crawler_token}
                        onChange={(e) => setForm({ ...form, native_crawler_token: e.target.value })}
                      />
                    </Field>
                  </>
                )}
                <div className="row">
                  <Btn tone="primary" size="sm" disabled={saving} onClick={() => void saveConfig()}>
                    保存配置
                  </Btn>
                  <Btn size="sm" onClick={() => void run(key)}>
                    <Icon name="play" size={12} />
                    立即采集
                  </Btn>
                </div>
              </div>
            </Panel>
          );
        })}
      </div>

      <div className="dash">
        <Panel title="文件接入" eyebrow="CSV / Excel" tone="green">
          <div
            className={`dropzone ${dragging ? "drag" : ""}`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              void handleFile(e.dataTransfer.files?.[0]);
            }}
          >
            <Icon name="upload" size={24} />
            <strong>拖拽文件到此处，或点击选择</strong>
            <span className="small muted">支持 CSV / XLSX / JSON，最大 20MB</span>
            <span className="small muted">
              字段：target_id, ts, list_price, title, region, source_tier
            </span>
            <input
              ref={inputRef}
              type="file"
              accept=".csv,.xlsx,.xlsm,.json"
              hidden
              onChange={(e) => void handleFile(e.target.files?.[0])}
            />
          </div>
          {upload && (
            <div className="row mt16">
              <Chip tone={upload.ok ? "green" : "rose"}>
                有效 {upload.rows_ok} · 去重 {upload.rows_dup} · 拒绝 {upload.rows_rejected}
              </Chip>
            </div>
          )}
          <div className="grid g3 mt16">
            <Mini label="近 24h 采集" value={num(summary.data ? Object.values(summary.data.outcomes).reduce((a, b) => a + b, 0) : 0)} />
            <Mini label="接入目标" value={num(integration.data?.counts.targets ?? 0)} />
            <Mini label="快照总量" value={num(integration.data?.counts.snapshots ?? 0)} />
          </div>
        </Panel>

        <Panel title="推送接口" eyebrow="Ingest API">
          <div className="stack" style={{ gap: 10 }}>
            {(integration.data?.endpoints ?? []).slice(0, 3).map((endpoint) => (
              <div className="row-item" key={endpoint.path}>
                <Chip tone="violet">{endpoint.method}</Chip>
                <div className="grow">
                  <div className="title-line num" style={{ fontSize: 12 }}>
                    {endpoint.path}
                  </div>
                  <div className="sub-line">{endpoint.description}</div>
                </div>
              </div>
            ))}
            <div className="row small muted">
              <Icon name="plug" size={14} />
              采集端使用 Bearer 令牌写入，不影响人工登录
            </div>
          </div>
        </Panel>
      </div>

      <Panel title="采集日志" eyebrow="Crawl logs">
        <div className="ticker">
          {(logs.data?.items ?? []).map((log, i) => (
            <div className="ticker-row" key={i}>
              <span className="ticker-time num">{clock(String(log.ts || ""))}</span>
              <span className="ticker-main">
                <strong>{String(log.channel || "—")}</strong>
                <span className="muted"> · {String(log.outcome || "")}</span>
                {log.error_kind ? <span className="muted"> · {String(log.error_kind)}</span> : null}
              </span>
              <span className="num small muted">{String(log.status_code || "—")}</span>
            </div>
          ))}
          {!logs.data?.items?.length && <Empty>暂无采集日志</Empty>}
        </div>
      </Panel>

      <Toast message={message} />
    </>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="num" style={{ fontSize: 20 }}>
        {value}
      </div>
      <div className="small muted">{label}</div>
    </div>
  );
}
