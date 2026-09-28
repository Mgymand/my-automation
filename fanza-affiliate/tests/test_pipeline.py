import random
from datetime import datetime, timedelta, timezone

from affiliate_bot import bandit, failsafe, metrics, patterns, products, reports, scheduler
from affiliate_bot.demo_data import demo_products
from affiliate_bot.dmm_client import parse_item
from affiliate_bot.publisher import publish_due
from affiliate_bot.similarity import jaccard
from affiliate_bot.x_client import DryRunXClient, OAuth1


def _seed(db, settings, site="DMM.com"):
    patterns.ensure_seed(db)
    products.upsert_products(db, demo_products(site), 0.2)
    products.rescore_all(db)


def test_parse_item_normalizes():
    item = {
        "content_id": "abc00123", "title": "T", "URL": "u", "affiliateURL": "a",
        "imageURL": {"large": "https://pics.dmm.co.jp/x/l.jpg", "small": "s"},
        "sampleImageURL": {"sample_s": {"image": ["s1", "s2"]}, "sample_l": {"image": ["l1"]}},
        "sampleMovieURL": {"size_476_306": "m476", "size_720_480": "m720"},
        "prices": {"price": "300~", "list_price": "1,980"},
        "date": "2026-09-01 10:00:00",
        "review": {"count": "12", "average": "4.5"},
        "iteminfo": {"genre": [{"id": 1, "name": "G1"}], "actress": [{"id": 2, "name": "A"}], "maker": [{"name": "M"}]},
    }
    p = parse_item(item, "FANZA")
    assert p.price == 300 and p.list_price == 1980 and p.discount_rate > 0.8
    assert p.sample_image_urls == ["l1"] and p.sample_movie_url == "m720"
    assert p.genres == ["G1"] and p.actresses == ["A"] and p.is_adult


def test_erpi_prefers_discount_and_reviews(db, settings):
    _seed(db, settings)
    top = products.top_candidates(db, limit=10)
    assert top and all(t["erpi"] >= 0 for t in top)
    ids = [t["content_id"] for t in top]
    assert ids.index("demo003") < ids.index("demo005")   # 高レビュー・割引・動画あり > 低価格のみ


def test_plan_and_publish_dry_run(db, settings):
    _seed(db, settings)
    rng = random.Random(1)
    day = datetime(2030, 1, 1, tzinfo=timezone.utc)   # 未来日で「過ぎた枠」ロジックを避ける
    ids = scheduler.plan_day(db, settings, None, day_jst=day, rng=rng)
    assert len(ids) == settings.posts_per_day
    rows = db.q("SELECT * FROM posts WHERE status='scheduled' ORDER BY scheduled_at")
    times = [datetime.fromisoformat(r["scheduled_at"]) for r in rows]
    for a, b in zip(times, times[1:]):
        assert (b - a) >= timedelta(minutes=settings.min_post_interval_min)
    assert len({r["product_id"] for r in rows}) == len(rows)
    assert all("PR" in r["text"] for r in rows)
    assert all(r["tracking_code"] for r in rows)
    x = DryRunXClient()
    done = publish_due(db, settings, x, now=datetime(2030, 1, 3, tzinfo=timezone.utc))
    assert done == [rows[0]["post_id"]]     # 最低投稿間隔で 1 件のみ
    ops = [c["op"] for c in x.calls]
    assert ops == ["upload_media", "create_post", "create_post"]
    assert x.calls[1]["paid_partnership"] is True
    assert "https://t.example.com/r/" in x.calls[2]["text"]
    post = db.one("SELECT * FROM posts WHERE post_id=?", (done[0],))
    assert post["status"] == "posted" and post["api_cost_jpy"] > 0


def test_adult_products_blocked_without_ack(db, settings):
    _seed(db, settings, site="FANZA")
    ids = scheduler.plan_day(db, settings, None, day_jst=datetime(2030, 1, 1, tzinfo=timezone.utc), rng=random.Random(2))
    assert ids == []
    assert db.one("SELECT COUNT(*) c FROM candidates WHERE status='human_review'")["c"] == 0  # 商品段階で除外
    assert db.one("SELECT 1 FROM events WHERE code='plan_short'")


def test_similarity_rewrite(db, settings):
    _seed(db, settings)
    assert jaccard("今日の新作はこちら【PR】", "今日の新作はこちら！【PR】") > 0.55
    assert jaccard("温泉旅館の一夜", "オフィスの午後") < 0.2


