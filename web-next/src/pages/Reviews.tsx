import { useState } from "react";

import { api, query } from "../api";
import { useAuth } from "../auth";
import { Card, Empty, ErrorBox, Loader, PageHead } from "../components/ui";
import { useAsync } from "../hooks";
import type { Insight, Review, Target } from "../types";

export default function Reviews() {
  const { me } = useAuth();
  const canEdit = me?.role === "admin" || me?.role === "manager";
  const { data: targets, error, loading } = useAsync(
    () => api.get<Target[]>("/api/targets"),
    [],
  );
  const [targetId, setTargetId] = useState("");
  const [reviews, setReviews] = useState<Review[]>([]);
  const [insight, setInsight] = useState<Insight | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const activeId = targetId || targets?.[0]?.id || "";

  async function load(tid: string) {
    if (!tid) return;
    setTargetId(tid);
    setMessage("");
    try {
      const list = await api.get<Review[]>(
        "/api/reviews" + query({ target_id: tid, limit: 100 }),
      );
      setReviews(list);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "评论加载失败");
    }
    try {
      setInsight(await api.get<Insight>(`/api/targets/${tid}/insights`));
    } catch {
      setInsight(null);
    }
  }

  async function seed() {
    if (!activeId) return;
    setBusy(true);
    try {
      const result = await api.post<{ inserted: number; duplicates: number }>(
        "/api/reviews/seed" + query({ target_id: activeId }),
      );
      setMessage(`新增 ${result.inserted} 条，重复 ${result.duplicates} 条`);
      await load(activeId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "载入失败");
    } finally {
      setBusy(false);
    }
  }

  async function generate() {
    if (!activeId) return;
    setBusy(true);
    try {
      setInsight(await api.post<Insight>(`/api/targets/${activeId}/insights`));
      setMessage("洞察已生成");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "生成失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHead
        title="评论洞察"
        sub="竞品评论的话题分布、负面占比与可行动机会"
        actions={
          <div className="row">
            <select
              className="input"
              value={activeId}
              onChange={(event) => void load(event.target.value)}
            >
              {(targets ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
            </select>
            {canEdit && (
              <>
                <button className="btn ghost" disabled={busy} onClick={() => void seed()}>
                  载入示例评论
                </button>
                <button className="btn" disabled={busy} onClick={() => void generate()}>
                  生成洞察
                </button>
              </>
            )}
          </div>
        }
      />

      {message && <div className="notice">{message}</div>}
      {error && <ErrorBox message={error} />}
      {loading && !targets && <Loader />}

      <Card title="洞察" sub="话题份额与负面占比，来源可为模板或模型">
        {!insight && <Empty>尚无洞察，选择竞品后点「生成洞察」。</Empty>}
        {insight && (
          <>
            <p>{insight.summary}</p>
            {(insight.topics ?? []).map((topic) => (
              <div className="row" key={topic.name}>
                <span style={{ minWidth: 96 }}>{topic.name}</span>
                <progress
                  max={100}
                  value={Math.round(topic.share * 100)}
                  style={{ flex: 1 }}
                />
                <span className="num">
                  {topic.count} 条 · 负面 {(topic.negative_share * 100).toFixed(0)}%
                </span>
              </div>
            ))}
            {(insight.opportunities ?? []).map((item) => (
              <p className="hint" key={item}>
                · {item}
              </p>
            ))}
            <p className="hint">
              来源 {insight.generated_by} · {insight.review_count} 条评论 · 窗口{" "}
              {insight.window_days} 天
            </p>
          </>
        )}
      </Card>

      <Card title="评论" sub={`${reviews.length} 条`}>
        {reviews.length === 0 ? (
          <Empty>暂无评论。</Empty>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>评分</th>
                  <th>内容</th>
                </tr>
              </thead>
              <tbody>
                {reviews.map((item) => (
                  <tr key={item.id}>
                    <td className="num">{item.rating ?? "—"}</td>
                    <td>{item.content}</td>
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
