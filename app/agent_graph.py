from __future__ import annotations

import json
import os
import time
from typing import Any, TypedDict

from . import (
    agent, cases as case_store, config, db, guardrail, metrics, skills, stream, tools,
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
    analysis: dict[str, Any]
    checks: dict[str, Any]
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
            "holdout": bool(target["holdout"]) if target else False,
            "cost": product["cost"] if product else None,
            "margin_floor": (
                product["margin_floor"]
                if product and product["margin_floor"] is not None
                else 0.15
            ),
        }
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
    return {"tool_results": results, "seq": seq}


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


def _propose_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    seq = state.get("seq", 0) + 1
    started = time.perf_counter()
    facts = state["facts"]
    analysis = state["analysis"]
    cases = _cases_from_results(state.get("tool_results", []))

    my_price = facts.get("my_price")
    impact_low = (
        round(my_price - facts["price_high"], 2) if my_price is not None else None
    )
    impact_high = (
        round(my_price - facts["price_low"], 2) if my_price is not None else None
    )
    target_price = (
        round(facts["point"], 2)
        if analysis["action"] in ("follow", "adjust_coupon")
        else None
    )
    check = guardrail.evaluate(
        target_price, facts.get("cost"), facts.get("margin_floor", 0.15)
    )

    suggestion_id = db.new_id()
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO suggestion (id, event_id, action, impact_low, impact_high,"
            " confidence, gate_level, narrative, generated_by, case_ids,"
            " target_price, margin_at_target, margin_floor, guardrail, guardrail_note,"
            " status, created_at, agent_run_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                suggestion_id, state["event_id"], analysis["action"],
                impact_low, impact_high, analysis["confidence"], facts["gate_level"],
                analysis["narrative"], analysis["generated_by"],
                json.dumps([item["id"] for item in cases], ensure_ascii=False),
                target_price, check.as_dict()["margin_at_target"], check.floor,
                check.status, check.note,
                "holdout" if facts.get("holdout") else "pending",
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
    _step(
        run_id, seq, "suggestion", "写入建议",
        {"action": analysis["action"]},
        {"suggestion_id": suggestion_id, "guardrail": check.status},
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    return {"suggestion": suggestion, "seq": seq}


def _build_graph():
    if StateGraph is None:
        return None
    graph = StateGraph(AgentState)
    graph.add_node("load", _load_context)
    graph.add_node("planning", _plan_node)
    graph.add_node("tools", _act_node)
    graph.add_node("analysis", _analyze_node)
    graph.add_node("verification", _verify_node)
    graph.add_node("suggest", _propose_node)
    graph.set_entry_point("load")
    graph.add_edge("load", "planning")
    graph.add_edge("planning", "tools")
    graph.add_edge("tools", "analysis")
    graph.add_edge("analysis", "verification")
    graph.add_edge("verification", "suggest")
    graph.add_edge("suggest", END)
    return graph.compile()


GRAPH = _build_graph()
_NODES = (
    _load_context, _plan_node, _act_node, _analyze_node, _verify_node, _propose_node,
)


def run_for_event(event_id: str, trigger: str = "api") -> dict[str, Any]:
    """执行一次完整研判，返回建议；过程写入 agent_run / agent_step。"""
    run_id = _new_run(event_id, trigger)
    started = time.perf_counter()
    state: AgentState = {
        "event_id": event_id, "run_id": run_id, "trigger": trigger, "seq": 0,
    }
    run_token = metrics.set_run_id(run_id)

    try:
        if GRAPH is not None:
            final = GRAPH.invoke(state)
        else:
            final = dict(state)
            for node in _NODES:
                final.update(node(final))  # type: ignore[arg-type]

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
        metrics.reset_run_id(run_token)
