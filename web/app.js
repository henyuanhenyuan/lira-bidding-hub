const state = {
  events: [],
  severity: "",
  selected: null,
  me: { auth: false, username: "local", role: "admin" },
};

const canApprove = () => ["admin", "manager"].includes(state.me.role);

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: options.body instanceof FormData ? {} : { "Content-Type": "application/json" },
    ...options,
  });
  if (res.status === 401) {
    if (!location.pathname.startsWith("/login")) location.replace("/login");
    throw new Error("未登录");
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${text}`);
  }
  return res.status === 204 ? null : res.json();
}

async function boot() {
  try {
    state.me = await api("/api/me");
  } catch (e) {
    return; // 401 已跳转登录页
  }
  renderAccount();
  connectStream();
  await Promise.all([loadHealth(), loadFreshness(), loadEvents(), loadApprovals()]);
}

function connectStream() {
  if (!("EventSource" in window)) return;
  const es = new EventSource("/api/stream");
  es.addEventListener("event", () => {
    loadEvents();
    loadHealth();
    loadFreshness();
  });
  es.addEventListener("approval", () => {
    loadApprovals();
    loadHealth();
  });
  es.addEventListener("ingest", () => {
    loadFreshness();
    loadHealth();
  });
}

async function loadFreshness() {
  const el = $("#freshness");
  if (!el) return;
  try {
    const f = await api("/api/freshness");
    if (f.latest_ts == null) {
      el.textContent = "暂无采集数据";
      el.className = "muted freshness stale";
      return;
    }
    const lag = f.lag_hours == null ? "—" : `${f.lag_hours.toFixed(1)} 小时前`;
    el.textContent = `数据截至 ${fmtTs(f.latest_ts)} · ${lag}`;
    el.className = "muted freshness" + (f.stale ? " stale" : "");
  } catch (e) {
    el.textContent = "";
  }
}

function renderAccount() {
  const chip = $("#user-chip");
  if (!chip) return;
  const name = state.me.username || state.me.actor || "local";
  const roleText = state.me.auth
    ? ({ admin: "管理员", manager: "主管", member: "运营" }[state.me.role] || state.me.role)
    : "本地模式";
  $("#user-name").textContent = name;
  $("#user-role").textContent = roleText;
  $("#user-initial").textContent = name.slice(0, 1).toUpperCase();
  chip.hidden = false;
  const opsTab = $(".tab[data-view='ops']");
  if (opsTab) opsTab.style.display = state.me.role === "admin" ? "" : "none";
}

async function logout() {
  try {
    await api("/api/logout", { method: "POST", body: "{}" });
  } catch (e) {
    // 退出失败也回到登录页
  }
  location.replace("/login");
}

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function fmtTs(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

const SEV_TEXT = { L3: "L3 紧急", L2: "L2 关注", L1: "L1 信息" };
const TYPE_TEXT = {
  price_drop: "价格下降", price_rise: "价格上升",
  band_breach: "价格带击穿", source_switch: "采集源切换",
  title_change: "标题变化", image_change: "主图更换", review_spike: "评论异动",
};
const ACTION_TEXT = {
  follow: "跟进调价", hold: "先观察", adjust_coupon: "投券对冲",
  join_promo: "报名活动", no_action: "不行动",
};

// ---------- health ----------
async function loadHealth() {
  try {
    const h = await api("/api/health");
    const el = $("#health");
    el.className = "health ok";
    el.textContent = h.llm_available ? "本地模型可用" : "模板模式（无本地模型）";
    $("#stats").innerHTML = `
      <span>目标 <b>${h.counts.targets}</b></span>
      <span>快照 <b>${h.counts.snapshots}</b></span>
      <span>事件 <b>${h.counts.events}</b></span>
      <span>建议 <b>${h.counts.suggestions}</b></span>
      <span>案例 <b>${h.counts.cases ?? 0}</b></span>`;
  } catch (e) {
    const el = $("#health");
    el.className = "health warn";
    el.textContent = "服务异常";
  }
}

// ---------- events ----------
async function loadEvents() {
  const q = state.severity ? `?severity=${state.severity}` : "";
  state.events = await api(`/api/events${q}`);
  renderEvents();
}

function renderEvents() {
  const ul = $("#event-list");
  if (!state.events.length) {
    ul.innerHTML = `<li class="event-item"><div class="note">暂无事件。到「数据导入」载入演示数据。</div></li>`;
    return;
  }
  ul.innerHTML = state.events.map((e) => `
    <li class="event-item ${state.selected === e.id ? "selected" : ""}"
        data-id="${e.id}" data-sev="${e.severity}">
      <div class="row1">
        <span class="badge ${e.severity}">${SEV_TEXT[e.severity] || e.severity}</span>
        <span class="badge gate ${e.gate_level}">${e.gate_level}</span>
        <span class="title">${esc(e.target_title || e.target_id)}</span>
      </div>
      <div class="note">${esc(TYPE_TEXT[e.type] || e.type)} · ${esc(e.note || "")}</div>
      <div class="ts">${fmtTs(e.ts)}</div>
    </li>`).join("");

  $$("#event-list .event-item").forEach((li) => {
    li.addEventListener("click", () => openEvent(li.dataset.id));
  });
}

function chart(points) {
  if (!points.length) return "";
  const w = 560, h = 160, pad = 28;
  const lows = points.map((p) => p.price_low);
  const highs = points.map((p) => p.price_high);
  const min = Math.min(...lows) * 0.97;
  const max = Math.max(...highs) * 1.03 || 1;
  const x = (i) => pad + (i * (w - pad * 2)) / Math.max(1, points.length - 1);
  const y = (v) => h - pad - ((v - min) / (max - min || 1)) * (h - pad * 2);

  const area = points.map((p, i) => `${x(i)},${y(p.price_high)}`).join(" ")
    + " " + points.slice().reverse().map((p, i) => `${x(points.length - 1 - i)},${y(p.price_low)}`).join(" ");
  const line = points.map((p, i) => `${x(i)},${y((p.price_low + p.price_high) / 2)}`).join(" ");

  return `<svg class="chart" viewBox="0 0 ${w} ${h}" width="100%" height="${h}">
    <polygon points="${area}" fill="#e8efff" stroke="none"/>
    <polyline points="${line}" fill="none" stroke="#2f6feb" stroke-width="2"/>
    ${points.map((p, i) => `<circle cx="${x(i)}" cy="${y((p.price_low + p.price_high) / 2)}" r="3" fill="#2f6feb"/>`).join("")}
    <text x="${pad}" y="${h - 6}" font-size="11" fill="#6b7280">${fmtTs(points[0].ts)}</text>
    <text x="${w - pad}" y="${h - 6}" font-size="11" fill="#6b7280" text-anchor="end">${fmtTs(points[points.length - 1].ts)}</text>
  </svg>`;
}

async function openEvent(id) {
  state.selected = id;
  renderEvents();
  const [ev, prices] = await Promise.all([
    api(`/api/events/${id}`),
    api(`/api/targets/${encodeURIComponent(state.events.find((e) => e.id === id).target_id)}/prices`),
  ]);
  renderDetail(ev, prices);
}

function renderDetail(ev, prices) {
  const s = ev.suggestion;
  const last = prices[prices.length - 1] || {};
  const missing = last.missing_fields || [];
  const observe = ev.gate_level === "observe";

  const box = $("#detail");
  box.innerHTML = `
    <div class="row1" style="display:flex;gap:8px;align-items:center">
      <span class="badge ${ev.severity}">${SEV_TEXT[ev.severity]}</span>
      <span class="badge gate ${ev.gate_level}">${ev.gate_level}</span>
    </div>
    <h2>${esc(ev.target_title || ev.target_id)}</h2>
    <div class="meta">${esc(TYPE_TEXT[ev.type] || ev.type)} · ${fmtTs(ev.ts)} · 规则 ${esc(ev.rule_version)}</div>
    <dl class="kv">
      <dt>说明</dt><dd>${esc(ev.note || "-")}</dd>
      <dt>我方价格</dt><dd>${ev.my_price ? ev.my_price.toFixed(2) + " 元" : "未设置"}</dd>
      <dt>到手价置信</dt><dd>${last.confidence != null ? (last.confidence * 100).toFixed(0) + "%" : "-"}</dd>
      <dt>数据完整度</dt><dd>${missing.length
        ? `<span class="chips">${missing.map((m) => `<span class="chip-missing">缺失 ${esc(m)}</span>`).join("")}</span>`
        : "完整"}</dd>
      <dt>证据</dt><dd>${ev.evidence.map((x) => `<code>${esc(x)}</code>`).join(" ") || "-"}</dd>
    </dl>
    ${chart(prices)}
    ${observe && !s ? `<div class="gate-warn">数据置信度不足，系统只提供观察，不给出建议。可先用「监控目标」补全我方价格，或等待更完整的数据。</div>` : ""}
    <div id="sugg-box">${s ? renderSuggestion(s) : (observe ? "" : `
      <button class="btn" id="analyze">生成建议</button>`)}</div>
    ${renderSimilar(ev.similar_cases)}`;

  if (!s && !observe) {
    $("#analyze").addEventListener("click", async () => {
      const btn = $("#analyze");
      btn.disabled = true;
      btn.textContent = "分析中…";
      try {
        await api(`/api/events/${ev.id}/analyze`, { method: "POST" });
        const fresh = await api(`/api/events/${ev.id}`);
        const p = await api(`/api/targets/${encodeURIComponent(fresh.target_id)}/prices`);
        renderDetail(fresh, p);
        loadHealth();
      } catch (e) {
        btn.disabled = false;
        btn.textContent = "生成建议";
        alert("分析失败：" + e.message);
      }
    });
  } else {
    bindDecision(s);
  }
}

function renderSimilar(items) {
  if (!items || !items.length) return "";
  return `<div class="similar">
    <h4>相似历史案例（${items.length}）</h4>
    ${items.map((c) => `
      <div class="item">
        <div class="s">${esc(c.summary)}</div>
        <div class="a">归因：${esc(c.attribution)}</div>
        ${c.outcome_7d ? `<div class="o">7 日结果：${esc(c.outcome_7d)}</div>` : ""}
        <div class="o"><code>case:${esc(c.id)}</code> · 价格带 ${esc(c.price_band)}</div>
      </div>`).join("")}
  </div>`;
}

function renderSuggestion(s) {
  const g = s.guardrail || "unknown";
  const margin = s.margin_at_target != null ? (s.margin_at_target * 100).toFixed(1) + "%" : "—";
  const floor = s.margin_floor != null ? (s.margin_floor * 100).toFixed(0) + "%" : "—";

  return `<div class="suggestion">
    <h4>建议 · ${esc(ACTION_TEXT[s.action] || s.action)}
      <span class="muted">（置信 ${(s.confidence * 100).toFixed(0)}% · ${esc(s.generated_by)}）</span></h4>
    <div class="narrative">${esc(s.narrative)}</div>
    ${s.impact_low != null ? `<div class="muted" style="margin-top:8px;font-size:12.5px">
      每件价差：${s.impact_low.toFixed(2)} ~ ${s.impact_high.toFixed(2)} 元（正数=竞品更便宜）</div>` : ""}
    <div class="guardrail ${g}">
      <b>${GUARDRAIL_TEXT[g] || g}</b> · 目标价 ${s.target_price != null ? s.target_price.toFixed(2) + " 元" : "不改变"}
      · 毛利率 ${margin} / 下限 ${floor}<br>${esc(s.guardrail_note || "")}
    </div>
    <div class="actions" id="workflow-${s.id}">${workflowButtons(s)}</div>
    ${["executed", "accepted"].includes(s.status) ? outcomeBlock(s) : ""}
    <div id="timeline-box"></div>
  </div>`;
}

function workflowButtons(s) {
  const id = s.id;
  if (s.status === "pending") {
    return `<button class="btn small" data-wf="submit">提交执行</button>
      <button class="btn ghost small" data-wf="reject">不采纳</button>
      <span class="muted" style="align-self:center">待提交</span>`;
  }
  if (s.status === "submitted") {
    const actions = canApprove()
      ? `<button class="btn small" data-wf="approve">批准</button>
         <button class="btn ghost small" data-wf="reject">驳回</button>`
      : "";
    return `${actions}
      <span class="muted" style="align-self:center">等待审批${s.submitted_by ? "（提交人 " + esc(s.submitted_by) + "）" : ""}${canApprove() ? "" : " · 当前账号无审批权限"}</span>`;
  }
  if (s.status === "approved") {
    return `<button class="btn small" data-wf="execute">标记已执行</button>
      <span class="muted" style="align-self:center">已批准${s.approved_by ? "（" + esc(s.approved_by) + "）" : ""}</span>`;
  }
  const text = { rejected: "已驳回", cancelled: "已取消", executed: "已执行", accepted: "已采纳" }[s.status] || s.status;
  return `<span class="muted">状态：${esc(text)}${s.executed_price ? " · 执行价 " + s.executed_price : ""}</span>`;
}

function outcomeBlock(s) {
  return `<div class="actions" id="outcome-${s.id}">
    <span class="muted" style="align-self:center">7 日后结果</span>
    <button class="btn ghost small" data-res="improved">改善</button>
    <button class="btn ghost small" data-res="unchanged">无变化</button>
    <button class="btn ghost small" data-res="worse">变差</button>
    <span class="muted" style="align-self:center" id="outcome-msg-${s.id}"></span>
  </div>`;
}

async function refreshDetail() {
  if (!state.selected) return;
  const ev = await api(`/api/events/${state.selected}`);
  const prices = await api(`/api/targets/${encodeURIComponent(ev.target_id)}/prices`);
  renderDetail(ev, prices);
}

function bindDecision(s) {
  const box = $(`#workflow-${s.id}`);
  if (box) {
    $$("button[data-wf]", box).forEach((b) => {
      b.addEventListener("click", async () => {
        const wf = b.dataset.wf;
        let body = {};
        if (wf === "execute") {
          const raw = prompt("执行价（元）", s.target_price != null ? s.target_price : "");
          if (raw === null) return;
          body.executed_price = raw.trim() === "" ? null : Number(raw);
        }
        try {
          await api(`/api/suggestions/${s.id}/${wf}`, {
            method: "POST",
            body: JSON.stringify(body),
          });
          await refreshDetail();
          loadHealth();
        } catch (e) {
          alert("操作失败：" + e.message);
        }
      });
    });
  }

  const ob = $(`#outcome-${s.id}`);
  if (ob) {
    $$("button[data-res]", ob).forEach((b) => {
      b.addEventListener("click", async () => {
        const r = await api(`/api/suggestions/${s.id}/outcome`, {
          method: "POST",
          body: JSON.stringify({ result: b.dataset.res }),
        });
        $(`#outcome-msg-${s.id}`).textContent = r.case_id
          ? "已记录，并沉淀为案例" : "已记录";
        loadHealth();
      });
    });
  }

  loadTimeline(s.id);
}

