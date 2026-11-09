from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, TypedDict

from . import (
    agent, cases as case_store, config, db, guardrail, handoff, llm, memory,
    metrics, pricing, safety, skills, stream, tools, tracing,
)
from .contracts import PricePoint

try:
    from langgraph.graph import END, StateGraph
except ImportError:  # pragma: no cover - 允许无 LangGraph 的降级运行
    END = "__end__"
    StateGraph = None  # type: ignore[assignment]


class AgentState(TypedDict, total=False):
    event_id: str
    run_id: str
    trigger: str
    seq: int
    facts: dict[str, Any]
    plan: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    allowed_evidence: list[str]
    tainted: bool
    analysis: dict[str, Any]
    pricing: dict[str, Any]
    checks: dict[str, Any]
    risk: dict[str, Any]
    proposal: dict[str, Any]
    suggestion: dict[str, Any]
    skill: dict[str, Any]


def _json(value: Any, limit: int = 4000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(value)
    return text[:limit]


def _new_run(event_id: str, trigger: str) -> str:
    run_id = db.new_id()
    model = config.OLLAMA_MODEL if config.LLM_ENABLED != "off" else "deterministic"
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO agent_run (id, event_id, trigger, status, model, started_at)"
            " VALUES (?,?,?,?,?,?)",
            (run_id, event_id, trigger, "running", model, db.now_iso()),
        )
    return run_id


def _step(
    run_id: str,
    seq: int,
    kind: str,
    name: str,
    input_obj: Any = None,
    output_obj: Any = None,
    status: str = "ok",
    latency_ms: int = 0,
    error: str | None = None,
) -> None:
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO agent_step (id, run_id, seq, kind, name, status, input,"
            " output, latency_ms, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                db.new_id(), run_id, seq, kind, name, status,
                _json(input_obj), _json({"error": error} if error else output_obj),
                latency_ms, db.now_iso(),
            ),
        )
        conn.execute(
            "UPDATE agent_run SET step_count = ? WHERE id = ?", (seq, run_id)
        )
    tracing.record(
        f"{kind}/{name}", kind=kind, status=status, run_id=run_id,
        duration_ms=latency_ms,
        attributes={"input": _json(input_obj)[:500] if input_obj else None},
    )


def _finish_run(
    run_id: str,
    status: str,
    suggestion_id: str | None,
    latency_ms: int,
    error: str | None,
    step_count: int,
    model: str | None = None,
) -> None:
    with db.get_db() as conn:
        usage = conn.execute(
            "SELECT COALESCE(SUM(prompt_tokens), 0) AS p,"
            " COALESCE(SUM(completion_tokens), 0) AS c,"
            " COALESCE(SUM(cost), 0) AS cost FROM model_call WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        conn.execute(
            "UPDATE agent_run SET status = ?, suggestion_id = ?, latency_ms = ?,"
            " error = ?, step_count = ?, finished_at = ?,"
            " model = COALESCE(?, model), prompt_tokens = ?, completion_tokens = ?,"
            " cost = ? WHERE id = ?",
            (
                status, suggestion_id, latency_ms, error, step_count,
                db.now_iso(), model, usage["p"], usage["c"], usage["cost"], run_id,
            ),
        )


