from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass

import httpx

from . import assertions, config, context as context_builder, evidence, llm as llm_gateway, metrics, tracing
from .safety import injection as injection_guard
from .contracts import PricePoint

log = logging.getLogger(__name__)

ACTIONS = ("follow", "hold", "adjust_coupon", "join_promo", "no_action", "adjust_price")

ACTION_TEXT = {
    "follow": "考虑跟进调价（需运营确认毛利护栏）",
    "hold": "建议先观察，不立即跟随",
    "adjust_coupon": "可考虑投放店铺券而非直接降价",
    "join_promo": "可考虑报名同类活动对冲",
    "no_action": "数据不足以支撑动作，保持现状",
    "adjust_price": "按策略自主调价（毛利护栏内自动执行）",
}

PROMPT = """你是电商定价分析助手。只根据给定事实写解释，不得编造。
严格输出一个 JSON 对象，不要输出任何其他文字。
字段：
- action: 必须从 [hold, adjust_coupon, join_promo, no_action, adjust_price] 中选一个
- confidence: 0 到 1 的小数
- evidence_ids: 从 allowed_evidence_ids 中逐字复制，至少 1 条
- narrative: 不超过 60 字的中文说明
如果 facts 里有 rules，可以引用其中的 doc:<id>，但只能复制 allowed_evidence_ids 里的 ID。
示例：
{"action":"hold","confidence":0.72,"evidence_ids":["snap:abc"],"narrative":"竞品到手价小幅下降，建议先观察两日。"}
"""

CRITIC_PROMPT = """你是审稿人，只检查建议是否被事实和证据支持，不重写建议。
输出 JSON：{"verdict":"approve|reject","issues":["..."]}。
检查项：
1. narrative 里的数字必须能在 facts 中找到；
2. evidence_ids 必须全部在 allowed_evidence_ids 里；
3. action 必须与 gate_level 一致（observe 只能是 no_action）；
4. 不得把常识当事实。
只输出 JSON，不要输出其他文字。
"""

CRITIC_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["approve", "reject"]},
        "issues": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["verdict", "issues"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["hold", "adjust_coupon", "join_promo", "no_action", "adjust_price"],
        },
        "confidence": {"type": "number"},
        "evidence_ids": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "narrative": {"type": "string"},
    },
    "required": ["action", "confidence", "evidence_ids", "narrative"],
}


@dataclass
class Analysis:
    action: str
    confidence: float
    narrative: str
    evidence_ids: list[str]
    generated_by: str


def _decide_action(event_type: str, severity: str, gate: str) -> str:
    """确定性动作策略：模型只写解释，动作与目标价都由这里决定。"""
    if gate == "observe":
        return "no_action"
    if event_type == "price_drop":
        return "adjust_price" if severity == "L3" else "hold"
    if event_type == "price_rise":
        return "hold"
    if event_type == "band_breach":
        return "adjust_price"
    return "no_action"


def _template(
    event_type: str,
    severity: str,
    gate: str,
    title: str,
    point: PricePoint,
    prev: PricePoint | None,
    allowed: set[str],
    cases: list[dict] | None = None,
    docs: list[dict] | None = None,
) -> Analysis:
    action = _decide_action(event_type, severity, gate)
    parts = [
        f"{title} 到手价估算 {point.price_low:.2f}–{point.price_high:.2f} 元",
        f"置信度 {point.confidence:.0%}",
    ]
    if prev:
        delta = (point.point - prev.point) / prev.point if prev.point else 0.0
        parts.append(f"较上次 {delta:+.1%}")
    if point.missing_fields:
        parts.append(f"缺失字段：{','.join(point.missing_fields)}")
    if cases:
        top = cases[0]
        parts.append(f"历史相似案例：{top['attribution'][:40]}")
    if docs:
        top_doc = docs[0]
        parts.append(f"参考规则「{top_doc.get('doc_title') or '规则文档'}」")
    parts.append(f"建议：{ACTION_TEXT[action]}")
    narrative = "；".join(parts)

    conf = evidence.confidence_ceiling(len(allowed), point.confidence)
    return Analysis(
        action=action,
        confidence=round(conf, 3),
        narrative=narrative,
        evidence_ids=sorted(allowed),
        generated_by="template:v1",
    )


def _llm_available() -> bool:
    if config.LLM_ENABLED == "off":
        return False
    if config.LLM_ENABLED == "on":
        return True
    if llm_gateway.gateway_enabled() and config.OPENAI_BASE_URL and config.OPENAI_API_KEY:
        return True
    try:
        r = httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=1.0)
        return r.status_code == 200
    except Exception:
        return False



