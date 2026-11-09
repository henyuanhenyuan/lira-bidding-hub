import { useState } from "react";

import { api, qs } from "../core/api";
import { useAsync } from "../core/hooks";
import { Cabinet, ItemShelf } from "../ui/viz";
import { Badge, Card, Empty, ErrorBox, Field, Page, Spinner, Table } from "../ui/kit";

interface DocItem {
  id: string;
  title: string;
  category?: string | null;
  created_at: string;
  chunk_count: number;
}

interface Hit {
  id: string;
  doc_title?: string;
  chunk_no: number;
  content: string;
  score: number;
}

interface CaseItem {
  id: string;
  category: string;
  event_type: string;
  price_band: string;
  summary: string;
  attribution: string;
  decision?: string | null;
  outcome_7d?: string | null;
  ts: string;
}

export default function Knowledge() {
  const { data, error, loading, reload } = useAsync(() => api.get<DocItem[]>("/api/docs"), []);
  const casesQ = useAsync(() => api.get<CaseItem[]>("/api/cases?limit=40"), []);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [caseQuery, setCaseQuery] = useState("");
  const [caseHits, setCaseHits] = useState<CaseItem[] | null>(null);

  async function search() {
    if (!query.trim()) return;
    setBusy(true);
    setMessage("");
    const started = Date.now();
    try {
      const result = await api.get<Hit[]>("/api/docs/search" + qs({ query, limit: 5 }));
      setHits(result);
      setMessage(`召回 ${result.length} 条 · ${Date.now() - started}ms`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "检索失败");
    } finally {
      setBusy(false);
    }
  }

  async function create() {
    if (!title.trim() || !content.trim()) {
      setMessage("标题和内容不能为空");
      return;
    }
    setBusy(true);
    try {
      await api.post("/api/docs", { title, content, category: "policy" });
      setTitle("");
      setContent("");
      setMessage("已写入并完成切片索引");
      await reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "写入失败");
    } finally {
      setBusy(false);
    }
  }

  async function seedCases() {
    setBusy(true);
    setMessage("");
    try {
      const result = await api.post<{ added: number; total: number }>("/api/cases/seed");
      setMessage(`新增 ${result.added} 条案例，共 ${result.total} 条`);
      await casesQ.reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "写入失败");
    } finally {
      setBusy(false);
    }
  }

  async function searchCases() {
    if (!caseQuery.trim()) return;
    setBusy(true);
    try {
      setCaseHits(
        await api.get<CaseItem[]>(`/api/cases/search${qs({ q: caseQuery, limit: 5 })}`),
      );
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "案例检索失败");
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  const docs = data;

  return (
    <Page title="知识库" desc="规则文档构成的知识星图；命中分数来自真实检索链路">
      {message && <div className="notice">{message}</div>}

      <div className="split">
        <Card title="知识货架" sub="每份文档是一件商品，高度是切片数量">
          <Cabinet title="知识商品" tag={`${docs.length} 件`}>
          <ItemShelf
            items={docs.map((doc) => ({
              id: doc.id,
              title: doc.title,
              value: doc.chunk_count,
              label: `${doc.chunk_count} 片`,
              tone:
                doc.category === "policy"
                  ? "#22d3ee"
                  : doc.category === "ops"
                    ? "#a78bfa"
                    : "#34d399",
            }))}
          />
          </Cabinet>
        </Card>

        <Card title="检索" sub="向量 + 关键词 + RRF + 二跳">
          <div className="row" style={{ marginBottom: 12 }}>
            <input
              className="input"
              style={{ flex: 1 }}
              placeholder="例如：价格带击穿怎么判定？"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && void search()}
            />
            <button className="btn" disabled={busy} onClick={() => void search()}>
              {busy ? "检索中…" : "检索"}
            </button>
          </div>

          {hits === null ? (
            <Empty>输入问题，看看会点亮哪些规则。</Empty>
          ) : hits.length === 0 ? (
            <Empty>没有召回到切片。</Empty>
          ) : (
            <div className="hit-list">
              {hits.map((hit, index) => (
                <div className={`hit rank-${index}`} key={hit.id}>
                  <div className="hit-head">
                    <span className="hit-rank">{index + 1}</span>
                    <b>{hit.doc_title}</b>
                    <Badge tone="accent">score {hit.score}</Badge>
                  </div>
                  <p>{hit.content}</p>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="split">
        <Card title="新增文档" sub="写入后立即可被检索与引用">
          <Field label="标题">
            <input className="input" value={title} onChange={(event) => setTitle(event.target.value)} />
          </Field>
          <Field label="正文">
            <textarea
              className="input"
              value={content}
              onChange={(event) => setContent(event.target.value)}
              placeholder="例如：价格带击穿的判定标准是……"
            />
          </Field>
          <button className="btn" disabled={busy} onClick={() => void create()}>
            写入知识库
          </button>
        </Card>

        <Card title="文档" sub={`${docs.length} 篇`} flush>
          {docs.length === 0 ? (
            <Empty>还没有文档。</Empty>
          ) : (
            <Table head={["标题", "分类", "切片"]}>
              {docs.map((doc) => (
                <tr key={doc.id}>
                  <td>
                    <b>{doc.title}</b>
                    <div className="sub">{doc.created_at.slice(0, 16).replace("T", " ")}</div>
                  </td>
                  <td>{doc.category ?? "—"}</td>
                  <td className="num">{doc.chunk_count}</td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      </div>

      <div className="split">
        <Card
          title="案例库"
          sub={`${casesQ.data?.length ?? 0} 条处置沉淀`}
          extra={
            <button className="btn ghost sm" disabled={busy} onClick={() => void seedCases()}>
              示例案例
            </button>
          }
        >
          {!casesQ.data || casesQ.data.length === 0 ? (
            <Empty>还没有案例，生成示例或记录一次回收结果。</Empty>
          ) : (
            <Table head={["类型", "价格带", "摘要", "决策"]}>
              {casesQ.data.slice(0, 10).map((item) => (
                <tr key={item.id}>
                  <td>
                    <Badge tone="neutral">{item.event_type}</Badge>
                    <div className="sub">{item.category}</div>
                  </td>
                  <td className="mono">{item.price_band}</td>
                  <td>{item.summary}</td>
                  <td>{item.decision ?? "—"}</td>
                </tr>
              ))}
            </Table>
          )}
        </Card>

        <Card title="案例检索" sub="按场景找相似处置">
          <div className="row" style={{ marginBottom: 10 }}>
            <input
              className="input"
              style={{ flex: 1 }}
              placeholder="例如：竞品大促前降价"
              value={caseQuery}
              onChange={(event) => setCaseQuery(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && void searchCases()}
            />
            <button className="btn" disabled={busy} onClick={() => void searchCases()}>
              检索
            </button>
          </div>
          {caseHits === null ? (
            <Empty>输入场景描述，找历史处置。</Empty>
          ) : caseHits.length === 0 ? (
            <Empty>没有相似案例。</Empty>
          ) : (
            <div className="hit-list">
              {caseHits.map((item, index) => (
                <div className={`hit rank-${index}`} key={item.id}>
                  <div className="hit-head">
                    <span className="hit-rank">{index + 1}</span>
                    <b>{item.summary}</b>
                    <Badge tone="accent">{item.price_band}</Badge>
                  </div>
                  <p>
                    {item.attribution}
                    {item.outcome_7d ? ` · ${item.outcome_7d}` : ""}
                  </p>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </Page>
  );
}
