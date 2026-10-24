import { useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import { Card, Empty, ErrorBox, Loader, PageHead } from "../components/ui";
import { formatTs } from "../format";
import { useAsync } from "../hooks";
import type { Skill } from "../types";

const ALL_TOOLS = [
  "collection_health",
  "price_history",
  "search_cases",
  "search_docs",
  "my_product",
  "simulate_price",
  "get_event",
];

const EVENT_TYPES = [
  "price_drop",
  "price_rise",
  "band_breach",
  "title_change",
  "image_change",
  "review_spike",
];

const EMPTY_FORM = {
  name: "",
  description: "",
  eventTypes: ["price_drop"],
  minSeverity: "L1",
  playbook: "",
  tools: [...ALL_TOOLS],
};

export default function Skills() {
  const { me } = useAuth();
  const canEdit = me?.role === "admin" || me?.role === "manager";
  const { data, error, loading, reload } = useAsync(
    () => api.get<Skill[]>("/api/skills"),
    [],
  );

  const [form, setForm] = useState(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function toggle(skill: Skill) {
    setMessage("");
    try {
      await api.patch(`/api/skills/${skill.id}`, { enabled: !skill.enabled });
      await reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "更新失败");
    }
  }

  async function create() {
    setBusy(true);
    setMessage("");
    try {
      await api.post("/api/skills", {
        name: form.name.trim(),
        description: form.description.trim() || null,
        event_types: form.eventTypes,
        min_severity: form.minSeverity,
        playbook: form.playbook,
        allowed_tools: form.tools,
      });
      setForm(EMPTY_FORM);
      setMessage("剧本已创建");
      await reload();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "创建失败");
    } finally {
      setBusy(false);
    }
  }

  function toggleItem(list: string[], value: string): string[] {
    return list.includes(value)
      ? list.filter((item) => item !== value)
      : [...list, value];
  }

  return (
    <>
      <PageHead
        title="Skill 管理"
        sub="每个剧本决定触发条件、可用工具与分析口径；停用后自动回退通用研判"
      />

      {message && <div className="notice">{message}</div>}

      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !data && <Loader />}
      {data && data.length === 0 && <Empty>还没有剧本。</Empty>}

      <div className="skill-grid">
        {data?.map((skill) => (
          <article className="card skill-card" key={skill.id}>
            <div className="skill-head">
              <h3>{skill.name}</h3>
              <span className={`badge ${skill.enabled ? "run-succeeded" : "status-cancelled"}`}>
                {skill.enabled ? "启用" : "停用"}
              </span>
              <span className="hint">v{skill.version}</span>
            </div>
            {skill.description && <p className="hint">{skill.description}</p>}
            <div className="tag-row">
              {skill.event_types.map((type) => (
                <span className="tag" key={type}>
                  {type}
                </span>
              ))}
              <span className="tag">≥ {skill.min_severity}</span>
            </div>
            <p className="skill-playbook">{skill.playbook}</p>
            <div className="tag-row">
              {skill.allowed_tools.map((tool) => (
                <code className="evidence" key={tool}>
                  {tool}
                </code>
              ))}
            </div>
            <div className="skill-foot">
              <span className="hint">更新于 {formatTs(skill.updated_at)}</span>
              {canEdit && (
                <button className="btn ghost small" onClick={() => void toggle(skill)}>
                  {skill.enabled ? "停用" : "启用"}
                </button>
              )}
            </div>
          </article>
        ))}
      </div>

      {canEdit && (
        <Card title="新建剧本" sub="allowed_tools 决定这次研判能调用哪些工具">
          <div className="form-grid">
            <label>
              名称
              <input
                className="input"
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
            </label>
            <label>
              描述
              <input
                className="input"
                value={form.description}
                onChange={(event) =>
                  setForm({ ...form, description: event.target.value })
                }
              />
            </label>
            <label>
              最低级别
              <select
                className="select"
                value={form.minSeverity}
                onChange={(event) =>
                  setForm({ ...form, minSeverity: event.target.value })
                }
              >
                {["L1", "L2", "L3"].map((level) => (
                  <option key={level} value={level}>
                    {level}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <span className="hint">触发事件</span>
          <div className="chips" style={{ margin: "6px 0 12px" }}>
            {EVENT_TYPES.map((type) => (
              <button
                key={type}
                className={`chip${form.eventTypes.includes(type) ? " active" : ""}`}
                onClick={() =>
                  setForm({ ...form, eventTypes: toggleItem(form.eventTypes, type) })
                }
              >
                {type}
              </button>
            ))}
          </div>

          <span className="hint">允许工具</span>
          <div className="chips" style={{ margin: "6px 0 12px" }}>
            {ALL_TOOLS.map((tool) => (
              <button
                key={tool}
                className={`chip${form.tools.includes(tool) ? " active" : ""}`}
                onClick={() => setForm({ ...form, tools: toggleItem(form.tools, tool) })}
              >
                {tool}
              </button>
            ))}
          </div>

          <label className="block-label">
            分析剧本
            <textarea
              className="textarea"
              rows={5}
              value={form.playbook}
              onChange={(event) => setForm({ ...form, playbook: event.target.value })}
              placeholder="写清判断顺序、优先动作和禁止事项。"
            />
          </label>
          <button
            className="btn"
            disabled={busy || !form.name.trim() || !form.playbook.trim()}
            onClick={() => void create()}
          >
            {busy ? "创建中…" : "创建剧本"}
          </button>
        </Card>
      )}
    </>
  );
}