def _context_json(facts: dict, allowed: set[str]) -> str:
    """统一入口：分层裁剪 + 不可信标记，并把预算结果写进 trace。"""
    payload, stats = context_builder.build_analysis_payload(
        facts, allowed, config.LLM_MAX_PROMPT_TOKENS
    )
    tracing.record("context.build", kind="context", attributes=stats)
    return json.dumps(payload, ensure_ascii=False)


def _extract_json(raw: str) -> dict | None:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lstrip().startswith("json"):
            raw = raw.lstrip()[4:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


def _post_chat(body: dict) -> dict:
    url = f"{config.OLLAMA_URL}/api/chat"
    r = httpx.post(url, json=body, timeout=config.LLM_TIMEOUT_S)
    if r.status_code == 400 and "think" in body:
        # 老版本 Ollama 不认识 think 参数
        body = {k: v for k, v in body.items() if k != "think"}
        r = httpx.post(url, json=body, timeout=config.LLM_TIMEOUT_S)
    if r.status_code == 400 and isinstance(body.get("format"), dict):
        # 不支持 JSON Schema 的版本，降级为 json 模式
        body = {**body, "format": "json"}
        r = httpx.post(url, json=body, timeout=config.LLM_TIMEOUT_S)
    if r.status_code >= 500:  # 偶发 500（模型加载/显存抖动）重试一次
        r = httpx.post(url, json=body, timeout=config.LLM_TIMEOUT_S)
    r.raise_for_status()
    return r.json()


def _call_gateway(facts: dict, allowed: set[str]) -> Analysis | None:
    """走多 Provider 网关；校验规则与直连路径完全一致。"""
    started = time.perf_counter()
    response = llm_gateway.complete(
        [
            {"role": "system", "content": PROMPT},
            {
                "role": "user",
                "content": _context_json(facts, allowed),
            },
        ],
        kind="attribution",
        prompt_name="analysis",
        schema=OUTPUT_SCHEMA,
        max_tokens=200,
        temperature=0.1,
    )
    if response is None:
        return None
    data = _extract_json(response.text)
    if data is None:
        metrics.record(
            "attribution", model=response.model, ok=False, fallback=True,
            latency_ms=int((time.perf_counter() - started) * 1000),
            detail="gateway: no parsable JSON", provider=response.provider,
            prompt_name="analysis",
        )
        return None
    action = data.get("action")
    ids = data.get("evidence_ids") or []
    if action not in ACTIONS or not isinstance(ids, list):
        return None
    check = evidence.validate([str(i) for i in ids], allowed)
    if not check.ok:
        return None
    violations = assertions.verify(
        str(data.get("narrative", "")), allowed=assertions.facts_to_numbers(facts)
    )
    if violations:
        return None
    conf = evidence.confidence_ceiling(
        len(check.valid), max(0.0, min(1.0, float(data.get("confidence", 0.5))))
    )
    return Analysis(
        action=action,
        confidence=round(conf, 3),
        narrative=str(data.get("narrative", ""))[:200],
        evidence_ids=check.valid,
        generated_by=f"llm:{response.model}",
    )


def _call_llm(
    facts: dict,
    allowed: set[str],
) -> Analysis | None:
    body = {
        "model": config.OLLAMA_MODEL,
        "stream": False,
        "think": False,  # qwen3 等思考型模型：不关掉会把 token 全花在 thinking 上
        "format": OUTPUT_SCHEMA,
        "options": {
            "temperature": 0.1,
            "num_predict": 200,
            "repeat_penalty": 1.15,  # 小模型在 JSON 模式下容易陷入重复直到被中止
        },
        "messages": [
            {"role": "system", "content": PROMPT},
            {
                "role": "user",
                "content": _context_json(facts, allowed),
            },
        ],
    }
    if metrics.budget_exceeded():
        metrics.record(
            "attribution", model=config.OLLAMA_MODEL, ok=False, fallback=True,
            detail="token budget exceeded",
        )
        return None

    if llm_gateway.gateway_enabled():
        return _call_gateway(facts, allowed)

    started = time.perf_counter()
    prompt_tokens = 0
    completion_tokens = 0
    try:
        payload = _post_chat(body)
        prompt_tokens = int(payload.get("prompt_eval_count") or 0)
        completion_tokens = int(payload.get("eval_count") or 0)
        msg = payload.get("message", {})
        data = _extract_json(msg.get("content") or "") or _extract_json(
            msg.get("thinking") or ""
        )
        if data is None:
            raise ValueError("no parsable JSON in response")
    except Exception as exc:  # 超时、不可用、坏 JSON —— 一律回退
        log.warning("llm unavailable, fallback to template: %s", exc)
        metrics.record(
            "attribution", model=config.OLLAMA_MODEL, ok=False, fallback=True,
            latency_ms=int((time.perf_counter() - started) * 1000), detail=str(exc),
        )
        return None

    action = data.get("action")
    ids = data.get("evidence_ids") or []
    if action not in ACTIONS or not isinstance(ids, list):
        return None

    check = evidence.validate([str(i) for i in ids], allowed)
    if not check.ok:  # 证据闭包不通过 → 整条作废
        log.warning("evidence closure rejected: %s", check.invalid)
        metrics.record(
            "attribution", model=config.OLLAMA_MODEL, ok=False, fallback=True,
            latency_ms=int((time.perf_counter() - started) * 1000),
            detail="evidence rejected",
        )
        return None

    violations = assertions.verify(
        str(data.get("narrative", "")),
        allowed=assertions.facts_to_numbers(facts),
    )
    if violations:
        log.warning("numeric assertion rejected: %s", [v.raw for v in violations])
        metrics.record(
            "attribution", model=config.OLLAMA_MODEL, ok=False, fallback=True,
            latency_ms=int((time.perf_counter() - started) * 1000),
            detail=f"numeric rejected: {','.join(v.raw for v in violations)[:120]}",
        )
        return None

    conf = float(data.get("confidence", 0.5))
    conf = max(0.0, min(1.0, conf))
    conf = evidence.confidence_ceiling(len(check.valid), conf)

    metrics.record(
        "attribution", model=config.OLLAMA_MODEL, ok=True,
        latency_ms=int((time.perf_counter() - started) * 1000),
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
    )

    return Analysis(
        action=action,
        confidence=round(conf, 3),
        narrative=str(data.get("narrative", ""))[:200],
        evidence_ids=check.valid,
        generated_by=f"llm:{config.OLLAMA_MODEL}",
    )


def call_with_tools(question: str, tool_schemas: list[dict]) -> dict | None:
    """可选：让模型选择工具。失败时返回 None，由确定性计划兜底。"""
    if not _llm_available():
        return None
    if metrics.budget_exceeded():
        metrics.record(
            "planner", model=config.OLLAMA_MODEL, ok=False, fallback=True,
            detail="token budget exceeded",
        )
        return None
    body = {
        "model": config.OLLAMA_MODEL,
        "stream": False,
        "think": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是电商竞品分析助手。只从给定工具里选择必要的最少工具，"
                    "参数必须来自问题中的事实，不要编造。"
                ),
            },
            {"role": "user", "content": question},
        ],
        "tools": tool_schemas,
        "options": {"temperature": 0.1, "num_predict": 250},
    }
    started = time.perf_counter()
    try:
        payload = _post_chat(body)
        metrics.record(
            "planner", model=config.OLLAMA_MODEL, ok=True,
            latency_ms=int((time.perf_counter() - started) * 1000),
            prompt_tokens=int(payload.get("prompt_eval_count") or 0),
            completion_tokens=int(payload.get("eval_count") or 0),
        )
        return payload
    except Exception as exc:
        log.warning("tool planner unavailable, fallback to deterministic: %s", exc)
        metrics.record(
            "planner", model=config.OLLAMA_MODEL, ok=False, fallback=True,
            latency_ms=int((time.perf_counter() - started) * 1000), detail=str(exc),
        )
        return None


