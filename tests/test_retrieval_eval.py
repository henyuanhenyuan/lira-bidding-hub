import pytest

from app import cases, db

QUERIES = [
    ("大促前降价并上了店铺券", "竞品在大促前 48 小时把套装降到 269 元"),
    ("直降清库存", "竞品洗发水从 199 直降 149"),
    ("护发素击穿价格带", "竞品护发素长期维持 89 元"),
    ("直播专享价 跨店满减", "精华液降价 15% 并叠加跨店满减"),
    ("提价并更换主图 成分升级", "面膜提价 12%"),
]


@pytest.fixture()
def seeded():
    with db.get_db() as conn:
        cases.seed(conn)
        rows = conn.execute('SELECT id, summary FROM "case"').fetchall()
    return {row["summary"]: row["id"] for row in rows}


@pytest.mark.parametrize("query,expected_prefix", QUERIES)
def test_seed_retrieval_hits_expected_case(seeded, query, expected_prefix):
    expected = next(
        cid for summary, cid in seeded.items() if summary.startswith(expected_prefix)
    )
    with db.get_db() as conn:
        found = cases.search(
            conn, query=query, category=None, event_type=None,
            price_band=None, limit=3,
        )
    assert expected in [case.id for case in found]
