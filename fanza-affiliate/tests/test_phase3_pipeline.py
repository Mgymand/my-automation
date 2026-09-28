"""統合テスト: research → fetch-products → plan → posted → metrics → conversions → learn → report → weekly。"""
import json
import random
from datetime import datetime, timedelta, timezone

from affiliate_bot import bandit, media, metrics, packages, patterns, planner, posted, products, reports, research
from affiliate_bot.demo_data import DEMO_RESEARCH_CSV, demo_products
from affiliate_bot.dmm_client import parse_item
from affiliate_bot.generation import generate_for_product
from affiliate_bot.llm import FakeLLMClient, LLMRouter
from affiliate_bot.x_client import DryRunXClient


def _seed(db, settings):
    patterns.ensure_seed(db)
    products.upsert_products(db, demo_products("FANZA"), 0.2)
    products.rescore_all(db)
    research.import_csv(db, DEMO_RESEARCH_CSV)


def test_parse_item_and_media_registry(db):
    item = {"content_id": "abc00123", "title": "T", "URL": "u", "affiliateURL": "a",
            "imageURL": {"large": "https://pics.dmm.co.jp/x/l.jpg"},
            "sampleImageURL": {"sample_l": {"image": ["https://pics.dmm.co.jp/x/1.jpg", "https://evil.example.com/2.jpg"]}},
            "sampleMovieURL": {"size_720_480": "https://cc3001.dmm.co.jp/litevideo/x.mp4"},
            "prices": {"price": "300~", "list_price": "1,980"}, "date": "2026-09-01 10:00:00",
            "review": {"count": "12", "average": "4.5"}, "iteminfo": {"genre": [{"name": "G1"}], "actress": [{"name": "A"}]}}
    p = parse_item(item, "FANZA")
    assert p.is_adult and p.sample_movie_url.endswith(".mp4")
    products.upsert_products(db, [p], 0.2)
    n = media.register_official_assets(db, dict(db.one("SELECT * FROM products WHERE content_id='abc00123'")))
    assert n == 3   # 1 sample image (DMM), 1 movie, 1 package。他ドメインは登録されない
    assert all(a["rights_status"] == "ok" for a in media.assets_for(db, "abc00123"))
    assert media.pick_asset(db, "abc00123", prefer="video")["media_kind"] == "video"


def test_ai_card_rules(db):
    media.register_ai_card(db, "p1", "file:///card.png", "title_card", "タイトルカード")
    try:
        media.register_ai_card(db, "p1", "file:///fake.png", "actress_photo")
        assert False
    except ValueError:
        pass


def test_research_features_ratios_and_classification(db):
    n = research.import_csv(db, DEMO_RESEARCH_CSV)
    assert n == 6
    rows = research.top_outliers(db, 10)
    assert rows[0]["x_post_id"] == "1001" and rows[0]["category"] == "意外性フック型"
    assert rows[0]["views_per_follower"] > 100 and rows[0]["engagement_rate"] > 0
    f = json.loads(rows[0]["features"])
    assert f["lines"] == 3 and f["cta"] and f["has_video"] and f["video_seconds"] == 45
    cats = {r["category"] for r in rows}
    assert {"問いかけ型", "ランキング型", "数字型", "新作訴求型"} <= cats
    # 大規模アカウントの平凡な投稿は外れ値スコアが低い
    big = next(r for r in rows if r["x_post_id"] == "1005")
    assert big["outlier_score"] < rows[0]["outlier_score"] / 5
    res = research.analyze(db, None)
    assert res["analyzed"] == 6 and "意外性フック型" in res["by_category"]
    pat = db.one("SELECT trend_score, last_seen FROM patterns WHERE pattern_id='P13_surprise'")
    assert pat is None or pat["trend_score"] is not None
    patterns.ensure_seed(db)
    research.analyze(db, None)
    assert db.one("SELECT trend_score FROM patterns WHERE pattern_id='P13_surprise'")["trend_score"] > 0
    sim = research.similar_success(db, "意外性フック型")
    assert sim["x_post_id"] == "1001" and "倍" in sim["reason"]


