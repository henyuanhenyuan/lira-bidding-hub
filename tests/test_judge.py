import json

from app.evaluation import judge as judge_mod
from app.evaluation import metrics


def _fake_ask(verdict):
    def ask(prompt: str) -> str:
        return json.dumps(
            {"faithfulness": 5 if verdict == "pass" else 2,
             "relevance": 5 if verdict == "pass" else 2,
             "rationale": "ok"}
        )

    return ask


def test_judge_returns_verdict_and_caches():
    calls = {"n": 0}

    def ask(prompt: str) -> str:
        calls["n"] += 1
        return json.dumps({"faithfulness": 5, "relevance": 5, "rationale": "ok"})

    judge = judge_mod.Judge(ask=ask, model="fake")
    first = judge.evaluate("问题", ["上下文"], "回答")
    second = judge.evaluate("问题", ["上下文"], "回答")
    assert first is not None and second is not None
    assert first.label == "pass"
    assert calls["n"] == 1  # 第二次命中缓存


def test_judge_fail_label():
    judge = judge_mod.Judge(ask=_fake_ask("fail"), model="fake")
    verdict = judge.evaluate("问题", ["上下文"], "回答")
    assert verdict is not None
    assert verdict.label == "fail"


def test_judge_handles_bad_json():
    judge = judge_mod.Judge(ask=lambda prompt: "not json", model="fake")
    assert judge.evaluate("q", ["c"], "a") is None


def test_cohen_kappa_used_for_calibration():
    human = ["pass"] * 6 + ["fail"] * 6
    predicted = list(human)
    assert metrics.cohen_kappa(human, predicted) == 1.0
    predicted = ["pass"] * 12
    assert metrics.cohen_kappa(human, predicted) == 0.0


def test_is_calibrated_without_report():
    assert judge_mod.load_calibration() is None or isinstance(
        judge_mod.load_calibration(), dict
    )
    # 仓库里没有提交校准报告时，默认视为未校准
    if judge_mod.load_calibration() is None:
        assert judge_mod.is_calibrated() is False


def test_calibration_file_roundtrip(tmp_path):
    path = tmp_path / "cal.json"
    path.write_text(
        json.dumps({"passed": True, "cohen_kappa": 0.82}), encoding="utf-8"
    )
    assert judge_mod.is_calibrated(path=path) is True
    path.write_text(json.dumps({"passed": False, "cohen_kappa": 0.4}), encoding="utf-8")
    assert judge_mod.is_calibrated(path=path) is False
