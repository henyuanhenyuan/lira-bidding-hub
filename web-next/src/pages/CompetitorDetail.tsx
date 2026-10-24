import { Link, useParams } from "react-router-dom";

import { api } from "../api";
import PriceChart from "../components/PriceChart";
import {
  Card,
  Empty,
  ErrorBox,
  KV,
  Loader,
  PageHead,
  SeverityBadge,
} from "../components/ui";
import { formatTs, money, percent } from "../format";
import { useAsync, useStreamEvent } from "../hooks";
import { TYPE_TEXT } from "../labels";
import type {
  EventItem,
  Insight,
  Mapping,
  PricePoint,
  Review,
  Target,
} from "../types";

export default function CompetitorDetail() {
  const { id } = useParams<{ id: string }>();

  const { data, error, loading, reload } = useAsync(async () => {
    const [target, prices, events, reviews] = await Promise.all([
      api.get<Target>(`/api/targets/${id}`),
      api.get<PricePoint[]>(`/api/targets/${encodeURIComponent(id!)}/prices`),
      api.get<EventItem[]>(`/api/events?target_id=${encodeURIComponent(id!)}&limit=50`),
      api.get<Review[]>(`/api/reviews?target_id=${encodeURIComponent(id!)}&limit=20`),
    ]);
    const insight = await api
      .get<Insight>(`/api/targets/${encodeURIComponent(id!)}/insights`)
      .catch(() => null);
    const mappings = await api
      .get<Mapping[]>("/api/mappings")
      .then((rows) => rows.filter((row) => row.target_id === id));
    return { target, prices, events, reviews, insight, mappings };
  }, [id]);

  useStreamEvent(["event", "ingest"], () => void reload());

  if (loading && !data) return <Loader label="载入竞品档案…" />;
  if (error && !data) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;

  const { target, prices, events, reviews, insight, mappings } = data;
  const latest = prices[0];

  async function analyzeInsight() {
    await api.post(`/api/targets/${encodeURIComponent(id!)}/insights`);
    await reload();
  }

  return (
    <>
      <PageHead
        title={target.title}
        sub={`${target.platform} · ${target.id} · ${events.length} 条事件 · ${reviews.length} 条评论`}
        actions={
          <Link className="btn ghost" to="/competitors">
            返回竞品列表
          </Link>
        }
      />

      <div className="detail-grid">
        <Card title="价格档案" sub="竞品到手价区间与我方价格">
          <PriceChart points={prices} myPrice={target.my_price} />
          <KV
            rows={[
              ["我方 SKU", target.my_sku || "未设置"],
              ["我方价", money(target.my_price)],
              ["最新置信", latest ? percent(latest.confidence) : "—"],
              [
                "缺失字段",
                latest?.missing_fields?.length ? latest.missing_fields.join("、") : "完整",
              ],
              [
                "SKU 对齐",
                mappings.length
                  ? mappings
                      .map((row) => `${row.my_sku}（${(row.score * 100).toFixed(0)} 分，${row.status}）`)
                      .join("；")
                  : "未对齐",
              ],
            ]}
          />
        </Card>

        <Card
          title="评论洞察"
          sub={insight ? `${insight.review_count} 条评论 · 窗口 ${insight.window_days} 天` : "尚无洞察"}
          actions={
            <button className="btn ghost small" onClick={() => void analyzeInsight()}>
              {insight ? "重新生成" : "生成洞察"}
            </button>
          }
        >
          {insight ? (
            <>
              <p className="narrative">{insight.summary}</p>
              <div className="topic-list">
                {insight.topics.map((topic) => (
                  <div className="topic-row" key={topic.name}>
                    <span>{topic.name}</span>
                    <span className="bar">
                      <span style={{ width: `${Math.max(4, topic.share * 100)}%` }} />
                    </span>
                    <span className="hint">
                      {topic.count} 条 · 负面 {percent(topic.negative_share)}
                    </span>
                  </div>
                ))}
              </div>
              {insight.opportunities.map((text) => (
                <p className="opportunity" key={text}>
                  {text}
                </p>
              ))}
            </>
          ) : (
            <Empty>还没有评论洞察。先导入评论，再生成。</Empty>
          )}
        </Card>
      </div>

      <Card title="事件时间线" sub="按时间倒序">
        {events.length === 0 ? (
          <Empty>没有事件</Empty>
        ) : (
          <ul className="feed">
            {events.map((event) => (
              <li key={event.id}>
                <Link to={`/events/${event.id}`} className="feed-item">
                  <SeverityBadge value={event.severity} />
                  <span className="feed-main">
                    <b>{TYPE_TEXT[event.type] ?? event.type}</b>
                    <span>{event.note || "—"}</span>
                  </span>
                  <span className="feed-time">{formatTs(event.ts)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="近期评论" sub="最多 20 条">
        {reviews.length === 0 ? (
          <Empty>暂无评论</Empty>
        ) : (
          <ul className="review-list">
            {reviews.map((review) => (
              <li key={review.id}>
                <span className="rating">{review.rating ?? "—"}★</span>
                <span>{review.content}</span>
                <span className="hint">{formatTs(review.ts)}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