def test_eav_not_simple_ranking(db, settings):
    _seed(db, settings)
    top = products.top_candidates(db, limit=10)
    assert [t["content_id"] for t in top] != sorted([t["content_id"] for t in top], key=lambda c: db.one("SELECT rank_position r FROM products WHERE content_id=?", (c,))["r"])
    c = top[0]["eav_components"]
    for k in ("p_views", "p_ctr", "p_cvr", "payout_jpy", "competition", "novelty", "discount_strength", "actress_momentum", "genre_momentum", "pattern_compat"):
        assert k in c


def test_generation_five_angles_and_similarity(db, settings):
    _seed(db, settings)
    prod = products.top_candidates(db, limit=1)[0]
    ids = generate_for_product(db, None, prod, recent_texts=["サンプル作品G シリーズ第3弾。企画・シリーズ。【PR】"])
    rows = [dict(db.one("SELECT * FROM candidates WHERE id=?", (i,))) for i in ids]
    assert {r["angle"] for r in rows} == {"A_short", "B_actress", "C_situation", "D_review", "E_price"}
    assert all(r["source_pattern_id"] and "PR" in r["text"] for r in rows)
    short = next(r for r in rows if r["angle"] == "A_short")
    assert short["rewrite_count"] >= 1 and short["similarity_score"] < 0.8   # 既存投稿と同文 → 書き直し


def test_generation_with_fake_llm(db, settings):
    _seed(db, settings)
    prod = products.top_candidates(db, limit=1)[0]
    fake = FakeLLMClient([json.dumps({"candidates": [
        {"angle": a, "text": f"{a} 用の本文です {prod['title']}【PR】", "hook_type": "h"} for a in ("A_short", "B_actress", "C_situation", "D_review", "E_price")]})])
    settings.anthropic_api_key = "x"
    llm = LLMRouter(settings, db, client=fake)
    ids = generate_for_product(db, llm, prod, [])
    assert len(ids) == 5 and db.one("SELECT model FROM candidates WHERE id=?", (ids[0],))["model"] == settings.model_sonnet
    assert db.one("SELECT SUM(amount_jpy) s FROM costs WHERE kind='ai'")["s"] > 0


def test_plan_creates_packages_with_all_fields(db, settings):
    _seed(db, settings)
    ids = planner.plan_day(db, settings, None, day_jst=datetime(2030, 1, 1, tzinfo=timezone.utc), rng=random.Random(1))
    assert len(ids) == settings.posts_per_day
    pk = planner.today_packages(db, settings, "2030-01-01")
    assert [p["seq"] for p in pk] == [1, 2, 3, 4]
    times = [p["scheduled_at"] for p in pk]
    assert times == sorted(times)
    for p in pk:
        assert p["status"] == "planned" and "PR" in p["text"] and p["media_source"] and p["reason"] and p["notes"]
        assert p["predicted"]["views"] > 0 and p["affiliate_url"] and p["similar_post_id"]
        assert any("投稿者本人の判断" in n for n in p["notes"])
    assert len({p["product_id"] for p in pk}) == len(pk)
    assert len({p["angle"] for p in pk}) >= 2
    txt = packages.render_day_text(pk, ["動画比率を維持"])
    for k in ("推奨投稿時刻", "商品名", "女優", "Affiliate URL", "使用Pattern", "この商品を選んだ理由", "投稿本文", "使用推奨素材", "素材の権利状態", "期待値", "類似成功投稿", "投稿時の注意", "本日の調整"):
        assert k in txt
    html = packages.render_day_html(pk, "2030-01-01")
    assert "copyText" in html and "POST 1" in html
    d = packages.export_day(pk, "2030-01-01", settings.data_dir / "exports")
    assert (d / "index.html").exists() and (d / "post1.txt").exists() and (d / "posts.txt").exists()
    # 再 plan で planned は置き換わる
    planner.plan_day(db, settings, None, day_jst=datetime(2030, 1, 1, tzinfo=timezone.utc), rng=random.Random(2))
    assert db.one("SELECT COUNT(*) c FROM posts WHERE day='2030-01-01'")["c"] == settings.posts_per_day


