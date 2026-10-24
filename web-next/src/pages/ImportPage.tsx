import { useState } from "react";

import { api } from "../api";
import { Card, PageHead } from "../components/ui";

interface ImportReport {
  rows_in: number;
  rows_ok: number;
  rows_dup: number;
  rows_rejected: number;
  events_created: number;
  errors: unknown[];
}

const D1 = "2026-10-23T02:17:00+08:00";
const D2 = "2026-10-24T02:17:00+08:00";

function demoSnapshots() {
  return {
    d1: [
      {
        target_id: "t1",
        ts: D1,
        collector: "yd-v1",
        source_tier: 3,
        observation: {
          list_price: 299,
          coupons: [],
          promotions: [],
          coin: { rate: 0, cap: 0 },
          account_tier: "normal",
          title: "竞品A·洗护套装",
        },
      },
      {
        target_id: "t2",
        ts: D1,
        collector: "api-vendor",
        source_tier: 1,
        observation: {
          list_price: 199,
          coupons: [],
          promotions: [],
          coin: { rate: 0, cap: 0 },
          account_tier: "normal",
          title: "竞品B·控油洗发水",
        },
      },
      {
        target_id: "t3",
        ts: D1,
        collector: "yd-v1",
        source_tier: 3,
        observation: {
          list_price: 89,
          coupons: [],
          promotions: [],
          coin: { rate: 0, cap: 0 },
          account_tier: "normal",
          title: "竞品C·护发素",
        },
      },
    ],
    d2: [
      {
        target_id: "t1",
        ts: D2,
        collector: "yd-v1",
        source_tier: 3,
        observation: {
          list_price: 299,
          coupons: [{ kind: "shop", threshold: 299, discount: 30, stackable: false }],
          promotions: [],
          coin: { rate: 0, cap: 0 },
          account_tier: "normal",
          title: "竞品A·洗护套装",
        },
      },
      {
        target_id: "t2",
        ts: D2,
        collector: "api-vendor",
        source_tier: 1,
        observation: {
          list_price: 149,
          coupons: [],
          promotions: [],
          coin: { rate: 0, cap: 0 },
          account_tier: "normal",
          title: "竞品B·控油洗发水",
        },
      },
      {
        target_id: "t3",
        ts: D2,
        collector: "yd-v1",
        source_tier: 3,
        observation: {
          list_price: 89,
          coupons: [],
          promotions: [],
          coin: { rate: 0, cap: 0 },
          account_tier: "normal",
          title: "竞品C·护发素",
        },
      },
    ],
  };
}

export default function ImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  function append(text: string) {
    setLog((prev) => [...prev, text]);
  }

  async function upload() {
    if (!file) {
      append("请先选择 CSV 文件");
      return;
    }
    setBusy(true);
    append(`上传 ${file.name} …`);
    try {
      const report = await api.upload<ImportReport>("/v1/import/csv", file);
      append(JSON.stringify(report, null, 2));
      append("完成。到「事件」查看变化。");
    } catch (err) {
      append(`失败：${err instanceof Error ? err.message : "未知错误"}`);
    } finally {
      setBusy(false);
    }
  }

  async function loadDemo() {
    setBusy(true);
    const { d1, d2 } = demoSnapshots();
    try {
      append("载入第 1 天快照 …");
      await api.post("/v1/ingest/snapshots", { snapshots: d1 });
      append("设置 t3 我方价格 = 100 …");
      await api.patch("/api/targets/t3", { my_price: 100, my_sku: "SKU-C" });
      append("载入第 2 天快照 …");
      const report = await api.post<ImportReport>("/v1/ingest/snapshots", {
        snapshots: d2,
      });
      append(JSON.stringify(report, null, 2));
      append("完成。到「事件」查看变化。");
    } catch (err) {
      append(`失败：${err instanceof Error ? err.message : "未知错误"}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHead
        title="数据导入"
        sub="只收原始观测；空单元格表示未知，不会当作 0"
      />

      <div className="detail-grid">
        <Card title="CSV 上传" sub="列：target_id, ts, collector, source_tier, list_price, coupons, promotions, coin_rate, coin_cap, member_price, live_price, account_tier, title">
          <input
            type="file"
            accept=".csv"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
          <div className="actions">
            <button className="btn" disabled={busy} onClick={() => void upload()}>
              上传
            </button>
            <button className="btn ghost" disabled={busy} onClick={() => void loadDemo()}>
              载入演示数据
            </button>
          </div>
        </Card>

        <Card title="文件收件箱" sub="data/inbox">
          <p className="hint">
            把影刀导出的 CSV/JSON 放进 <code>data/inbox/</code>，后台每 15 秒扫描一次，
            按内容哈希判重。失败文件会移到 <code>failed/</code>。
          </p>
        </Card>
      </div>

      <Card title="导入日志">
        <pre className="log">{log.join("\n") || "等待导入…"}</pre>
      </Card>
    </>
  );
}