def parse_tool_calls(payload: dict | None, allowed: set[str], limit: int = 5) -> list[dict]:
    calls = ((payload or {}).get("message") or {}).get("tool_calls") or []
    plan: list[dict] = []
    seen: set[str] = set()
    for call in calls:
        fn = (call or {}).get("function") or {}
        name = fn.get("name")
        if not isinstance(name, str) or name not in allowed or name in seen:
            continue
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                continue
        if not isinstance(args, dict):
            continue
        seen.add(name)
        plan.append({"tool": name, "args": args, "reason": "llm"})
        if len(plan) >= limit:
            break
    return plan


def analyze(
    *,
    event_type: str,
    severity: str,
    gate: str,
    title: str,
    point: PricePoint,
    prev: PricePoint | None,
    allowed_evidence: list[str],
    cases: list[dict] | None = None,
    docs: list[dict] | None = None,
    skill: dict | None = None,
    force_template: bool = False,
) -> Analysis:
    cases = cases or []
    docs = docs or []
    allowed = (
        set(allowed_evidence)
        | {f"case:{c['id']}" for c in cases}
        | {f"doc:{d['id']}" for d in docs}
    )
    facts = {
        "event_type": event_type,
        "severity": severity,
        "gate_level": gate,
        "title": title,
        "price_low": point.price_low,
        "price_high": point.price_high,
        "point": point.point,
        "confidence": point.confidence,
        "missing_fields": point.missing_fields,
        "prev_point": prev.point if prev else None,
        "delta_pct": (
            (point.point - prev.point) / prev.point
            if prev and prev.point
            else None
        ),
        "prev_ts": prev.ts if prev else None,
        "similar_cases": [
            {
                "id": f"case:{c['id']}",
                "summary": c["summary"],
                "attribution": c["attribution"],
                "outcome": c.get("outcome_7d"),
            }
            for c in cases
        ],
        "rules": [
            {
                "id": f"doc:{d['id']}",
                "title": d.get("doc_title"),
                "chunk_no": d.get("chunk_no"),
                "content": injection_guard.wrap_untrusted(
                    str(d.get("content") or ""), source=f"doc:{d['id']}"
                ),
                "injection": injection_guard.scan(str(d.get("content") or "")).hits,
            }
            for d in docs
        ],
        "skill": (
            {"name": skill.get("name"), "playbook": skill.get("playbook")}
            if skill
            else None
        ),
    }

    if force_template:
        pass
    elif _llm_available():
        result = _call_llm(facts, allowed)
        if result and result.narrative:
            # 决策永远由确定性策略给出，模型只负责解释与措辞
            result.action = _decide_action(event_type, severity, gate)
            return result
    else:
        metrics.record(
            "attribution", model=config.OLLAMA_MODEL, ok=False, fallback=True,
            detail="model unavailable",
        )

    return _template(
        event_type, severity, gate, title, point, prev, allowed, cases, docs
    )


