"""主力の価格帯（既定 500〜1000 円の人気作）を中心に選ぶテスト。"""
import random
from datetime import datetime, timezone

from affiliate_bot import patterns, planner, products
from affiliate_bot.demo_data import demo_doujin_products, demo_products


def _setup(db, settings, prices: dict[str, tuple[float, int, int]]):
    patterns.ensure_seed(db)
    products.upsert_products(db, demo_products("FANZA") + demo_doujin_products(), 0.2)
    for cid, (price, rank, rc) in prices.items():
        db.exec("UPDATE products SET price=?, list_price=?, discount_rate=0, rank_position=?, review_count=?, review_avg=4.3 WHERE content_id=?",
                (price, price, rank, rc, cid))
    products.rescore_all(db)


def test_tiers_and_popularity(settings):
    s = settings
    assert products.price_tier({"price": 800, "rank_position": 12}, s) == 0          # 価格帯内・ランキング上位
    assert products.price_tier({"price": 800, "rank_position": 1500, "review_count": 40, "review_avg": 4.2}, s) == 0   # レビューで人気
    assert products.price_tier({"price": 800, "rank_position": 1500, "review_count": 3}, s) == 1
    assert products.price_tier({"price": 300}, s) == 2 and products.price_tier({"price": 2480}, s) == 3 and products.price_tier({}, s) == 3


def test_plan_fills_main_share_with_popular_500_to_1000(db, settings):
    # 価格帯より高い作品ほど EAV（予測収益）が高くなる状況でも、主力の価格帯で 7 割以上を埋める
    _setup(db, settings, {"demo001": (300, 1500, 2), "demo002": (980, 3, 80), "demo003": (750, 8, 120), "demo004": (2980, 1, 400),
                          "demo005": (550, 40, 60), "demo006": (1980, 2, 300), "demo007": (880, 1500, 1), "d_demo901": (3500, 5, 500)})
    settings.posts_per_day = 5
    planner.plan_day(db, settings, None, day_jst=datetime(2030, 1, 1, tzinfo=timezone.utc), rng=random.Random(2))
    pk = planner.today_packages(db, settings, "2030-01-01")
    picked = {p["product_id"]: p for p in pk}
    in_band = [cid for cid in picked if 500 <= picked[cid]["price"] <= 1000]
    assert len(pk) == 5 and len(in_band) >= 4                                          # ceil(5 × 0.7) = 4
    assert {"demo002", "demo003", "demo005"} <= set(picked)                             # 価格帯内の人気作は全部入る
    assert all("主力" in picked[c]["reason"] for c in in_band)
    assert "demo001" in picked                                                          # 残り枠は安い作品（可）が先
    assert not {"demo004", "demo006", "d_demo901"} & set(picked)                       # 価格帯より高い作品は候補不足時だけ
