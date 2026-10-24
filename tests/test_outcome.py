from app import cases, db, outcome

SID = "sugg-1"


def seed_suggestion(status="accepted"):
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO target (id, platform, external_id, title, my_sku, my_price, active)"
            " VALUES ('t1','taobao','t1','竞品A·洗护套装','SKU-A',289,1)"
        )
        conn.execute(
            "INSERT INTO price_point (target_id, ts, price_low, price_high, confidence,"
            " missing_fields, discontinuity) VALUES ('t1','2026-10-24T02:17:00+08:00',"
            " 268,270,0.8,'[]',0)"
        )
        conn.execute(
            "INSERT INTO event (id, target_id, ts, type, severity, gate_level, suppressed,"
            " note, evidence, rule_version) VALUES ('e1','t1','2026-10-24T02:17:00+08:00',"
            " 'price_drop','L2','strong',0,'到手价下降 10%','[]','rules-v1')"
        )
        conn.execute(
            "INSERT INTO suggestion (id, event_id, action, impact_low, impact_high,"
            " confidence, gate_level, narrative, generated_by, case_ids, status, created_at)"
            " VALUES (?, 'e1','hold',1.0,2.0,0.8,'strong','建议先观察','template:v1',"
            "'[]', ?, '2026-10-24T03:00:00+00:00')",
            (SID, status),
        )


def test_accepted_outcome_creates_case():
    seed_suggestion("accepted")
    with db.get_db() as conn:
        r = outcome.record(conn, SID, "improved", "7 日转化提升 1.2pt", 0.1, "qa")
        assert r["case_id"]
        assert cases.count(conn) == 1
        row = conn.execute('SELECT * FROM "case"').fetchone()
    assert row["decision"] == "hold"
    assert "转化提升" in row["outcome_7d"]


def test_rejected_outcome_does_not_create_case():
    seed_suggestion("rejected")
    with db.get_db() as conn:
        r = outcome.record(conn, SID, "unchanged", None, None, "qa")
        assert r["case_id"] is None
        assert cases.count(conn) == 0


def test_outcome_is_upserted():
    seed_suggestion("accepted")
    with db.get_db() as conn:
        outcome.record(conn, SID, "unchanged", None, None, "qa")
        outcome.record(conn, SID, "worse", "价格战", -0.2, "qa2")
        row = outcome.get(conn, SID)
    assert row["result"] == "worse"
    assert row["recorded_by"] == "qa2"


def test_invalid_result_rejected():
    seed_suggestion("accepted")
    with db.get_db() as conn:
        try:
            outcome.record(conn, SID, "great", None, None, "qa")
        except ValueError:
            pass
        else:
            raise AssertionError("should reject invalid result")


def test_overdue_lists_accepted_without_outcome():
    seed_suggestion("accepted")
    with db.get_db() as conn:
        rows = outcome.overdue(conn, days=0)
    assert any(r["id"] == SID for r in rows)
