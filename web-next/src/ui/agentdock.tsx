import { useState } from "react";
import { createPortal } from "react-dom";

import { api } from "../core/api";
import type { ChatReply } from "../core/types";

type Turn = { q: string; a: ChatReply | null; error?: string };

export default function QAWidget({ context }: { context?: string }) {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);

  async function ask() {
    const text = question.trim();
    if (text.length < 2 || busy) return;
    setQuestion("");
    setBusy(true);
    const index = turns.length;
    setTurns((rows) => [...rows, { q: text, a: null }]);
    try {
      const prompt = context ? `当前上下文：${context}\n问题：${text}` : text;
      const reply = await api.post<ChatReply>("/api/agent/chat", { question: prompt });
      setTurns((rows) => rows.map((row, i) => (i === index ? { ...row, a: reply } : row)));
    } catch (err) {
      setTurns((rows) =>
        rows.map((row, i) => (i === index ? { ...row, error: err instanceof Error ? err.message : "失败" } : row)),
      );
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return createPortal(
      <button className="btn primary qa-dock" style={{ width: "auto" }} onClick={() => setOpen(true)}>
        辅助问答
      </button>,
      document.body,
    );
  }

  return createPortal(
    <div className="glass qa-dock pad">
      <div className="qa-head" onClick={() => setOpen(false)}>
        <div className="row gap-8">
          <span className="badge cyan"><i className="dot" /> 辅助问答</span>
          <span className="muted" style={{ fontSize: 10.5 }}>核心分析已在视图内完成</span>
        </div>
        <span className="muted" style={{ fontSize: 16 }}>×</span>
      </div>

      <div className="qa-body stack gap-8 mt-12">
        {turns.length === 0 && (
          <div className="muted" style={{ fontSize: 12 }}>
            补充追问某个价格、事件或口径即可，例如「价格带击穿的判定标准是什么？」。
          </div>
        )}
        {turns.map((turn, i) => (
          <div className="stack gap-6" key={i}>
            <div className="qa-bubble me" style={{ alignSelf: "flex-end" }}>{turn.q}</div>
            {turn.error ? (
              <div className="qa-bubble" style={{ borderColor: "rgba(255,122,156,.4)" }}>出错：{turn.error}</div>
            ) : turn.a ? (
              <div className="stack gap-6">
                <div className="qa-bubble">{turn.a.answer}</div>
                {turn.a.citations.slice(0, 2).map((cite) => (
                  <div className="muted" key={cite.id} style={{ fontSize: 11.5 }}>
                    · {cite.title ?? cite.id}
                  </div>
                ))}
              </div>
            ) : (
              <div className="qa-bubble muted">分析中…</div>
            )}
          </div>
        ))}
      </div>

      <div className="row gap-8 mt-12">
        <input
          className="input"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="追问一句…"
          onKeyDown={(event) => event.key === "Enter" && void ask()}
        />
        <button className="btn primary sm" onClick={() => void ask()} disabled={busy}>
          {busy ? "…" : "发送"}
        </button>
      </div>
    </div>,
    document.body,
  );
}