async function loadTimeline(sid) {
  const rows = await api(`/api/suggestions/${sid}/timeline`);
  const box = $("#timeline-box");
  if (!box) return;
  if (!rows.length) { box.innerHTML = ""; return; }
  box.innerHTML = `<div class="timeline"><h4>审批记录</h4>
    ${rows.map((r) => `<div class="row"><b>${esc(WF_TEXT[r.action] || r.action)}</b>
      <span>${esc(r.actor)} · ${fmtTs(r.at)}</span>
      <span>${esc(r.note || "")}</span></div>`).join("")}</div>`;
}

const GUARDRAIL_TEXT = {
  ok: "护栏通过", warning: "接近毛利下限", blocked: "毛利护栏拦截", unknown: "缺成本数据",
};
const WF_TEXT = {
  submit: "提交", approve: "批准", reject: "驳回", execute: "执行", cancel: "取消",
};

// ---------- suggestions ----------
async function loadSuggestions() {
  const rows = await api("/api/suggestions");
  const ul = $("#suggestion-list");
  if (!rows.length) {
    ul.innerHTML = `<li class="muted">暂无建议</li>`;
    return;
  }
  ul.innerHTML = rows.map((s) => `
    <li>
      <div class="head">
        <span class="badge gate ${s.gate_level}">${s.gate_level}</span>
        <span class="action">${esc(ACTION_TEXT[s.action] || s.action)}</span>
        <span class="muted">${esc(s.target_title || s.target_id || "")} · ${fmtTs(s.created_at)}</span>
        <span class="muted" style="margin-left:auto">${(s.confidence * 100).toFixed(0)}% · ${esc(s.generated_by)}</span>
      </div>
      <div class="txt">${esc(s.narrative)}</div>
    </li>`).join("");
}

