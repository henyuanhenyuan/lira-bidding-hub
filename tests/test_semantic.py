from app import semantic


def obs(title="竞品A 洗发水 500ml", image="http://img/1.jpg"):
    return {"title": title, "main_image_url": image}


def test_similarity_is_high_for_minor_edit():
    a = "竞品A 洗发水 500ml"
    b = "竞品A 洗发水 500ml 官方"
    assert semantic.similarity(a, b) > 0.6


def test_similarity_is_low_for_rewrite():
    a = "竞品A 洗发水 500ml"
    b = "全新升级 控油蓬松 家庭装"
    assert semantic.similarity(a, b) < 0.4


def test_no_previous_observation_means_no_change():
    assert semantic.detect(None, obs()) == []


def test_identical_snapshot_has_no_change():
    assert semantic.detect(obs(), obs()) == []


def test_title_change_reports_claims():
    prev = obs("竞品A 洗发水 500ml 赠小样")
    cur = obs("竞品A 洗发水 500ml 买一送一")
    changes = semantic.detect(prev, cur)
    assert len(changes) == 1
    ch = changes[0]
    assert ch.field == "title"
    assert "买一送一" in ch.added
    assert "赠小样" in ch.removed
    assert "标题变化" in ch.note


def test_major_rewrite_is_l2():
    prev = obs("竞品A 洗发水 500ml")
    cur = obs("全新升级 控油蓬松 家庭装")
    ch = semantic.detect(prev, cur)[0]
    assert ch.severity == "L2"


def test_image_change_detected():
    prev = obs(image="http://img/1.jpg")
    cur = obs(image="http://img/2.jpg")
    changes = semantic.detect(prev, cur)
    assert [c.field for c in changes] == ["image"]
    assert changes[0].note == "主图已更换"


def test_missing_image_on_one_side_is_ignored():
    prev = obs(image="http://img/1.jpg")
    cur = obs(image="")
    assert semantic.detect(prev, cur) == []


def test_confidence_decreases_with_source_tier():
    assert semantic.confidence_for_tier(0) > semantic.confidence_for_tier(3)