def test_manual_posting_flow_and_attribution(db, settings):
    _seed(db, settings)
    planner.plan_day(db, settings, None, day_jst=datetime(2030, 1, 1, tzinfo=timezone.utc), rng=random.Random(3))
    r1 = posted.register(db, settings, "https://x.com/me/status/1970000000000000001", seq=1, day="2030-01-01")
    assert r1["x_post_id"] == "1970000000000000001" and r1["seq"] == 1
    r2 = posted.register(db, settings, "1970000000000000002", seq=2, day="2030-01-01", actual_text="変えた本文【PR】", actual_media="photo")
    assert r2["actual_text"] == "変えた本文【PR】"
    try:
        posted.register(db, settings, "1970000000000000001", seq=3, day="2030-01-01")
        assert False
    except ValueError:
        pass
    posted.skip(db, "2030-01-01", 4, "時間なし")
    st = {r["status"]: r["c"] for r in db.q("SELECT status, COUNT(*) c FROM posts WHERE day='2030-01-01' GROUP BY status")}
    assert st == {"posted": 2, "planned": 1, "skipped": 1}
    # 指標: 手入力 + CSV
    metrics.ingest_manual_metrics(db, r1["post_id"], 12000, 80, 9, 3, 20)
    assert metrics.ingest_metrics_csv(db, f"x_post_id,views,likes,reposts,replies,bookmarks,milestone_hours\n{r2['x_post_id']},3000,10,1,0,4,24\n") == 1
    assert metrics.latest_metrics(db, r2["post_id"])["views"] == 3000
    # 成果 CSV: 商品一致 × 時間窓 → high、同日別窓 → low、商品不明 → unattributed
    p1 = db.one("SELECT product_id, posted_at FROM posts WHERE post_id=?", (r1["post_id"],))
    ts = datetime.fromisoformat(p1["posted_at"]) + timedelta(hours=5)
    csv = ("日時,商品ID,報酬,注文ID\n"
           f"{ts.strftime('%Y-%m-%d %H:%M:%S')},{p1['product_id']},250,o1\n"
           f"{ts.strftime('%Y-%m-%d %H:%M:%S')},{p1['product_id']},250,o1\n"
           f"{ts.strftime('%Y-%m-%d %H:%M:%S')},unknown-cid,100,o2\n")
    assert metrics.ingest_conversions_csv(db, settings, csv) == 2
    rows = db.q("SELECT post_id, attribution, attribution_confidence, attribution_share FROM conversions ORDER BY id")
    assert rows[0]["post_id"] == r1["post_id"] and rows[0]["attribution_confidence"] == "high" and rows[0]["attribution_share"] == 1.0
    assert rows[1]["post_id"] is None and rows[1]["attribution"] == "unattributed"


