from app import skills


def test_text_playbook_is_accepted_as_legacy():
    result = skills.validate_playbook("先看采集健康度，再检索案例")
    assert result["valid"] is True
    assert result["format"] == "text"


def test_structured_sop_validates():
    import json

    sop = {
        "name": "降价应对",
        "steps": [
            {"action": "check_freshness", "criteria": "滞后 < 6h",
             "tools": ["collection_health"]},
            {"action": "search", "criteria": "至少 3 条证据",
             "tools": ["search_cases", "search_docs"]},
        ],
    }
    result = skills.validate_playbook(json.dumps(sop, ensure_ascii=False))
    assert result["valid"] is True
    assert result["steps"] == 2


def test_structured_sop_rejects_unknown_tool():
    import json

    sop = {"steps": [{"action": "x", "criteria": "y", "tools": ["delete_price"]}]}
    result = skills.validate_playbook(json.dumps(sop))
    assert result["valid"] is False
    assert any("未知工具" in item for item in result["errors"])


def test_empty_playbook_invalid():
    assert skills.validate_playbook("")["valid"] is False