def critic_review(
    facts: dict, analysis: dict, allowed: list[str]
) -> dict | None:
    """可选的 LLM 审稿。默认关闭；失败时返回 None，不阻塞主流程。"""
    if os.getenv("LIRA_AGENT_LLM_CRITIC", "off") != "on":
        return None
    if not _llm_available():
        return None
    if metrics.budget_exceeded():
        metrics.record(
            "critic", model=config.OLLAMA_MODEL, ok=False, fallback=True,
            detail="token budget exceeded",
        )
        return None
    if llm_gateway.gateway_enabled():
        response = llm_gateway.complete(
            [
                {"role": "system", "content": CRITIC_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"facts": facts, "analysis": analysis,
                         "allowed_evidence_ids": allowed},
                        ensure_ascii=False,
                    ),
                },
            ],
            kind="critic",
            prompt_name="critic",
            schema=CRITIC_SCHEMA,
            max_tokens=160,
        )
        if response is None:
            return None
        data = _extract_json(response.text)
        if not data or data.get("verdict") not in ("approve", "reject"):
            return None
        issues = [str(item)[:120] for item in (data.get("issues") or [])][:5]
        return {"verdict": data["verdict"], "issues": issues}
    body = {
        "model": config.OLLAMA_MODEL,
        "stream": False,
        "think": False,
        "format": CRITIC_SCHEMA,
        "options": {"temperature": 0.0, "num_predict": 160},
        "messages": [
            {"role": "system", "content": CRITIC_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "facts": facts,
                        "analysis": analysis,
                        "allowed_evidence_ids": allowed,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }
    started = time.perf_counter()
    try:
        payload = _post_chat(body)
        message = payload.get("message", {})
        data = _extract_json(message.get("content") or "")
        if not data or data.get("verdict") not in ("approve", "reject"):
            return None
        issues = [str(item)[:120] for item in (data.get("issues") or [])][:5]
        metrics.record(
            "critic", model=config.OLLAMA_MODEL, ok=True,
            latency_ms=int((time.perf_counter() - started) * 1000),
            detail=data["verdict"],
            prompt_tokens=int(payload.get("prompt_eval_count") or 0),
            completion_tokens=int(payload.get("eval_count") or 0),
        )
        return {"verdict": data["verdict"], "issues": issues}
    except Exception as exc:
        log.warning("llm critic unavailable: %s", exc)
        metrics.record(
            "critic", model=config.OLLAMA_MODEL, ok=False, fallback=True,
            latency_ms=int((time.perf_counter() - started) * 1000), detail=str(exc),
        )
        return None
