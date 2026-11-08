"""立ち読み（購入前に無料で見られる画像）を添える投稿のテスト。"""
import random
import sqlite3
from datetime import datetime, timezone

from affiliate_bot import media, ops, patterns, planner, products, replicate as R
from affiliate_bot.compliance import media_rights_ok
from affiliate_bot.config import Settings
from affiliate_bot.db import Database
from affiliate_bot.demo_data import demo_doujin_products, demo_products
from affiliate_bot.dmm_client import parse_item

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=R.TZ)


def test_parse_tachiyomi_and_doujin_image_host():
    p = parse_item({"content_id": "d_1", "title": "T", "prices": {"price": "550"}, "service_code": "doujin",
                    "sampleImageURL": {"sample_l": {"image": ["https://doujin-assets.dmm.co.jp/digital/comic/d_1/d_1jp-001.jpg"]}},
                    "tachiyomi": {"URL": "https://www.dmm.co.jp/dc/doujin/-/tachiyomi/=/cid=d_1/", "affiliateURL": "https://al.fanza.co.jp/?t=1"}}, "FANZA")
    assert p.tachiyomi_affiliate_url == "https://al.fanza.co.jp/?t=1" and p.service == "doujin"
    assert media_rights_ok(p.sample_image_urls[0])
    assert not media_rights_ok("https://dmm.co.jp.evil.example/x.jpg") and not media_rights_ok("http://pics2.dmm.co.jp/x.jpg")


def test_old_database_gets_new_columns(tmp_path):
    path = tmp_path / "old.sqlite3"
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE products (content_id TEXT PRIMARY KEY, site TEXT NOT NULL, title TEXT NOT NULL)")
    c.commit(); c.close()
    db = Database(path)
    cols = {r["name"] for r in db.q("PRAGMA table_info(products)")}
    assert {"tachiyomi_url", "tachiyomi_affiliate_url"} <= cols
    db.close()


def test_tachiyomi_claim_only_when_true():
    sk = "⟦TITLE⟧\n⟦CLAIM:無料で立ち読み⟧\n⟦PRICE⟧\n続きはリプ欄"
    doujin = demo_doujin_products()[0]
    d = {k: getattr(doujin, k) for k in ("content_id", "title", "price", "list_price", "genres", "actresses", "service", "sample_image_urls",
                                         "tachiyomi_url", "release_date", "review_count", "review_avg", "campaign")}
    assert R.render(sk, d, NOW).text == "サンプル同人H 放課後の図書室（全40ページ）\n無料で立ち読み\n550円\n続きはリプ欄\n【PR】"
    video = demo_products()[0]
    v = {k: getattr(video, k) for k in ("content_id", "title", "price", "list_price", "genres", "actresses", "service", "sample_image_urls",
                                        "release_date", "review_count", "review_avg", "campaign")}
    assert R.render(sk, v, NOW).text is None            # 動画のサンプル静止画は「立ち読み」と言わない


def test_preview_images_and_tachiyomi_link_reach_the_package(db, settings):
    patterns.ensure_seed(db)
    products.upsert_products(db, demo_doujin_products() + demo_products()[:1], 0.2)
    products.rescore_all(db)
    R.ensure_seeds(db)
    # この型が調査で最も成果が高かった状況（rebuild と同じく骨格スコアと Pattern の確信度を両方上げる）
    db.exec("UPDATE skeletons SET score=0.99 WHERE category='立ち読み画像型'")
    db.exec("UPDATE patterns SET confidence=0.95, trend_score=1.0 WHERE pattern_id IN (SELECT pattern_id FROM skeletons WHERE category='立ち読み画像型')")
    settings.posts_per_day = 1
    planner.plan_day(db, settings, None, day_jst=datetime(2030, 1, 1, tzinfo=timezone.utc), rng=random.Random(1))
    pk = planner.today_packages(db, settings, "2030-01-01")
    assert len(pk) == 1 and pk[0]["product_id"] == "d_demo901" and "無料で立ち読み" in pk[0]["text"]
    assert len(pk[0]["media_sources"]) == 4 and all("doujin-assets.dmm.co.jp" in u for u in pk[0]["media_sources"])
    assert any("センシティブ" in n for n in pk[0]["notes"]) and any("無料立ち読み" in n for n in pk[0]["notes"])
    body = ops.render_daily_issue(pk, "2030-01-01")
    assert pk[0]["tachiyomi_affiliate_url"] in body and body.count("doujin-assets.dmm.co.jp") == 4
    assert len(media.pick_assets(db, "d_demo901", "image", n=9)) == 4              # X の上限 4 枚


def test_extra_targets_parse():
    s = Settings()
    s.dmm_extra_targets = "doujin:digital_doujin, ebook:comic,bad"
    assert s.dmm_targets() == [(s.dmm_service, s.dmm_floor), ("doujin", "digital_doujin"), ("ebook", "comic")]


def test_type_defining_fact_missing_skips_the_type():
    doujin = demo_doujin_products()[0]
    d = {k: getattr(doujin, k) for k in ("content_id", "title", "price", "list_price", "genres", "actresses", "service", "sample_image_urls",
                                         "release_date", "review_count", "review_avg", "campaign")}
    assert R.render("⟦ACTRESS⟧\n⟦TITLE⟧\n⟦PRICE⟧｜⟦GENRE⟧\nリプ欄から", d, NOW).text is None      # 出演者のいない同人に女優訴求型は使わない
    assert R.render("⟦TITLE⟧\n⟦ACTRESS⟧｜⟦GENRE⟧\n⟦PRICE⟧", d, NOW).text is not None              # 行の一部なら省くだけ