def test_attribution_split_and_product_day(db, settings):
    _seed(db, settings)
    conv_ts = datetime(2030, 1, 5, 2, 0, tzinfo=timezone.utc)   # 成果 CSV は日付粒度（早朝）のことがある
    # demo001 は窓内に 2 件（按分）、demo002 は同日だが成果時刻より後（窓外）→ product_day
    for i, (pid, delta_h) in enumerate([("demo001", -10), ("demo001", -30), ("demo002", +10)], 1):
        db.exec("INSERT INTO posts(day,seq,account,product_id,pattern_id,text,scheduled_at,status,posted_at,x_post_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                ("2030-01-05", i, "m", pid, "P01_actress", "t【PR】", conv_ts.isoformat(), "posted", (conv_ts + timedelta(hours=delta_h)).isoformat(timespec="seconds"), f"x{i}", conv_ts.isoformat()))
        metrics.ingest_manual_metrics(db, i, 1000 * i)
    res = metrics.attribute(db, "demo001", conv_ts, 72)
    assert len(res) == 2 and all(r[2] == "medium" for r in res) and abs(sum(r[3] for r in res) - 1.0) < 1e-6
    assert max(res, key=lambda r: r[3])[0] == 2        # views が多い投稿に多く按分
    res = metrics.attribute(db, "demo002", conv_ts, 72)
    assert res[0][1] == "product_day" and res[0][2] == "low"


def test_learn_blends_signals_and_updates_patterns(db, settings):
    _seed(db, settings)
    planner.plan_day(db, settings, None, day_jst=datetime(2030, 1, 1, tzinfo=timezone.utc), rng=random.Random(4))
    now = datetime.now(timezone.utc)
    for i, r in enumerate(db.q("SELECT post_id FROM posts"), 1):
        db.exec("UPDATE posts SET status='posted', posted_at=?, x_post_id=? WHERE post_id=?", ((now - timedelta(days=2)).isoformat(timespec="seconds"), f"x{i}", r["post_id"]))
        metrics.ingest_manual_metrics(db, r["post_id"], 2000 * i, 20 * i, 2, 1, 5, url_clicks=10 * i)
    db.exec("INSERT INTO conversions(ts,post_id,product_id,revenue_jpy,source,attribution,attribution_confidence,attribution_share,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (now.isoformat(), 1, "demo003", 300, "dmm_csv", "product_window", "high", 1.0, now.isoformat()))
    n = metrics.learn(db)
    assert n == settings.posts_per_day and metrics.learn(db) == 0
    assert float(db.get_setting("conv_weight")) < 0.5      # CV 1 件では売上重みは小さい
    arms = bandit.get_arms(db, "pattern")
    assert sum(v[2] for v in arms.values()) == settings.posts_per_day
    pat = db.one("SELECT * FROM patterns WHERE uses>0 AND avg_views>0")
    assert pat["engagement_rate"] > 0 and pat["confidence"] > 0.2


def test_daily_and_weekly_reports(db, settings):
    _seed(db, settings)
    planner.plan_day(db, settings, None, rng=random.Random(5))
    md = reports.daily_report(db, settings, None)
    for k in ("今日の投稿", "POST 1", "昨日", "売上", "最良投稿", "最低投稿", "CTR 推定", "EPC", "投稿あたり利益",
              "昨日分かったこと", "今日増やすもの", "今日減らすもの", "新しく試すもの", "投稿セット", "本日の調整"):
        assert k in md
    assert "週次レビュー" in reports.weekly_review(db, settings, None)
    assert "7 日未満" in reports.weekly_review(db, settings, None)


def test_suggest_posts_per_day_needs_history(db, settings):
    n, why = planner.suggest_posts_per_day(db, 5)
    assert n == 5 and "7 日未満" in why


def test_decay_and_trend(db):
    patterns.ensure_seed(db)
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat(timespec="seconds")
    db.exec("UPDATE patterns SET last_used_at=?, created_at=? WHERE pattern_id='P01_actress'", (old, old))
    assert "P01_actress" in patterns.decay_stale(db)
    patterns.update_trend(db, "女優訴求型", 0.8)
    assert db.one("SELECT trend_score FROM patterns WHERE pattern_id='P01_actress'")["trend_score"] == 0.8


def test_dry_run_x_client_and_milestones(db, settings):
    _seed(db, settings)
    settings.metric_milestones_hours = (24, 72)
    now = datetime.now(timezone.utc)
    db.exec("INSERT INTO posts(day,seq,account,product_id,pattern_id,text,scheduled_at,status,posted_at,x_post_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            ("2030-01-05", 1, "m", "demo001", "P01_actress", "t【PR】", now.isoformat(), "posted", (now - timedelta(hours=30)).isoformat(timespec="seconds"), "x1", now.isoformat()))
    due = metrics.due_milestones(db, settings.metric_milestones_hours, now)
    assert due == [(1, "x1", 24)]

    class FakeX(DryRunXClient):
        def posts(self, ids, owned=False):
            return [{"x_post_id": "x1", "views": 500, "likes": 5, "reposts": 1, "replies": 0, "quotes": 0, "bookmarks": 2}], 0.001
    assert metrics.ingest_x_metrics(db, settings, FakeX(), now) == 1
    assert metrics.due_milestones(db, settings.metric_milestones_hours, now) == []
    assert db.one("SELECT milestone_hours, source FROM post_metrics")["milestone_hours"] == 24


def test_slot_reason_recorded_and_research_prior(db, settings):
    _seed(db, settings)
    prior = planner.research_slot_prior(db, settings.timezone)
    assert prior == {}                      # 調査 6 件では事前分布を作らない（データ不足）
    planner.plan_day(db, settings, None, day_jst=datetime(2030, 1, 1, tzinfo=timezone.utc), rng=random.Random(9))
    pk = planner.today_packages(db, settings, "2030-01-01")
    assert all(any(n.startswith("時間帯 ") and "選択" in n for n in p["notes"]) for p in pk)
    # 調査データが十分なら JST 時刻分布からボーナスが付く
    for i in range(12):
        db.exec("INSERT INTO research_posts(x_post_id,author_followers,text,created_at,captured_at,views,views_per_follower,outlier_score,category,features) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)", (f"r{i}", 500, "t", f"2026-09-2{i % 8}T13:00:00+00:00", "2026-09-28T00:00:00+00:00", 10000, 20, 5.0, "短文型", "{}"))
    prior = planner.research_slot_prior(db, settings.timezone)
    assert prior.get("21-24") == 1.0        # 13:00 UTC = 22:00 JST


def test_new_pattern_types_and_research_rules(db, settings):
    patterns.ensure_seed(db)
    ids = {r["pattern_id"] for r in db.q("SELECT pattern_id FROM patterns")}
    assert {"P16_sale_alert", "P17_bargain", "P18_roundup", "P19_persona"} <= ids
    f = research.text_features("50%OFF｜300円→150円\n人妻ドラマの一本\n9/30 23:59まで\nリプ欄から", {})
    assert research.rule_category(f)[0] == "セール速報型" and f["deadline"] and f["cta_position"] == "tail"
    f = research.text_features("100円で買える。\nタイトル\nジャンル", {})
    assert research.rule_category(f)[0] == "激安・価格訴求型"
    f = research.text_features("今週のFANZA、安い順に5本\n1. …\n2. …", {})
    assert research.rule_category(f)[0] == "まとめ型"
    f = research.text_features("おはよう。今日の1本はこれ。\n理由は…", {})
    assert research.rule_category(f)[0] == "キャラクター人格型"
    assert len(research.DEFAULT_QUERIES) >= 8


def test_launch_posts_use_only_facts(db, settings):
    from affiliate_bot import launch
    _seed(db, settings)
    posts = launch.build_launch_posts(db, settings)
    assert len(posts) == 10 and len({p["key"] for p in posts}) == 10
    assert all("PR" in p["text"] for p in posts)
    for p in posts:
        if p["product_id"]:
            prod = db.one("SELECT price, discount_rate FROM products WHERE content_id=?", (p["product_id"],))
            if "OFF" in p["text"] and p["key"] == "sale_alert":
                assert float(prod["discount_rate"]) >= 0.3
    keys = {p["key"]: p for p in posts}
    assert keys["video"]["media"] and keys["video"]["media"].endswith(".mp4")
    assert "10円" not in keys["bargain"]["text"]          # 捏造しない（demo に 10円商品は無い）
    d = launch.export_launch(db, settings, settings.data_dir / "exports")
    assert (d / "launch.md").exists() and (d / "post01_intro.txt").exists()
    md = (d / "launch.md").read_text(encoding="utf-8")
    assert launch.ACCOUNT["name"] in md and "アイコン生成プロンプト" in md


def test_default_slot_prior_used_without_research(db, settings):
    patterns.ensure_seed(db)
    products.upsert_products(db, demo_products("FANZA"), 0.2)
    products.rescore_all(db)
    planner.plan_day(db, settings, None, day_jst=datetime(2030, 1, 1, tzinfo=timezone.utc), rng=random.Random(11))
    pk = planner.today_packages(db, settings, "2030-01-01")
    assert all(any("既定重み" in n for n in p["notes"]) for p in pk)
