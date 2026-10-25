from fastapi.testclient import TestClient

from app import db, skills
from app.main import app

client = TestClient(app)


def test_seed_and_pick_by_event_type():
    with db.get_db() as conn:
        skills.ensure_seeded(conn)
        assert skills.pick_skill(conn, "price_drop", "L3")["id"] == "price_war"
        assert skills.pick_skill(conn, "price_rise", "L1")["id"] == "price_war"
        assert skills.pick_skill(conn, "band_breach", "L1")["id"] == "band_breach"
        assert skills.pick_skill(conn, "title_change", "L2")["id"] == "default"


def test_builtin_skills_declare_stages():
    with db.get_db() as conn:
        listing = skills.list_skills(conn)
    price_war = next(item for item in listing if item["id"] == "price_war")
    assert price_war["stages"] == list(skills.DEFAULT_STAGES)


def test_unknown_stage_rejected():
    with db.get_db() as conn:
        skills.ensure_seeded(conn)
        try:
            skills.create_skill(
                conn, name="坏剧本", playbook="x", event_types=[],
                allowed_tools=[], stages=["bogus"],
            )
        except ValueError as exc:
            assert "bogus" in str(exc)
        else:
            raise AssertionError("unknown stage accepted")


def test_disabled_skill_falls_back_to_default():
    with db.get_db() as conn:
        skills.ensure_seeded(conn)
        skills.update_skill(conn, "price_war", {"enabled": False})
        assert skills.pick_skill(conn, "price_drop", "L3")["id"] == "default"


def test_api_skill_crud():
    listing = client.get("/api/skills").json()
    assert len(listing) >= 3

    created = client.post(
        "/api/skills",
        json={
            "name": "测试剧本",
            "playbook": "先观察，再取证。",
            "event_types": ["title_change"],
            "allowed_tools": ["price_history", "search_docs"],
        },
    )
    assert created.status_code == 200, created.text
    skill = created.json()
    assert skill["version"] == 1

    patched = client.patch(f"/api/skills/{skill['id']}", json={"enabled": False})
    assert patched.status_code == 200
    assert patched.json()["enabled"] == 0
    assert patched.json()["version"] == 2


def test_api_rejects_unknown_stage():
    created = client.post(
        "/api/skills",
        json={
            "name": "阶段校验", "playbook": "x", "event_types": [],
            "allowed_tools": [], "stages": ["nope"],
        },
    )
    assert created.status_code == 400


def test_api_patch_stages():
    created = client.post(
        "/api/skills",
        json={
            "name": "自定义阶段", "playbook": "x", "event_types": [],
            "allowed_tools": [], "stages": ["planning", "tools", "analyst"],
        },
    )
    assert created.status_code == 200, created.text
    skill = created.json()
    assert skill["stages"] == ["planning", "tools", "analyst"]
    patched = client.patch(
        f"/api/skills/{skill['id']}",
        json={"stages": ["planning", "tools", "analyst", "writer"]},
    )
    assert patched.status_code == 200
    assert patched.json()["stages"][-1] == "writer"

    invalid = client.post(
        "/api/skills",
        json={
            "name": "坏剧本",
            "playbook": "x",
            "event_types": [],
            "allowed_tools": ["drop_database"],
        },
    )
    assert invalid.status_code == 400


def test_skill_restricts_plan_tools():
    from app import agent_graph

    plan = agent_graph._deterministic_plan(
        {
            "point": 199.0,
            "prev_point": {"point": 299.0},
            "title": "竞品A",
            "note": "降价",
            "event_type": "price_drop",
            "target_id": "t1",
            "my_price": 100,
            "price_low": 197.0,
            "price_high": 201.0,
            "confidence": 0.9,
        }
    )
    restricted = {"price_history", "simulate_price"}
    filtered = [item for item in plan if item["tool"] in restricted]
    assert [item["tool"] for item in filtered] == ["price_history", "simulate_price"]
