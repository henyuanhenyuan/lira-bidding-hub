import { useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import { Card, Empty, ErrorBox, Loader, PageHead } from "../components/ui";
import { formatTs } from "../format";
import { useAsync } from "../hooks";
import type { Doc } from "../types";

const EMPTY_FORM = {
  title: "",
  source: "",
  category: "",
  version: "",
  content: "",
};

export default function Docs() {
  const { me } = useAuth();
  const canEdit = me?.role === "admin" || me?.role === "manager";
  const { data, error, loading, reload } = useAsync(
    () => api.get<Doc[]>("/api/docs"),
    [],
  );

  const [form, setForm] = useState(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, Doc>>({});

  async function create() {
    setBusy(true);
    setMessage("");
    try {
      const doc = await api.post<Doc>("/api/docs", {
        title: form.title.trim(),
        content: form.content,
        source: form.source.trim() || null,
        category: form.category.trim() || null,
        version: form.version.trim() || null,
      });
      setDetails((prev) => ({ ...prev, [doc.id]: doc }));
      setForm(EMPTY_FORM);
      setMessage(`已入库：${doc.title}，切分为 ${doc.chunk_count} 片`);
      await reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "入库失败");
    } finally {
      setBusy(false);
    }
  }

  async function toggle(doc: Doc) {
    setMessage("");
    if (openId === doc.id) {
      setOpenId(null);
      return;
    }
    setOpenId(doc.id);
    if (!details[doc.id]) {
      try {
        const detail = await api.get<Doc>(`/api/docs/${doc.id}`);
        setDetails((prev) => ({ ...prev, [doc.id]: detail }));
      } catch (err) {
        setMessage(err instanceof Error ? err.message : "加载切片失败");
      }
    }
  }

  return (
    <>
      <PageHead
        title="规则库"
        sub="平台规则、活动玩法与内部策略；检索后以 doc:<id> 进入证据链"
      />

      {canEdit && (
        <Card title="新增文档" sub="按段落切片后向量化；正文越结构化，检索越准">
          <div className="form-grid">
            <label>
              标题
              <input
                className="input"
                value={form.title}
                onChange={(event) => setForm({ ...form, title: event.target.value })}
                placeholder="例如：大促价保规则"
              />
            </label>
            <label>
              来源
              <input
                className="input"
                value={form.source}
                onChange={(event) => setForm({ ...form, source: event.target.value })}
                placeholder="平台 / 内部"
              />
            </label>
            <label>
              分类
              <input
                className="input"
                value={form.category}
                onChange={(event) => setForm({ ...form, category: event.target.value })}
                placeholder="活动 / 合规"
              />
            </label>
            <label>
              版本
              <input
                className="input"
                value={form.version}
                onChange={(event) => setForm({ ...form, version: event.target.value })}
                placeholder="2026-10"
              />
            </label>
          </div>
          <label className="block-label">
            正文
            <textarea
              className="textarea"
              rows={7}
              value={form.content}
              onChange={(event) => setForm({ ...form, content: event.target.value })}
              placeholder="粘贴规则原文；标题与段落用空行分隔。"
            />
          </label>
          <div className="actions">
            <button
              className="btn"
              disabled={busy || !form.title.trim() || !form.content.trim()}
              onClick={() => void create()}
            >
              {busy ? "入库中…" : "入库"}
            </button>
            {message && <span className="hint">{message}</span>}
          </div>
        </Card>
      )}

      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !data && <Loader />}
      {data && data.length === 0 && (
        <Empty>规则库还是空的。把平台活动规则或内部定价策略粘进来。</Empty>
      )}

      <div className="doc-grid">
        {data?.map((doc) => (
          <article className="card doc-card" key={doc.id}>
            <div className="doc-head">
              <h3>{doc.title}</h3>
              <span className="badge gate-confirm">{doc.chunk_count} 片</span>
            </div>
            <div className="doc-meta">
              {doc.category && <span>{doc.category}</span>}
              {doc.source && <span>{doc.source}</span>}
              {doc.version && <span>v{doc.version}</span>}
              <span>{formatTs(doc.created_at)}</span>
            </div>
            <button className="btn ghost small" onClick={() => void toggle(doc)}>
              {openId === doc.id ? "收起切片" : "查看切片"}
            </button>
            {openId === doc.id && (
              <div className="chunk-list">
                {(details[doc.id]?.chunks ?? []).map((chunk) => (
                  <div className="chunk" key={chunk.id}>
                    <span className="hint">
                      切片 #{chunk.chunk_no + 1} · <code>doc:{chunk.id}</code>
                    </span>
                    <pre className="chunk-text">{chunk.content}</pre>
                  </div>
                ))}
              </div>
            )}
          </article>
        ))}
      </div>
    </>
  );
}
