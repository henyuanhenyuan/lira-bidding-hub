import { useState } from "react";

import { api } from "../api";
import { Card, Empty, ErrorBox, Loader, PageHead } from "../components/ui";
import { useAsync } from "../hooks";
import type { AskResult, AskTemplate } from "../types";

export default function Ask() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: templates, error: templateError, loading } = useAsync(
    () => api.get<AskTemplate[]>("/api/ask/templates"),
    [],
  );

  async function submit(text?: string) {
    const value = (text ?? question).trim();
    if (!value) return;
    setQuestion(value);
    setBusy(true);
    setError(null);
    try {
      setResult(await api.post<AskResult>("/api/ask", { question: value }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "查询失败");
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  const columns = result?.rows?.length ? Object.keys(result.rows[0]) : [];

  return (
    <>
      <PageHead
        title="问数"
        sub="固定模板 + 参数绑定，不拼 SQL；界面会标明用了哪个模板"
      />

      <Card>
        <form
          className="ask-row"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <input
            className="input"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="例如：最近 7 天有哪些降价？"
          />
          <button className="btn" type="submit" disabled={busy}>
            {busy ? "查询中…" : "提问"}
          </button>
        </form>

        {loading && <Loader label="载入模板…" />}
        {templateError && <ErrorBox message={templateError} />}
        <div className="chips">
          {templates
            ?.flatMap((template) => template.examples ?? [])
            .slice(0, 8)
            .map((example) => (
              <button
                className="chip"
                key={example}
                onClick={() => void submit(example)}
              >
                {example}
              </button>
            ))}
        </div>
      </Card>

      {error && <ErrorBox message={error} />}

      {result && (
        <Card
          title="回答"
          sub={
            result.ok
              ? `${result.template_title || result.template || "模板"} · ${result.rows?.length ?? 0} 行`
              : "没有匹配到模板"
          }
        >
          <p className="narrative">{result.answer}</p>
          {result.params && (
            <p className="hint">参数：{JSON.stringify(result.params)}</p>
          )}
          {result.suggestions && result.suggestions.length > 0 && (
            <div className="chips">
              {result.suggestions.map((item) => (
                <button className="chip" key={item} onClick={() => void submit(item)}>
                  {item}
                </button>
              ))}
            </div>
          )}
          {result.ok && columns.length > 0 && (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    {columns.map((column) => (
                      <th key={column}>{column}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows?.map((row, index) => (
                    <tr key={index}>
                      {columns.map((column) => (
                        <td key={column}>{String(row[column] ?? "—")}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {result.ok && !columns.length && <Empty>没有符合条件的记录。</Empty>}
        </Card>
      )}
    </>
  );
}