def _load_context(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    seq = state.get("seq", 0) + 1
    started = time.perf_counter()
    try:
        with db.get_db() as conn:
            event = conn.execute(
                "SELECT * FROM event WHERE id = ?", (state["event_id"],)
            ).fetchone()
            if not event:
                raise ValueError("event not found")
            target = conn.execute(
                "SELECT * FROM target WHERE id = ?", (event["target_id"],)
            ).fetchone()
            point = conn.execute(
                "SELECT * FROM price_point WHERE target_id = ? AND ts = ?",
                (event["target_id"], event["ts"]),
            ).fetchone()
            if not point:
                raise ValueError("price point missing")
            prev = conn.execute(
                "SELECT * FROM price_point WHERE target_id = ? AND ts < ?"
                " ORDER BY ts DESC LIMIT 1",
                (event["target_id"], event["ts"]),
            ).fetchone()
            product = None
            if target and target["my_sku"]:
                product = conn.execute(
                    "SELECT cost, margin_floor, price, title FROM my_product"
                    " WHERE sku = ?",
                    (target["my_sku"],),
                ).fetchone()

        mid = (point["price_low"] + point["price_high"]) / 2
        prev_point = None
        if prev:
            prev_point = {
                "ts": prev["ts"],
                "point": (prev["price_low"] + prev["price_high"]) / 2,
                "price_low": prev["price_low"],
                "price_high": prev["price_high"],
                "confidence": prev["confidence"],
                "missing_fields": db.loads(prev["missing_fields"], []),
            }
        facts = {
            "event_id": event["id"],
            "target_id": event["target_id"],
            "event_type": event["type"],
            "severity": event["severity"],
            "gate_level": event["gate_level"],
            "note": event["note"],
            "ts": event["ts"],
            "title": target["title"] if target else event["target_id"],
            "price_low": point["price_low"],
            "price_high": point["price_high"],
            "point": mid,
            "confidence": point["confidence"],
            "missing_fields": db.loads(point["missing_fields"], []),
            "prev_point": prev_point,
            "my_price": target["my_price"] if target else None,
            "my_sku": target["my_sku"] if target else None,
            "region": (target["region"] if target else None) or "全国",
            "strategy": (target["pricing_strategy"] if target else None) or "follow",
            "holdout": bool(target["holdout"]) if target else False,
            "cost": product["cost"] if product else None,
            "margin_floor": (
                product["margin_floor"]
                if product and product["margin_floor"] is not None
                else 0.15
            ),
        }
        facts["memory_notes"] = memory.recall_text(
            run_id=run_id, query=str(facts.get("title") or ""), limit=3
        )
        _step(
            run_id, seq, "context", "加载事件与价格",
            {"event_id": state["event_id"]},
            {
                "title": facts["title"], "event_type": facts["event_type"],
                "price_low": facts["price_low"], "price_high": facts["price_high"],
                "has_prev": prev_point is not None,
            },
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        return {
            "facts": facts,
            "allowed_evidence": db.loads(event["evidence"], []),
            "seq": seq,
        }
    except Exception as exc:
        _step(
            run_id, seq, "context", "加载事件与价格", {"event_id": state["event_id"]},
            None, "error", int((time.perf_counter() - started) * 1000), str(exc),
        )
        raise


def _deterministic_plan(facts: dict[str, Any]) -> list[dict[str, Any]]:
    band = case_store.price_band_of(facts["point"])
    delta = None
    prev = facts.get("prev_point")
    if prev and prev["point"]:
        delta = round((facts["point"] - prev["point"]) / prev["point"], 4)
    query = " ".join(
        filter(None, [facts["title"], facts.get("note"), facts["event_type"]])
    )
    plan = [
        {
            "tool": "collection_health",
            "args": {},
            "reason": "先确认数据新鲜度，再判断事实是否可信",
        },
        {
            "tool": "price_history",
            "args": {"target_id": facts["target_id"], "days": 30},
            "reason": "判断是短期波动还是结构性变化",
        },
        {
            "tool": "search_cases",
            "args": {
                "query": query,
                "event_type": facts["event_type"],
                "price_band": band,
                "delta_pct": delta,
                "limit": 3,
            },
            "reason": "检索历史相似案例，作为归因依据",
        },
        {
            "tool": "search_docs",
            "args": {"query": query, "limit": 3},
            "reason": "检索平台规则与玩法文档，引用时必须带 doc:<id>",
        },
        {
            "tool": "my_product",
            "args": {"target_id": facts["target_id"]},
            "reason": "读取成本与毛利下限",
        },
    ]
    if facts.get("my_price") is not None:
        plan.append(
            {
                "tool": "simulate_price",
                "args": {
                    "target_id": facts["target_id"],
                    "new_price": round(facts["point"], 2),
                },
                "reason": "模拟跟进价位的毛利与护栏",
            }
        )
    return plan


def _maybe_llm_plan(
    facts: dict[str, Any], fallback: list[dict[str, Any]]
) -> list[dict[str, Any]] | None:
    if os.getenv("LIRA_AGENT_LLM_PLANNER", "off") != "on":
        return None
    specs = [
        {
            "type": "function",
            "function": {
                "name": item["name"],
                "description": item["description"],
                "parameters": item["input_schema"],
            },
        }
        for item in tools.list_tools()
    ]
    question = (
        f"{facts['event_type']} 事件：{facts['title']}；{facts.get('note') or ''}；"
        f"到手价 {facts['price_low']}-{facts['price_high']}，置信 {facts['confidence']:.0%}；"
        f"我方价 {facts.get('my_price')}。请选择需要调用的工具。"
    )
    payload = agent.call_with_tools(question, specs)
    plan = agent.parse_tool_calls(payload, set(tools.TOOLS), limit=5)
    if not plan:
        return None
    names = {item["tool"] for item in plan}
    for item in fallback:
        if item["tool"] in {"collection_health", "search_cases", "my_product"}:
            if item["tool"] not in names:
                plan.append(item)
    return plan


def _plan_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    seq = state.get("seq", 0) + 1
    started = time.perf_counter()
    facts = state["facts"]
    with db.get_db() as conn:
        skill = skills.pick_skill(conn, facts["event_type"], facts["severity"])
        conn.execute(
            "UPDATE agent_run SET skill_id = ? WHERE id = ?",
            (skill["id"], run_id),
        )

    deterministic = _deterministic_plan(facts)
    allowed_tools = set(skill.get("allowed_tools") or [])
    plan = [item for item in deterministic if item["tool"] in allowed_tools] or deterministic
    llm_plan = _maybe_llm_plan(facts, plan)
    if llm_plan:
        filtered = [item for item in llm_plan if item["tool"] in allowed_tools]
        plan = filtered or plan

    with db.get_db() as conn:
        conn.execute(
            "UPDATE agent_run SET plan = ? WHERE id = ?", (_json(plan, 8000), run_id)
        )
    _step(
        run_id, seq, "plan", "生成执行计划",
        {
            "event_type": facts["event_type"],
            "severity": facts["severity"],
            "skill": skill["name"],
        },
        plan,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    return {"plan": plan, "skill": skill, "seq": seq}


def _act_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    seq = state.get("seq", 0)
    results: list[dict[str, Any]] = []
    for item in state.get("plan", []):
        seq += 1
        started = time.perf_counter()
        status = "ok"
        error = None
        result = None
        try:
            result = tools.call_tool(item["tool"], item.get("args") or {})
        except Exception as exc:
            status = "error"
            error = str(exc)
        latency = int((time.perf_counter() - started) * 1000)
        _step(
            run_id, seq, "tool", item["tool"], item.get("args"), result,
            status, latency, error,
        )
        results.append(
            {
                "tool": item["tool"],
                "args": item.get("args") or {},
                "status": status,
                "result": result,
                "error": error,
                "latency_ms": latency,
            }
        )
    tainted = bool(state.get("tainted"))
    for item in results:
        if item["tool"] == "search_docs" and item["status"] == "ok" and item["result"]:
            if item["result"].get("chunks"):
                tainted = True
    return {"tool_results": results, "seq": seq, "tainted": tainted}


REACT_SCHEMA = {
    "type": "object",
    "properties": {
        "done": {"type": "boolean"},
        "tool": {"type": "string"},
        "args": {"type": "object"},
        "reason": {"type": "string"},
    },
    "required": ["done"],
}


def _ask_react(
    state: AgentState,
    results: list[dict[str, Any]],
    allowed: list[str],
    step: int,
) -> dict[str, Any] | None:
    facts = state.get("facts") or {}
    used = [
        {"tool": item["tool"], "args": item.get("args"),
         "status": item["status"]}
        for item in results
    ]
    response = llm.complete(
        [
            {
                "role": "system",
                "content": (
                    "你是竞品情报 Agent 的规划器。只输出 JSON。\n"
                    "根据已有工具结果判断是否还需要补充证据。\n"
                    "可用工具：" + ", ".join(allowed) + "\n"
                    '已完成则输出 {"done": true}；否则输出 {"done": false, "tool": "<工具名>", "args": {...}, "reason": "<20字>"}。\n'
                    "不得重复调用相同工具与参数；不得臆造工具。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "step": step,
                        "event_type": facts.get("event_type"),
                        "severity": facts.get("severity"),
                        "title": facts.get("title"),
                        "confidence": facts.get("confidence"),
                        "done_tools": used,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        kind="planner",
        schema=REACT_SCHEMA,
        max_tokens=160,
    )
    if response is None:
        return None
    return agent._extract_json(response.text)


def _react_node(state: AgentState) -> AgentState:
    """有界 ReAct：最多 N 步，无进展或超时即停止，结果写回 tool_results。"""
    run_id = state["run_id"]
    seq = state.get("seq", 0)
    results = list(state.get("tool_results") or [])
    if os.getenv("LIRA_AGENT_LOOP", "on") != "on":
        return {"tool_results": results, "seq": seq}
    if not agent._llm_available():
        return {"tool_results": results, "seq": seq}

    skill = state.get("skill") or {}
    allowed = list(
        safety.restrict_tools(
            sorted(set(skill.get("allowed_tools") or tools.TOOLS)),
            tainted=bool(state.get("tainted")),
        )
    )
    started = time.perf_counter()
    used = {
        (item["tool"], json.dumps(item.get("args") or {}, sort_keys=True))
        for item in results
    }
    steps = 0
    for step in range(config.AGENT_MAX_STEPS):
        if time.perf_counter() - started > config.AGENT_MAX_SECONDS:
            break
        decision = _ask_react(state, results, allowed, step)
        if not decision or decision.get("done"):
            break
        name = str(decision.get("tool") or "")
        args = decision.get("args") or {}
        if name not in allowed or not isinstance(args, dict):
            break
        key = (name, json.dumps(args, sort_keys=True))
        if key in used:
            break
        used.add(key)
        seq += 1
        call_started = time.perf_counter()
        status, error, result = "ok", None, None
        try:
            result = tools.call_tool(name, args)
        except Exception as exc:
            status, error = "error", str(exc)
        latency = int((time.perf_counter() - call_started) * 1000)
        _step(run_id, seq, "react_tool", name, args, result, status, latency, error)
        results.append(
            {
                "tool": name, "args": args, "status": status,
                "result": result, "error": error, "latency_ms": latency,
            }
        )
        steps += 1

    seq += 1
    _step(
        run_id, seq, "react", "有界 ReAct 循环",
        {"max_steps": config.AGENT_MAX_STEPS},
        {"extra_steps": steps, "allowed_tools": allowed},
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    return {"tool_results": results, "seq": seq}


def _stages(state: AgentState) -> set[str]:
    skill = state.get("skill") or {}
    stages = skill.get("stages")
    return set(stages) if stages else set(skills.DEFAULT_STAGES)


def _steward_node(state: AgentState) -> AgentState:
    """数据可信度门禁：采集过期时不允许 L3，降级并标注原因（默认关闭）。"""
    run_id = state["run_id"]
    seq = state.get("seq", 0) + 1
    started = time.perf_counter()
    facts = dict(state["facts"])

    freshness: dict[str, Any] | None = None
    for item in state.get("tool_results", []):
        if item["tool"] == "collection_health" and item["status"] == "ok":
            freshness = (item.get("result") or {}).get("freshness") or {}
            break
    stale = bool(freshness.get("stale")) if freshness else True

    downgraded = False
    if (
        os.getenv("LIRA_STEWARD_ENFORCE", "off") == "on"
        and stale
        and facts.get("severity") == "L3"
    ):
        facts["severity"] = "L2"
        facts["downgraded_by_freshness"] = True
        downgraded = True

    _step(
        run_id, seq, "steward", "采集健康门禁",
        {"event_id": state.get("event_id")},
        {"stale": stale, "downgraded": downgraded},
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    if handoff.allowed(run_id):
        seq += 1
        handoff.record(
            run_id, seq,
            handoff.Handoff(
                "steward", "analysis", "facts_ready",
                {"stale": stale, "downgraded": downgraded},
            ),
        )
    return {"facts": facts, "seq": seq}


def _route_after_tools(state: AgentState) -> str:
    return "steward" if "steward" in _stages(state) else "analysis"


def _cases_from_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for item in results:
        if item["tool"] == "search_cases" and item["status"] == "ok" and item["result"]:
            return item["result"].get("cases", [])
    return []


def _docs_from_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for item in results:
        if item["tool"] == "search_docs" and item["status"] == "ok" and item["result"]:
            return item["result"].get("chunks", [])
    return []


def _points_from_facts(facts: dict[str, Any]) -> tuple[PricePoint, PricePoint | None]:
    point = PricePoint(
        target_id=facts["target_id"],
        ts=facts["ts"],
        point=facts["point"],
        price_low=facts["price_low"],
        price_high=facts["price_high"],
        confidence=facts["confidence"],
        missing_fields=facts["missing_fields"],
    )
    prev = None
    if facts.get("prev_point"):
        item = facts["prev_point"]
        prev = PricePoint(
            target_id=facts["target_id"], ts=item["ts"], point=item["point"],
            price_low=item["price_low"], price_high=item["price_high"],
            confidence=item["confidence"], missing_fields=item["missing_fields"],
        )
    return point, prev


def _analysis_payload(result) -> dict[str, Any]:
    return {
        "action": result.action,
        "confidence": result.confidence,
        "narrative": result.narrative,
        "evidence_ids": result.evidence_ids,
        "generated_by": result.generated_by,
    }


def _checks(
    facts: dict[str, Any], analysis: dict[str, Any], allowed: set[str]
) -> dict[str, Any]:
    checks = {
        "evidence_ok": bool(analysis["evidence_ids"])
        and set(analysis["evidence_ids"]).issubset(allowed),
        "action_ok": analysis["action"] in agent.ACTIONS,
        "confidence_ok": 0.0 <= float(analysis["confidence"]) <= 1.0,
        "narrative_ok": bool(str(analysis["narrative"]).strip()),
        "gate_ok": facts["gate_level"] != "observe"
        or analysis["action"] == "no_action",
    }
    checks["ok"] = all(checks.values())
    return checks


def _critic_facts(facts: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "event_type", "severity", "gate_level", "title", "price_low",
        "price_high", "confidence", "missing_fields", "prev_point", "my_price",
    )
    return {key: facts.get(key) for key in keys}


def _analyze_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    seq = state.get("seq", 0) + 1
    started = time.perf_counter()
    facts = state["facts"]
    cases = _cases_from_results(state.get("tool_results", []))
    docs = _docs_from_results(state.get("tool_results", []))
    point, prev = _points_from_facts(facts)

    result = agent.analyze(
        event_type=facts["event_type"],
        severity=facts["severity"],
        gate=facts["gate_level"],
        title=facts["title"],
        point=point,
        prev=prev,
        allowed_evidence=state.get("allowed_evidence", []),
        cases=cases,
        docs=docs,
        skill=state.get("skill"),
    )
    analysis = _analysis_payload(result)
    _step(
        run_id, seq, "analysis", "归因与建议",
        {
            "event_type": facts["event_type"],
            "cases": len(cases),
            "rules": len(docs),
            "skill": (state.get("skill") or {}).get("name"),
        },
        analysis,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    return {"analysis": analysis, "seq": seq}


def _verify_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    seq = state.get("seq", 0) + 1
    started = time.perf_counter()
    facts = state["facts"]
    analysis = state["analysis"]
    cases = _cases_from_results(state.get("tool_results", []))
    docs = _docs_from_results(state.get("tool_results", []))
    allowed = (
        set(state.get("allowed_evidence", []))
        | {f"case:{item['id']}" for item in cases}
        | {f"doc:{item['id']}" for item in docs}
    )
    checks = _checks(facts, analysis, allowed)
    _step(
        run_id, seq, "verify", "校验证据与动作",
        {"action": analysis["action"], "evidence": analysis["evidence_ids"]},
        checks, "ok" if checks["ok"] else "error",
        int((time.perf_counter() - started) * 1000),
        None if checks["ok"] else "verification failed",
    )
    if not checks["ok"]:
        raise ValueError("agent verification failed")

    critic_started = time.perf_counter()
    critic = agent.critic_review(_critic_facts(facts), analysis, sorted(allowed))
    if critic:
        seq += 1
        _step(
            run_id, seq, "critic", "LLM 复核",
            {"action": analysis["action"]},
            critic,
            "ok",
            int((time.perf_counter() - critic_started) * 1000),
        )
        checks["critic_verdict"] = critic["verdict"]
        if critic["verdict"] == "reject":
            point, prev = _points_from_facts(facts)
            fallback = agent.analyze(
                event_type=facts["event_type"],
                severity=facts["severity"],
                gate=facts["gate_level"],
                title=facts["title"],
                point=point,
                prev=prev,
                allowed_evidence=state.get("allowed_evidence", []),
                cases=cases,
                docs=docs,
                skill=state.get("skill"),
                force_template=True,
            )
            fallback_analysis = _analysis_payload(fallback)
            seq += 1
            _step(
                run_id, seq, "fallback", "Critic 驳回后回退模板",
                {"issues": critic["issues"]}, fallback_analysis, "ok", 0,
            )
            fallback_checks = _checks(facts, fallback_analysis, allowed)
            if not fallback_checks["ok"]:
                _step(
                    run_id, seq + 1, "error", "回退后仍不可信", {},
                    fallback_checks, "error", 0, "fallback verification failed",
                )
                raise ValueError("agent verification failed after critic")
            analysis = fallback_analysis
            checks["fallback"] = True
            checks["fallback_checks"] = fallback_checks

    return {"analysis": analysis, "checks": checks, "seq": seq}


def _price_node(state: AgentState) -> AgentState:
    """Pricer Agent：按确定性策略给出目标价，模型不参与定价。"""
    run_id = state["run_id"]
    seq = state.get("seq", 0) + 1
    started = time.perf_counter()
    facts = state["facts"]
    analysis = state["analysis"]

    from . import autopilot

    cfg = autopilot.config()
    point = PricePoint(
        target_id=facts["target_id"], ts=facts["ts"], point=facts["point"],
        price_low=facts["price_low"], price_high=facts["price_high"],
        confidence=facts["confidence"], missing_fields=facts["missing_fields"],
    )
    if analysis["action"] in ("adjust_price", "follow"):
        plan = pricing.propose(
            point, facts.get("my_price"), facts.get("cost"),
            facts.get("margin_floor", 0.15),
            strategy=facts.get("strategy") or cfg["strategy"],
            undercut_pct=cfg["undercut_pct"],
            max_delta_pct=cfg["max_delta_pct"],
        )
    else:
        plan = pricing.propose(
            point, facts.get("my_price"), facts.get("cost"),
            facts.get("margin_floor", 0.15), strategy="hold",
        )
    payload = plan.as_dict()
    _step(
        run_id, seq, "pricing", "调价策略", {"action": analysis["action"]},
        payload, latency_ms=int((time.perf_counter() - started) * 1000),
    )
    out: dict[str, Any] = {"pricing": payload, "seq": seq}
    if plan.action == "hold" and analysis["action"] in ("adjust_price", "follow"):
        out["analysis"] = {**analysis, "action": "hold"}
    return out  # type: ignore[return-value]


def _risk_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    seq = state.get("seq", 0) + 1
    started = time.perf_counter()
    facts = state["facts"]
    analysis = state["analysis"]
    pricing_plan = state.get("pricing") or {}

    target_price = pricing_plan.get("target_price")
    if analysis["action"] in ("follow", "adjust_coupon") and target_price is None:
        target_price = round(facts["point"], 2)
    check = guardrail.evaluate(
        target_price, facts.get("cost"), facts.get("margin_floor", 0.15)
    )
    payload = {
        "target_price": target_price,
        "guardrail": {**check.as_dict(), "status": check.status},
        "floor": check.floor,
    }
    _step(
        run_id, seq, "risk", "毛利与可行性",
        {"action": analysis["action"], "target_price": target_price},
        payload,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    return {"risk": payload, "seq": seq}


def _writer_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    seq = state.get("seq", 0) + 1
    started = time.perf_counter()
    facts = state["facts"]
    analysis = state["analysis"]
    risk_payload = state.get("risk") or {}
    my_price = facts.get("my_price")

    proposal = {
        "action": analysis["action"],
        "narrative": analysis["narrative"],
        "impact_low": (
            round(my_price - facts["price_high"], 2) if my_price is not None else None
        ),
        "impact_high": (
            round(my_price - facts["price_low"], 2) if my_price is not None else None
        ),
        "target_price": risk_payload.get("target_price"),
    }
    _step(
        run_id, seq, "writer", "生成建议文案",
        {"action": analysis["action"]},
        {"impact_low": proposal["impact_low"], "impact_high": proposal["impact_high"]},
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    return {"proposal": proposal, "seq": seq}


def _propose_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    seq = state.get("seq", 0) + 1
    started = time.perf_counter()
    facts = state["facts"]
    analysis = state["analysis"]
    cases = _cases_from_results(state.get("tool_results", []))

    proposal = state.get("proposal") or {}
    risk_payload = state.get("risk") or {}
    check = risk_payload.get("guardrail") or {}
    pricing_plan = state.get("pricing") or {}
    impact_low = proposal.get("impact_low")
    impact_high = proposal.get("impact_high")
    target_price = pricing_plan.get("target_price")
    review_reasons = pricing_plan.get("reasons") or []

    suggestion_id = db.new_id()
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO suggestion (id, event_id, action, impact_low, impact_high,"
            " confidence, gate_level, narrative, generated_by, case_ids,"
            " target_price, margin_at_target, margin_floor, guardrail, guardrail_note,"
            " status, mode, exception, exception_reason, created_at, agent_run_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                suggestion_id, state["event_id"], analysis["action"],
                impact_low, impact_high, analysis["confidence"], facts["gate_level"],
                analysis["narrative"], analysis["generated_by"],
                json.dumps([item["id"] for item in cases], ensure_ascii=False),
                target_price, check.get("margin_at_target"),
                risk_payload.get("floor", facts.get("margin_floor", 0.15)),
                check.get("status", "unknown"), check.get("guardrail_note"),
                "holdout" if facts.get("holdout") else "pending",
                "manual", 1 if review_reasons else 0,
                "；".join(review_reasons)[:500] if review_reasons else None,
                db.now_iso(), run_id,
            ),
        )
        conn.execute(
            "UPDATE event SET evidence = ? WHERE id = ?",
            (json.dumps(analysis["evidence_ids"], ensure_ascii=False), state["event_id"]),
        )
        row = conn.execute(
            "SELECT * FROM suggestion WHERE id = ?", (suggestion_id,)
        ).fetchone()

    suggestion = {**dict(row), "similar_cases": cases}
    memory.remember(
        run_id, memory.SESSION,
        f"{facts.get('title')}｜{facts.get('event_type')}/{facts.get('severity')}"
        f"｜{analysis['action']}｜{analysis['narrative'][:60]}",
        {"event_id": state.get("event_id"), "action": analysis["action"]},
    )
    _step(
        run_id, seq, "suggestion", "写入建议",
        {"action": analysis["action"]},
        {"suggestion_id": suggestion_id, "guardrail": check.get("status", "unknown")},
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    # 建议落库后立即分流：能自动执行的直接执行，异常进待确认队列
    try:
        from . import autopilot

        suggestion["autopilot"] = autopilot.apply(suggestion_id)
    except Exception as exc:  # 自动分流失败不应让整次研判作废
        logging.getLogger(__name__).exception("autopilot failed for %s", suggestion_id)
        suggestion["autopilot"] = {"error": str(exc)}

    return {"suggestion": suggestion, "seq": seq}


def _build_graph():
    if StateGraph is None:
        return None
    graph = StateGraph(AgentState)
    graph.add_node("load", _load_context)
    graph.add_node("planning", _plan_node)
    graph.add_node("tools", _act_node)
    graph.add_node("react", _react_node)
    graph.add_node("steward", _steward_node)
    graph.add_node("analysis", _analyze_node)
    graph.add_node("pricing_agent", _price_node)
    graph.add_node("risk", _risk_node)
    graph.add_node("verification", _verify_node)
    graph.add_node("writer", _writer_node)
    graph.add_node("suggest", _propose_node)
    graph.set_entry_point("load")
    graph.add_edge("load", "planning")
    graph.add_edge("planning", "tools")
    graph.add_edge("tools", "react")
    graph.add_conditional_edges(
        "react", _route_after_tools,
        {"steward": "steward", "analysis": "analysis"},
    )
    graph.add_edge("steward", "analysis")
    graph.add_edge("analysis", "pricing_agent")
    graph.add_edge("pricing_agent", "risk")
    graph.add_edge("risk", "verification")
    graph.add_edge("verification", "writer")
    graph.add_edge("writer", "suggest")
    graph.add_edge("suggest", END)
    return graph.compile()


def _run_without_langgraph(state: AgentState) -> AgentState:
    final = dict(state)
    for node in (_load_context, _plan_node, _act_node, _react_node):
        final.update(node(final))  # type: ignore[arg-type]
    if "steward" in _stages(final):
        final.update(_steward_node(final))  # type: ignore[arg-type]
    for node in (
        _analyze_node, _price_node, _risk_node, _verify_node, _writer_node,
        _propose_node,
    ):
        final.update(node(final))  # type: ignore[arg-type]
    return final  # type: ignore[return-value]


GRAPH = _build_graph()


def run_for_event(event_id: str, trigger: str = "api") -> dict[str, Any]:
    """执行一次完整研判，返回建议；过程写入 agent_run / agent_step。"""
    run_id = _new_run(event_id, trigger)
    tracing.new_trace()
    root_span = tracing.record("agent_run", "run", run_id=run_id,
                               attributes={"trigger": trigger})
    span_token = tracing.set_span(root_span)
    started = time.perf_counter()
    state: AgentState = {
        "event_id": event_id, "run_id": run_id, "trigger": trigger, "seq": 0,
    }
    run_token = metrics.set_run_id(run_id)

    try:
        if GRAPH is not None:
            final = GRAPH.invoke(state)
        else:
            final = _run_without_langgraph(state)

        suggestion = final["suggestion"]
        seq = final.get("seq", 0) + 1
        latency = int((time.perf_counter() - started) * 1000)
        _step(
            run_id, seq, "finalize", "完成", {"status": "succeeded"},
            {"suggestion_id": suggestion["id"]}, latency_ms=0,
        )
        _finish_run(
            run_id, "succeeded", suggestion["id"], latency, None, seq,
            suggestion.get("generated_by"),
        )
        stream.publish(
            "agent",
            {
                "run_id": run_id, "event_id": event_id,
                "status": "succeeded", "suggestion_id": suggestion["id"],
            },
        )
        return suggestion
    except Exception as exc:
        seq = state.get("seq", 0) + 1
        latency = int((time.perf_counter() - started) * 1000)
        try:
            _step(run_id, seq, "error", "运行失败", {}, None, "error", latency, str(exc))
        except Exception:  # pragma: no cover - 落库失败时不再掩盖原始异常
            pass
        try:
            _finish_run(run_id, "failed", None, latency, str(exc), seq)
        except Exception:  # pragma: no cover
            pass
        stream.publish(
            "agent",
            {"run_id": run_id, "event_id": event_id, "status": "failed"},
        )
        raise
    finally:
        tracing.reset_span(span_token)
        metrics.reset_run_id(run_token)