// ---------- targets ----------
async function loadTargets() {
  const rows = await api("/api/targets");
  const tbody = $("#target-table tbody");
  tbody.innerHTML = rows.map((t) => `
    <tr data-id="${esc(t.id)}">
      <td>${esc(t.title)}</td>
      <td><input class="inp my-sku" value="${esc(t.my_sku || "")}" placeholder="SKU" style="width:110px"></td>
      <td><input class="inp my-price" value="${t.my_price ?? ""}" placeholder="价格" style="width:90px"></td>
      <td>${t.active ? "启用" : "停用"}</td>
      <td><button class="btn ghost small save">保存</button></td>
    </tr>`).join("");

  $$("#target-table .save").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const tr = btn.closest("tr");
      const id = tr.dataset.id;
      const my_sku = $(".my-sku", tr).value.trim() || null;
      const raw = $(".my-price", tr).value.trim();
      const my_price = raw === "" ? null : Number(raw);
      await api(`/api/targets/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: JSON.stringify({ my_sku, my_price }),
      });
      btn.textContent = "已保存";
      setTimeout(() => (btn.textContent = "保存"), 1200);
    });
  });
}

// ---------- ask (自然语言问数) ----------
async function loadAskTab() {
  const tpls = await api("/api/ask/templates");
  const examples = tpls.flatMap((t) => t.examples || []).slice(0, 6);
  const box = $("#ask-examples");
  if (box.dataset.ready) return;
  box.innerHTML = examples
    .map((e) => `<button class="ask-example">${esc(e)}</button>`).join("");
  $$("#ask-examples .ask-example").forEach((b) => {
    b.addEventListener("click", () => {
      $("#ask-input").value = b.textContent;
      submitAsk();
    });
  });
  box.dataset.ready = "1";
}

async function submitAsk() {
  const q = $("#ask-input").value.trim();
  if (!q) return;
  const btn = $("#ask-btn");
  btn.disabled = true;
  try {
    const r = await api("/api/ask", {
      method: "POST",
      body: JSON.stringify({ question: q }),
    });
    renderAskResult(r);
  } catch (e) {
    $("#ask-answer").innerHTML = `<div class="answer-card"><div class="a">查询失败：${esc(e.message)}</div></div>`;
  } finally {
    btn.disabled = false;
  }
}

function renderAskResult(r) {
  if (!r.ok) {
    $("#ask-answer").innerHTML = `<div class="answer-card">
      <div class="a">${esc(r.answer || "没听懂这个问题")}</div>
      ${(r.suggestions || []).map((s) => `<div class="hint">· ${esc(s)}</div>`).join("")}
    </div>`;
    return;
  }
  const rows = r.rows || [];
  const cols = rows.length ? Object.keys(rows[0]) : [];
  $("#ask-answer").innerHTML = `<div class="answer-card">
    <div class="a">${esc(r.answer)}</div>
    <div class="meta">模板：${esc(r.template_title || r.template)} ·
      参数 ${esc(JSON.stringify(r.params))} · ${rows.length} 行</div>
    ${rows.length ? `<table class="table" style="margin-top:12px">
      <thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>
      <tbody>${rows.map((row) => `<tr>${cols.map((c) => `<td>${esc(row[c])}</td>`).join("")}</tr>`).join("")}</tbody>
    </table>` : ""}
  </div>`;
}

// ---------- reviews ----------
async function loadReviewsTab() {
  const targets = await api("/api/targets");
  const sel = $("#review-target");
  const current = sel.value;
  sel.innerHTML = targets
    .map((t) => `<option value="${esc(t.id)}">${esc(t.title)}</option>`)
    .join("");
  if (current) sel.value = current;
  if (sel.value) await loadReviewData(sel.value);
}

async function loadReviewData(tid) {
  const reviews = await api(`/api/reviews?target_id=${encodeURIComponent(tid)}`);
  $("#review-list").innerHTML = reviews.length
    ? reviews.map((r) => `<div class="review-item">
        <span class="star">${r.rating ?? "-"}★</span>
        <span class="txt">${esc(r.content)}</span>
      </div>`).join("")
    : `<div class="muted">暂无评论，点「载入示例评论」。</div>`;

  try {
    const ins = await api(`/api/targets/${encodeURIComponent(tid)}/insights`);
    renderInsight(ins);
  } catch {
    $("#insight-box").innerHTML = `<div class="muted">尚无洞察，点「生成洞察」。</div>`;
  }
}

function renderInsight(ins) {
  const topics = ins.topics || [];
  $("#insight-box").innerHTML = `<div class="insight-card">
    <div class="summary">${esc(ins.summary)}</div>
    ${topics.map((t) => `<div class="topic-row">
      <span class="name">${esc(t.name)}</span>
      <span class="bar ${t.negative_share >= 0.5 ? "neg" : ""}">
        <span style="width:${Math.max(4, t.share * 100)}%"></span></span>
      <span class="num">${t.count} 条 · 负面 ${(t.negative_share * 100).toFixed(0)}%</span>
    </div>`).join("")}
    ${(ins.opportunities || []).map((o) => `<div class="opportunity">${esc(o)}</div>`).join("")}
    <div class="muted" style="margin-top:10px;font-size:12px">
      来源 ${esc(ins.generated_by)} · ${ins.review_count} 条评论 · 窗口 ${ins.window_days} 天
    </div>
  </div>`;
}

async function seedReviews() {
  const tid = $("#review-target").value;
  const r = await api(`/api/reviews/seed?target_id=${encodeURIComponent(tid)}`, { method: "POST" });
  $("#review-hint").textContent = `新增 ${r.inserted} 条，重复 ${r.duplicates} 条`;
  await loadReviewData(tid);
  loadHealth();
}

async function runInsight() {
  const tid = $("#review-target").value;
  try {
    const ins = await api(`/api/targets/${encodeURIComponent(tid)}/insights`, { method: "POST" });
    renderInsight(ins);
    $("#review-hint").textContent = ins.event_id ? "已生成，并触发评论异动告警" : "已生成洞察";
    loadEvents();
  } catch (e) {
    $("#review-hint").textContent = "生成失败：" + e.message;
  }
}

// ---------- approvals ----------
async function loadApprovals() {
  const rows = await api("/api/approvals/inbox");
  const badge = $("#approval-badge");
  if (badge) badge.textContent = rows.length ? rows.length : "";

  const box = $("#approval-list");
  if (!rows.length) {
    box.innerHTML = `<div class="muted">没有待审批的建议。</div>`;
    return;
  }
  const can = canApprove();
  box.innerHTML = rows.map((s) => `
    <div class="approval-item" data-id="${esc(s.id)}">
      <div class="top">
        <span class="badge gate ${s.gate_level}">${s.gate_level}</span>
        <span class="act">${esc(ACTION_TEXT[s.action] || s.action)}</span>
        <span class="muted">${esc(s.target_title || s.target_id)} · 提交人 ${esc(s.submitted_by || "-")}</span>
        <span class="muted" style="margin-left:auto">毛利率 ${s.margin_at_target != null ? (s.margin_at_target * 100).toFixed(1) + "%" : "—"}</span>
      </div>
      <div class="nar">${esc(s.narrative)}</div>
      <div class="btns">
        ${can
          ? `<button class="btn small" data-approve="${esc(s.id)}">批准</button>
             <button class="btn ghost small" data-reject="${esc(s.id)}">驳回</button>`
          : `<span class="muted">当前账号无审批权限，仅可查看</span>`}
      </div>
    </div>`).join("");

  if (!can) return;
  $$("#approval-list button[data-approve]").forEach((b) => {
    b.addEventListener("click", () => decideApproval(b.dataset.approve, "approve"));
  });
  $$("#approval-list button[data-reject]").forEach((b) => {
    b.addEventListener("click", () => decideApproval(b.dataset.reject, "reject"));
  });
}

async function decideApproval(id, kind) {
  try {
    await api(`/api/suggestions/${id}/${kind}`, { method: "POST", body: "{}" });
    await loadApprovals();
    loadHealth();
  } catch (e) {
    alert("操作失败：" + e.message);
  }
}

// ---------- mappings ----------
async function loadMappings() {
  const [pending, confirmed] = await Promise.all([
    api("/api/mappings?status=pending"),
    api("/api/mappings?status=confirmed"),
  ]);
  $("#pending-count").textContent = pending.length ? `(${pending.length})` : "";
  $("#pending-list").innerHTML = pending.length
    ? pending.map((m) => mappingCard(m, true)).join("")
    : `<div class="muted">暂无待确认。先点「载入示例商品」，再点「生成匹配建议」。</div>`;
  $("#confirmed-list").innerHTML = confirmed.length
    ? confirmed.map((m) => mappingCard(m, false)).join("")
    : `<div class="muted">还没有已对齐的 SKU。</div>`;

  $$("#pending-list button[data-map]").forEach((b) => {
    b.addEventListener("click", async () => {
      const id = b.closest(".map-item").dataset.id;
      await api(`/api/mappings/${id}/decide`, {
        method: "POST", body: JSON.stringify({ decision: b.dataset.map }),
      });
      await loadMappings();
      loadHealth();
    });
  });
}

function mappingCard(m, actionable) {
  return `<div class="map-item" data-id="${esc(m.id)}">
    <div class="row">
      <span class="score">${(m.score * 100).toFixed(0)}</span>
      <span class="s">${esc(m.my_title || m.my_sku)}</span>
      <span class="arrow">→</span>
      <span class="s">${esc(m.target_title || m.target_id)}</span>
    </div>
    <div class="meta">我方 ${esc(m.my_sku)}${m.my_price ? " · " + m.my_price + " 元" : ""} · ${esc(m.method || "")}${m.decided_by ? " · 由 " + esc(m.decided_by) + " 确认" : ""}</div>
    ${actionable ? `<div class="acts">
      <button class="btn small" data-map="confirmed">确认对齐</button>
      <button class="btn ghost small" data-map="rejected">忽略</button>
    </div>` : ""}
  </div>`;
}

async function seedProducts() {
  await api("/api/my-products/seed", { method: "POST" });
  $("#mapping-hint").textContent = "示例商品已载入，点「生成匹配建议」";
  loadHealth();
}

async function suggestMappings() {
  const r = await api("/api/mappings/suggest", { method: "POST" });
  $("#mapping-hint").textContent = `新增 ${r.created} 条建议，待确认 ${r.pending} 条`;
  await loadMappings();
}

// ---------- ops ----------
async function loadOps() {
  const o = await api("/api/ops");
  const s = o.scheduler;
  const m = o.metrics || {};
  const fallbackPct = m.calls ? Math.round((m.fallback_rate || 0) * 100) : 0;

  $("#ops-grid").innerHTML = `
    <div class="op-card">
      <h4>后台调度</h4>
      <div class="big">${s.enabled ? "运行中" : "已关闭"}</div>
      <div class="sub">${s.started_at ? "启动于 " + fmtTs(s.started_at) : "未启动"}</div>
      <div class="acts"><button class="btn ghost small" data-run="inbox_scan">立即扫描收件箱</button></div>
    </div>
    <div class="op-card">
      <h4>文件收件箱</h4>
      <div class="big">${o.inbox.pending}</div>
      <div class="sub">待处理文件（data/inbox）· 失败 ${o.inbox.failed ?? 0}</div>
    </div>
    <div class="op-card">
      <h4>数据新鲜度</h4>
      <div class="big">${o.freshness?.lag_hours == null ? "—" : o.freshness.lag_hours + " h"}</div>
      <div class="sub">SLA ${o.freshness?.sla_hours ?? "—"} 小时 · ${o.freshness?.stale ? "已超时" : "正常"}</div>
    </div>
    <div class="op-card">
      <h4>模型调用 · 24h</h4>
      <div class="big">${m.calls ?? 0}</div>
      <div class="sub">回退率 ${fallbackPct}% · P95 ${m.p95_latency_ms ?? "—"}ms</div>
    </div>
    <div class="op-card">
      <h4>三方连接器</h4>
      <div class="big">${o.connector?.configured ? "已配置" : "未配置"}</div>
      <div class="sub">LIRA_CONNECTOR_URL，每 30 分钟同步一次</div>
    </div>
    <div class="op-card">
      <h4>备份</h4>
      <div class="big">${(o.backups || []).length}</div>
      <div class="sub">${o.backups?.[0] ? "最近：" + o.backups[0] : "每日 03:30 自动备份"}</div>
    </div>
    <div class="op-card">
      <h4>登录鉴权</h4>
      <div class="big">${o.auth_enabled ? "已启用" : "未启用"}</div>
      <div class="sub">${o.auth_enabled ? "操作者来自登录账号" : "操作者取自 X-Actor，默认 local"}</div>
    </div>
    <div class="op-card">
      <h4>消息推送</h4>
      <div class="big">${o.webhook ? "已配置" : "未配置"}</div>
      <div class="sub">LIRA_WEBHOOK → 企业微信/钉钉机器人</div>
    </div>`;

  $$("#ops-grid button[data-run]").forEach((b) => {
    b.addEventListener("click", async () => {
      const r = await api(`/api/ops/run?kind=${b.dataset.run}`, { method: "POST" });
      $("#mapping-hint").textContent = `${r.kind}：${r.result}`;
      await loadOps();
      loadHealth();
    });
  });

  const health = o.collection || [];
  $("#collector-table tbody").innerHTML = health.length
    ? health.map((c) => `<tr>
        <td>${esc(c.collector)}</td>
        <td>${c.snapshots}</td>
        <td>${fmtTs(c.last_ts)}</td>
        <td>${c.lag_hours == null ? "—" : c.lag_hours + " 小时"}</td>
        <td>${c.stale ? '<span class="badge L2">滞后</span>' : '<span class="badge L1">正常</span>'}</td>
      </tr>`).join("")
    : `<tr><td colspan="5" class="muted">暂无采集记录</td></tr>`;
  $("#freshness-note").textContent = `SLA ${o.freshness?.sla_hours ?? "—"} 小时`;
  const failed = o.inbox?.failed_files || [];
  $("#failed-files").innerHTML = failed.length
    ? `失败文件 ${o.inbox.failed} 个：` + failed.map((f) => `<code>${esc(f.name)}</code>`).join(" ")
    : "没有失败文件";

  const rows = s.recent || [];
  $("#job-table tbody").innerHTML = rows.length
    ? rows.map((r) => `<tr>
        <td>${esc(r.kind)}</td>
        <td>${r.status === "ok" ? "成功" : "失败"}</td>
        <td>${fmtTs(r.started_at)}</td>
        <td class="muted">${esc((r.detail || "").slice(0, 80))}</td>
      </tr>`).join("")
    : `<tr><td colspan="4" class="muted">暂无任务记录</td></tr>`;
}

// ---------- cases ----------
async function loadCases() {
  const rows = await api("/api/cases");
  $("#case-count").textContent = `共 ${rows.length} 条`;
  const box = $("#case-list");
  if (!rows.length) {
    box.innerHTML = `<div class="muted">案例库为空。点「载入示例案例」或新增一条。</div>`;
    return;
  }
  box.innerHTML = rows.map((c) => `
    <div class="case-card">
      <div class="head">
        <span class="badge gate">${esc(c.event_type)}</span>
        <span>${esc(c.category)} · ${esc(c.price_band)}</span>
        <span style="margin-left:auto">${esc(c.embed_provider)}</span>
      </div>
      <div class="summary">${esc(c.summary)}</div>
      <div class="attr">归因：${esc(c.attribution)}</div>
      ${c.outcome_7d ? `<div class="outcome">7 日结果：${esc(c.outcome_7d)}</div>` : ""}
      <div class="outcome"><code>case:${esc(c.id)}</code>${c.decision ? " · 当时决策：" + esc(c.decision) : ""}</div>
    </div>`).join("");
}

async function seedCases() {
  const r = await api("/api/cases/seed", { method: "POST" });
  $("#case-count").textContent = `新增 ${r.added} 条，共 ${r.total} 条`;
  await loadCases();
  loadHealth();
}

async function addCase() {
  const body = {
    category: $("#c-category").value.trim() || "通用",
    event_type: $("#c-event").value,
    price_band: $("#c-band").value.trim() || "0-50",
    summary: $("#c-summary").value.trim(),
    attribution: $("#c-attribution").value.trim(),
    decision: $("#c-decision").value,
    outcome_7d: $("#c-outcome").value.trim() || null,
  };
  if (!body.summary || !body.attribution) {
    $("#case-msg").textContent = "摘要和归因不能为空";
    return;
  }
  await api("/api/cases", { method: "POST", body: JSON.stringify(body) });
  $("#case-msg").textContent = "已保存";
  $("#c-summary").value = $("#c-attribution").value = $("#c-outcome").value = "";
  await loadCases();
  loadHealth();
}

// ---------- import ----------
function log(msg) {
  $("#import-log").textContent += msg + "\n";
}

async function uploadCsv() {
  const file = $("#csv-file").files[0];
  if (!file) return alert("请选择 CSV 文件");
  const fd = new FormData();
  fd.append("file", file);
  log(`上传 ${file.name} …`);
  try {
    const r = await api("/v1/import/csv", { method: "POST", body: fd });
    log(JSON.stringify(r, null, 2));
    await Promise.all([loadHealth(), loadEvents()]);
  } catch (e) {
    log("失败：" + e.message);
  }
}

function demoSnapshots() {
  const d1 = "2026-10-23T02:17:00+08:00";
  const d2 = "2026-10-24T02:17:00+08:00";
  return {
    d1: [
      { target_id: "t1", ts: d1, collector: "yd-v1", source_tier: 3,
        observation: { list_price: 299, coupons: [], promotions: [], coin: { rate: 0, cap: 0 },
          account_tier: "normal", title: "竞品A·洗护套装" } },
      { target_id: "t2", ts: d1, collector: "api-vendor", source_tier: 1,
        observation: { list_price: 199, coupons: [], promotions: [], coin: { rate: 0, cap: 0 },
          account_tier: "normal", title: "竞品B·控油洗发水" } },
      { target_id: "t3", ts: d1, collector: "yd-v1", source_tier: 3,
        observation: { list_price: 89, coupons: [], promotions: [], coin: { rate: 0, cap: 0 },
          account_tier: "normal", title: "竞品C·护发素" } },
    ],
    d2: [
      { target_id: "t1", ts: d2, collector: "yd-v1", source_tier: 3,
        observation: { list_price: 299, coupons: [{ kind: "shop", threshold: 299, discount: 30, stackable: false }],
          promotions: [], coin: { rate: 0, cap: 0 }, account_tier: "normal", title: "竞品A·洗护套装" } },
      { target_id: "t2", ts: d2, collector: "api-vendor", source_tier: 1,
        observation: { list_price: 149, coupons: [], promotions: [], coin: { rate: 0, cap: 0 },
          account_tier: "normal", title: "竞品B·控油洗发水" } },
      { target_id: "t3", ts: d2, collector: "yd-v1", source_tier: 3,
        observation: { list_price: 89, coupons: [], promotions: [], coin: { rate: 0, cap: 0 },
          account_tier: "normal", title: "竞品C·护发素" } },
    ],
  };
}

async function loadDemo() {
  const { d1, d2 } = demoSnapshots();
  log("载入第 1 天快照 …");
  await api("/v1/ingest/snapshots", { method: "POST", body: JSON.stringify({ snapshots: d1 }) });
  log("设置 t3 我方价格 = 100 …");
  await api("/api/targets/t3", { method: "PATCH", body: JSON.stringify({ my_price: 100, my_sku: "SKU-C" }) });
  log("载入第 2 天快照 …");
  const r = await api("/v1/ingest/snapshots", { method: "POST", body: JSON.stringify({ snapshots: d2 }) });
  log(JSON.stringify(r, null, 2));
  await Promise.all([loadHealth(), loadEvents()]);
  log("完成。切到「今日事件」查看。");
}

// ---------- wiring ----------
const PAGE_META = {
  events: ["今日事件", "竞品动态与需要你决策的事项"],
  suggestions: ["建议", "按状态流转的执行建议"],
  approvals: ["审批", "等待批准的建议，批准后运营才能执行"],
  reviews: ["评论洞察", "竞品评论的话题分布与机会点"],
  cases: ["案例库", "历史归因案例，供新事件检索参照"],
  ask: ["问数", "自然语言查询 · 固定模板 · 不拼 SQL"],
  targets: ["监控目标", "我方 SKU 与价格配置"],
  mappings: ["SKU 对齐", "竞品与我方 SKU 的对应关系"],
  import: ["数据导入", "CSV 上传与文件收件箱"],
  ops: ["系统", "调度、采集、模型调用与备份状态"],
};

function switchView(name) {
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === name));
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  const meta = PAGE_META[name];
  if (meta) {
    $("#page-title").textContent = meta[0];
    $("#page-sub").textContent = meta[1];
  }
  if (name === "suggestions") loadSuggestions();
  if (name === "approvals") loadApprovals();
  if (name === "targets") loadTargets();
  if (name === "cases") loadCases();
  if (name === "mappings") loadMappings();
  if (name === "reviews") loadReviewsTab();
  if (name === "ask") loadAskTab();
  if (name === "ops") loadOps();
}

$$(".tab").forEach((t) => t.addEventListener("click", () => switchView(t.dataset.view)));
$$(".chip").forEach((c) => c.addEventListener("click", () => {
  $$(".chip").forEach((x) => x.classList.remove("active"));
  c.classList.add("active");
  state.severity = c.dataset.sev;
  loadEvents();
}));
$("#refresh").addEventListener("click", () => Promise.all([loadHealth(), loadFreshness(), loadEvents()]));
$("#upload").addEventListener("click", uploadCsv);
$("#demo").addEventListener("click", loadDemo);
$("#seed-cases").addEventListener("click", seedCases);
$("#add-case").addEventListener("click", addCase);
$("#seed-products").addEventListener("click", seedProducts);
$("#suggest-mappings").addEventListener("click", suggestMappings);
$("#refresh-approvals").addEventListener("click", loadApprovals);
$("#seed-reviews").addEventListener("click", seedReviews);
$("#run-insight").addEventListener("click", runInsight);
$("#review-target").addEventListener("change", (e) => loadReviewData(e.target.value));
$("#ask-btn").addEventListener("click", submitAsk);
$("#ask-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") submitAsk();
});

const logoutBtn = $("#logout");
if (logoutBtn) logoutBtn.addEventListener("click", logout);

boot();