def test_learn_updates_bandit_and_patterns(db, settings):
    _seed(db, settings)
    scheduler.plan_day(db, settings, None, day_jst=datetime(2030, 1, 1, tzinfo=timezone.utc), rng=random.Random(3))
    now = datetime.now(timezone.utc)
    for r in db.q("SELECT post_id, tracking_code FROM posts"):
        db.exec("UPDATE posts SET status='posted', posted_at=?, x_post_id=? WHERE post_id=?",
                ((now - timedelta(days=2)).isoformat(timespec='seconds'), f"x{r['post_id']}", r["post_id"]))
        db.exec("INSERT INTO post_metrics(post_id,captured_at,views,url_clicks) VALUES(?,?,?,?)", (r["post_id"], now.isoformat(), 2000, 20))
        for _ in range(5):
            db.exec("INSERT INTO clicks(tracking_code,ts) VALUES(?,?)", (r["tracking_code"], (now - timedelta(hours=30)).isoformat(timespec='seconds')))
    n = metrics.learn(db)
    assert n == settings.posts_per_day
    assert metrics.learn(db) == 0   # 二重学習しない
    arms = bandit.get_arms(db, "pattern")
    assert sum(v[2] for v in arms.values()) == settings.posts_per_day
    pat = db.one("SELECT * FROM patterns WHERE uses>0")
    assert pat["avg_views"] == 2000 and abs(pat["avg_ctr"] - 0.01) < 1e-9


def test_conversion_attribution(db, settings):
    _seed(db, settings)
    scheduler.plan_day(db, settings, None, day_jst=datetime(2030, 1, 1, tzinfo=timezone.utc), rng=random.Random(4))
    post = db.one("SELECT * FROM posts LIMIT 1")
    ts = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
    db.exec("INSERT INTO clicks(tracking_code,ts) VALUES(?,?)", (post["tracking_code"], (ts - timedelta(hours=2)).isoformat(timespec='seconds')))
    csv = f"日時,商品ID,報酬,注文ID\n2026-09-27 12:00:00,{post['product_id']},250,o1\n2026-09-27 12:00:00,{post['product_id']},250,o1\n"
    assert metrics.ingest_conversions_csv(db, settings, csv) == 1  # 注文ID 重複は無視
    cv = db.one("SELECT * FROM conversions")
    assert cv["post_id"] == post["post_id"] and cv["attribution"] == "last_click"


def test_failsafe_halts_on_duplicates_and_tracking(db, settings):
    _seed(db, settings)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for i in range(2):
        db.exec("INSERT INTO posts(account,product_id,pattern_id,text,scheduled_at,status,created_at) VALUES('m','demo001','P01','same text',?,'scheduled',?)", (now, now))
    reasons = failsafe.run_checks(db, settings)
    assert any("重複" in r for r in reasons)
    assert failsafe.is_paused(db)[0]
    assert publish_due(db, settings, DryRunXClient()) == []
    failsafe.resume(db)
    assert not failsafe.is_paused(db)[0]


def test_daily_report_contains_required_header(db, settings):
    _seed(db, settings)
    md = reports.daily_report(db, settings, None)
    for k in ("昨日売上", "昨日利益", "クリック数", "CV数", "CTR", "CVR", "最優秀Pattern", "最優秀商品", "AI/APIコスト",
              "昨日わかったこと", "本日継続する施策", "本日停止する施策", "本日の新規テスト", "本日の投稿予定"):
        assert k in md


def test_weekly_review_only_every_7_days(db, settings):
    _seed(db, settings)
    md1 = reports.weekly_review(db, settings, None)
    assert "週次レビュー" in md1
    md2 = reports.weekly_review(db, settings, None)
    assert "7 日未満" in md2


def test_pattern_decay(db, settings):
    patterns.ensure_seed(db)
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat(timespec="seconds")
    db.exec("UPDATE patterns SET last_used_at=?, created_at=? WHERE pattern_id='P01_actress'", (old, old))
    changed = patterns.decay_stale(db)
    assert "P01_actress" in changed
    assert db.one("SELECT confidence FROM patterns WHERE pattern_id='P01_actress'")["confidence"] < 0.2


def test_oauth1_signature_is_stable_format():
    h = OAuth1("ck", "cs", "at", "ats").header("POST", "https://api.x.com/2/tweets")
    assert h.startswith("OAuth ") and 'oauth_signature="' in h and 'oauth_consumer_key="ck"' in h


def test_llm_router_cost_ledger(db, settings):
    from affiliate_bot.llm import FakeLLMClient, LLMRouter, LLMUnavailable
    fake = FakeLLMClient(['{"candidates":[{"angle":"content","text":"本文【PR】","hook_type":"h"}]}'])
    r = LLMRouter(settings, db, client=fake)
    res = r.call("sonnet", "sys", "user", schema={"type": "object"})
    assert res.parsed["candidates"][0]["text"] == "本文【PR】"
    assert fake.calls[0]["model"] == settings.model_sonnet
    assert fake.calls[0]["output_config"]["effort"] == "low"
    assert db.one("SELECT SUM(amount_jpy) s FROM costs WHERE kind='ai'")["s"] > 0
    # Fable は beta + fallbacks
    r.call("fable", "sys", "user")
    assert fake.calls[1]["betas"] == ["server-side-fallback-2026-07-01"] and fake.calls[1]["fallbacks"] == "default"
    # 予算超過
    settings.daily_ai_budget_jpy = 0.0001
    try:
        r.call("sonnet", "sys", "user")
        assert False
    except LLMUnavailable:
        pass
    # refusal
    r2 = LLMRouter(settings, db, client=FakeLLMClient(["x"], stop_reason="refusal"))
    settings.daily_ai_budget_jpy = 1000
    try:
        r2.call("opus", "s", "u")
        assert False
    except LLMUnavailable:
        pass
