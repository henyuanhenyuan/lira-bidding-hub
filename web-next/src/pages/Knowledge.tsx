import { useState } from "react";

import { api, qs } from "../core/api";
import { ts } from "../core/format";
import { useAsync } from "../core/hooks";
import type { DocChunkHit, DocItem } from "../core/types";
import { Badge, Card, Empty, ErrorBox, Field, Page, Spinner, Table } from "../ui/kit";

export default function Knowledge() {
  const { data, error, loading, reload } = useAsync(() => api.get<DocItem[]>("/api/docs"), []);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<DocChunkHit[] | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function search() {
    if (!query.trim()) return;
    setBusy(true);
    setMessage("");
    try {
      setHits(await api.get<DocChunkHit[]>("/api/docs/search" + qs({ query, limit: 5 })));
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
      setMessage("已写入知识库并完成切片索引");
      await reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "写入失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page title="知识库" desc="规则与策略文档经父子块切分后进入向量库，供 Agent 检索引用">
      {message && <div className="notice">{message}</div>}
      {error && <ErrorBox message={error} />}

      <div className="split">
        <Card title="检索验证" sub="向量 + 关键词 + RRF 融合，分数来自真实检索链路">
          <div className="row" style={{ marginBottom: 12 }}>
            <input
              className="input"
              style={{ flex: 1 }}
              placeholder="例如：价格带击穿的判定标准是什么？"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && void search()}
            />
            <button className="btn" disabled={busy} onClick={() => void search()}>
              检索
            </button>
          </div>

          {hits === null ? (
            <Empty>输入问题，看看会召回哪些规则切片。</Empty>
          ) : hits.length === 0 ? (
            <Empty>没有召回到切片。先补充文档或换个问法。</Empty>
          ) : (
            <ul className="timeline">
              {hits.map((hit) => (
                <li key={hit.id}>
                  <b>
                    {hit.doc_title} <span className="sub">#{hit.chunk_no}</span>
                  </b>
                  <span style={{ whiteSpace: "pre-wrap" }}>{hit.content}</span>
                  <span>
                    <Badge tone="accent">score {hit.score}</Badge>{" "}
                    <span className="mono sub">{hit.id}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="新增文档" sub="写入后立即可被检索">
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
      </div>

      <Card title="文档列表" sub={`${data?.length ?? 0} 篇`} flush>
        {loading && !data ? (
          <Spinner />
        ) : (data ?? []).length === 0 ? (
          <Empty>还没有文档。</Empty>
        ) : (
          <Table head={["标题", "分类", "切片", "创建时间"]}>
            {(data ?? []).map((doc) => (
              <tr key={doc.id}>
                <td>
                  <b>{doc.title}</b>
                  <div className="sub mono">{doc.id}</div>
                </td>
                <td>{doc.category ?? "—"}</td>
                <td className="num">{doc.chunk_count}</td>
                <td className="sub">{ts(doc.created_at)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </Page>
  );
}
