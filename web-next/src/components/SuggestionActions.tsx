import { useState } from "react";

import { api } from "../api";
import { canApprove, useAuth } from "../auth";
import { STATUS_TEXT } from "../labels";
import { money, percent } from "../format";
import type { ExecutionPreview, Suggestion } from "../types";
import { GuardrailBadge } from "./ui";

const MODE_TEXT: Record<string, string> = {
  off: "仅记录，不调用外部系统",
  preview: "预演，不写外部系统",
  webhook: "外部执行（Webhook）",
};

export default function SuggestionActions({
  suggestion,
  onChange,
}: {
  suggestion: Suggestion;
  onChange: () => void | Promise<void>;
}) {
  const { me } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ExecutionPreview | null>(null);
  const [price, setPrice] = useState(suggestion.target_price?.toString() ?? "");

  async function act(kind: string, body?: unknown) {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/api/suggestions/${suggestion.id}/${kind}`, body);
      setPreview(null);
      await onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  async function openPreview() {
    setBusy(true);
    setError(null);
    try {
      const data = await api.get<ExecutionPreview>(
        `/api/suggestions/${suggestion.id}/execution-preview`,
      );
      setPreview(data);
      setPrice(String(data.plan.to_price));
    } catch (err) {
      setError(err instanceof Error ? err.message : "预览失败");
    } finally {
      setBusy(false);
    }
  }

  const status = suggestion.status;
  const approver = canApprove(me?.role);
  const blocked = preview?.plan.guardrail === "blocked" && !approver;

  return (
    <div className="actions">
      {status === "pending" && (
        <>
          <button className="btn" disabled={busy} onClick={() => void act("submit")}>
            提交执行
          </button>
          <button className="btn ghost" disabled={busy} onClick={() => void act("reject")}>
            不采纳
          </button>
        </>
      )}

      {status === "submitted" &&
        (approver ? (
          <>
            <button className="btn" disabled={busy} onClick={() => void act("approve")}>
              批准
            </button>
            <button className="btn ghost" disabled={busy} onClick={() => void act("reject")}>
              驳回
            </button>
          </>
        ) : (
          <span className="hint">等待审批 · 当前账号无审批权限</span>
        ))}

      {status === "approved" && (
        <>
          <button className="btn" disabled={busy} onClick={() => void openPreview()}>
            执行
          </button>
          <button className="btn ghost" disabled={busy} onClick={() => void act("cancel")}>
            取消
          </button>
        </>
      )}

      {preview && status === "approved" && (
        <div className="exec-preview">
          <div className="exec-head">
            <b>执行预览</b>
            <GuardrailBadge value={preview.plan.guardrail} />
            <span className="hint">{MODE_TEXT[preview.plan.mode] ?? preview.plan.mode}</span>
          </div>
          <div className="exec-grid">
            <span>SKU</span>
            <b>{preview.plan.sku || "未设置"}</b>
            <span>价格</span>
            <b>
              {money(preview.plan.from_price)} → {money(preview.plan.to_price)}
            </b>
            <span>毛利率</span>
            <b>
              {percent(preview.plan.margin_at_target, 1)} / 下限{" "}
              {percent(preview.plan.margin_floor)}
            </b>
          </div>
          <p className="hint">{preview.plan.guardrail_note}</p>
          {!preview.configured && (
            <p className="error-text">
              外部执行地址未配置：本次只会记录执行，不会真正改价。
            </p>
          )}
          {blocked && (
            <p className="error-text">毛利护栏拦截，需要管理员操作。</p>
          )}
          <div className="inline-form">
            <label>
              实际执行价
              <input
                inputMode="decimal"
                value={price}
                onChange={(event) => setPrice(event.target.value)}
              />
            </label>
            <button
              className="btn"
              disabled={busy || blocked || price.trim() === ""}
              onClick={() =>
                void act("execute", { executed_price: Number(price) })
              }
            >
              确认执行
            </button>
            <button className="btn ghost" onClick={() => setPreview(null)}>
              返回
            </button>
          </div>
        </div>
      )}

      {["executed", "accepted", "rejected", "cancelled", "holdout"].includes(status) && (
        <span className="hint">
          状态：{STATUS_TEXT[status]}
          {suggestion.executed_price ? ` · 执行价 ¥${suggestion.executed_price}` : ""}
        </span>
      )}

      {error && <span className="error-text">{error}</span>}
    </div>
  );
}
