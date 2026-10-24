import json

import pytest

from app import db, nlq

T = "2026-10-24T02:17:00+08:00"


def seed():
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO target (id, platform, external_id, title, my_sku, my_price,"
            " active) VALUES ('t1','taobao','t1','竞品A·洗护套装','SKU-A',289,1)"
        )
        for i, price in enumerate([299, 269, 249]):
            conn.execute(
                "INSERT INTO price_point (target_id, ts, price_low, price_high,"
                " confidence, missing_fields, discontinuity) VALUES (?,?,?,?,?,?,0)",
                ("t1", f"2026-10-2{i + 3}T02:17:00+08:00", price, price, 0.8, "[]"),
            )
        conn.execute(
            "INSERT INTO event (id,target_id,ts,type,severity,gate_level,suppressed,"
            "note,evidence,rule_version) VALUES ('e1','t1',?,'price_drop','L2',"
            "'strong',0,'到手价估算 269.00','[]','rules-v1')", (T,)
        )
        conn.execute(
            "INSERT INTO event (id,target_id,ts,type,severity,gate_level,suppressed,"
            "note,evidence,rule_version) VALUES ('e2','t1',?,'band_breach','L2',"
            "'strong',0,'击穿我方价格带','[]','rules-v1')", (T,)
        )
        conn.execute(
            "INSERT INTO suggestion (id,event_id,action,confidence,gate_level,narrative,"
            "generated_by,case_ids,guardrail,guardrail_note,target_price,status,created_at)"
            " VALUES ('s1','e1','hold',0.8,'strong','建议观察','template:v1','[]',"
            "'ok','通过',NULL,'pending',?)", (T,)
        )
        conn.execute(
            "INSERT INTO suggestion (id,event_id,action,confidence,gate_level,narrative,"
            "generated_by,case_ids,guardrail,guardrail_note,target_price,status,created_at)"
            " VALUES ('s2','e2','follow',0.8,'strong','建议跟价','template:v1','[]',"
            "'blocked','毛利 1.1% 低于下限',89.0,'pending',?)", (T,)
        )
        conn.execute(
            "INSERT INTO suggestion (id,event_id,action,confidence,gate_level,narrative,"
            "generated_by,case_ids,guardrail,guardrail_note,target_price,executed_price,"
            "status,created_at) VALUES ('s3','e1','hold',0.8,'strong','x','template:v1',"
            "'[]','ok','通过',NULL,280,'executed',?)", (T,)
        )
        conn.execute(
            "INSERT INTO outcome (id,suggestion_id,result,recorded_by,recorded_at)"
            " VALUES ('o1','s3','improved','qa',?)", (T,)
        )
        conn.execute(
            "INSERT INTO review_insight (id,target_id,window_days,generated_at,"
            "review_count,topics,opportunities,summary,generated_by)"
            " VALUES ('ri1','t1',7,?,10,?,'[]','s','template:v1')",
            (T, json.dumps([
                {"name": "物流发货", "count": 5, "share": 0.5,
                 "negative_share": 0.8, "examples": []},
            ], ensure_ascii=False)),
        )


def ask(question):
    with db.get_db() as conn:
        return nlq.ask(conn, question)


def test_template_registry_is_populated():
    info = nlq.templates_info()
    assert len(info) >= 8
    assert all({"id", "title", "params", "examples"} <= set(i) for i in info)


def test_routes_price_drop_question():
    seed()
    r = ask("最近 7 天有哪些降价？")
    assert r["ok"] is True
    assert r["template"] == "price_drops"
    assert r["params"]["days"] == 7
    assert r["rows"]


def test_days_extraction_variants():
    assert nlq._extract_days("最近 30 天", 7) == 30
    assert nlq._extract_days("近 3 日", 7) == 3
    assert nlq._extract_days("今天有什么", 7) == 1
    assert nlq._extract_days("一周内", 7) == 7
    assert nlq._extract_days("最近怎么样", 14) == 14


def test_days_are_clamped():
    assert nlq._extract_days("最近 9999 天", 7) == 180


def test_severity_routing():
    seed()
    r = ask("最近有哪些紧急事件？")
    assert r["ok"] is True
    assert r["template"] == "events_by_severity"
    assert r["params"]["severity"] == "L3"


def test_guardrail_blocked_question():
    seed()
    r = ask("哪些建议被毛利护栏拦截了？")
    assert r["ok"] is True
    assert r["template"] == "guardrail_blocked"
    assert len(r["rows"]) == 1


def test_pending_suggestions_question():
    seed()
    r = ask("现在有哪些待提交的建议？")
    assert r["template"] == "pending_suggestions"
    assert len(r["rows"]) == 2


def test_outcome_summary_question():
    seed()
    r = ask("最近的结果回收怎么样？")
    assert r["template"] == "outcome_summary"
    assert r["rows"][0]["result"] == "improved"


def test_negative_topics_question():
    seed()
    r = ask("竞品评论里最大的问题是什么？")
    assert r["template"] == "negative_topics"
    assert "物流发货" in r["answer"]


def test_price_trend_requires_target():
    seed()
    r = ask("最近的价格走势")
    assert r["ok"] is False
    assert r["reason"] == "missing_param"


def test_price_trend_with_target_name():
    seed()
    r = ask("竞品A 最近的价格走势")
    assert r["ok"] is True
    assert r["template"] == "price_trend"
    assert r["params"]["target"]
    assert "竞品A" in r["answer"]


def test_unknown_question_returns_suggestions():
    r = ask("今天中午吃什么")
    assert r["ok"] is False
    assert r["reason"] == "no_template"
    assert r["suggestions"]


def test_sql_injection_attempt_is_not_executed():
    seed()
    r = ask("降价'; DROP TABLE event; --")
    # 要么走模板但参数被钳制，要么不匹配；无论如何表必须还在
    with db.get_db() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM event").fetchone()["c"] >= 1
    assert "rows" in r


def test_params_never_carry_raw_text_into_enum():
    seed()
    r = ask("的 L3 事件")
    assert r["params"]["severity"] in ("L1", "L2", "L3")
