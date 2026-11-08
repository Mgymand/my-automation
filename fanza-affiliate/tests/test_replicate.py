"""模倣優先モード（既存の勝ち投稿の型を再現）のテスト。"""
import random
from datetime import datetime, timezone

from affiliate_bot import patterns, planner, products, replicate as R, research
from affiliate_bot.db import dumps
from affiliate_bot.demo_data import demo_products
from affiliate_bot.generation import generate_for_product

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=R.TZ)
PROD = {"content_id": "x1", "title": "サンプル作品A 温泉旅館の一夜", "price": 990, "list_price": 1980, "discount_rate": 0.5,
        "genres": ["人妻", "温泉"], "actresses": ["架空 花子"], "review_avg": 4.6, "review_count": 38, "release_date": "2026-11-05",
        "campaign": [{"date_end": "2026-11-12 09:59:59"}]}


def _post(db, pid, author, text, outlier=5.0, created="2026-11-01T13:00:00+00:00", media="photo"):
    db.exec("INSERT INTO research_posts(x_post_id,author_username,author_followers,text,created_at,captured_at,views,views_per_follower,"
            "outlier_score,category,features) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (pid, author, 800, text, created, created, 20000, 25.0, outlier, research.rule_category(research.text_features(text, {}))[0],
             dumps({**research.text_features(text, {"media_types": [media], "image_count": 1 if media == "photo" else 0,
                                                     "has_video": media == "video"}), "length": len(text)})))


def test_skeleton_keeps_form_and_drops_distinctive_wording():
    p = R.prepare("50%OFF｜1,980円→990円\n「温泉旅館の一夜」\n人妻／山田 花子さん\n9/30 23:59まで\nリプ欄から #FANZA #個人タグ https://al.fanza.co.jp/x",
                  [], ["山田 花子"])
    sk = R.skeletonize(p, set())
    assert sk == "⟦DISC⟧｜⟦LIST_PRICE⟧→⟦PRICE⟧\n「⟦TITLE⟧」\n⟦GENRE⟧／⟦ACTRESS⟧さん\n⟦END_DATE⟧ ⟦END_TIME⟧まで\nリプ欄から #FANZA"
    assert p["link_in"] == "body"
    sk2 = R.skeletonize(R.prepare("今日の1本はこれ。後半の展開が想像以上だった。レビュー平均4.8（120件）"), set())
    assert "想像以上" not in sk2 and "今日の一本" in sk2 and "⟦RAVG⟧" in sk2 and "⟦RCOUNT⟧" in sk2


def test_common_phrases_across_three_accounts_are_kept(db):
    for i, a in enumerate(["a1", "a2", "a3"]):
        _post(db, f"c{i}", a, f"神コスパ\n{1000 + i * 10}円→{300 + i}円\n「作品{i}の名前です」\nリプ欄から")
    _post(db, "u1", "solo", "唯一無二の言い回しです\n50%OFF｜1,980円\n「別作品の名前です」")
    res = R.rebuild(db)
    assert res["common_phrases"] >= 1
    sks = {s["skeleton"]: s for s in R.top_skeletons(db, 50) if s["source"] == "research"}
    shared = next(k for k in sks if "神コスパ" in k)
    assert sks[shared]["n_authors"] == 3 and sks[shared]["n_posts"] == 3
    assert not any("唯一無二" in k for k in sks)
    pat = patterns.get_pattern(db, sks[shared]["pattern_id"])
    assert pat and pat["confidence"] > 0.2 and pat["category"]


def test_render_uses_only_facts_and_never_fabricates():
    ok = R.render("⟦DISC⟧｜⟦LIST_PRICE⟧→⟦PRICE⟧\n⟦TITLE⟧\n⟦GENRE⟧／⟦ACTRESS⟧\n⟦END_DATE⟧ ⟦END_TIME⟧まで", PROD, NOW)
    assert ok.text == "50%OFF｜1,980円→990円\nサンプル作品A 温泉旅館の一夜\n人妻／架空 花子\n11/12 9:59まで\n【PR】"
    no_campaign = dict(PROD, campaign=[])
    assert R.render("⟦TITLE⟧\n⟦END_DATE⟧まで", no_campaign, NOW).text is None                        # 期限を作らない
    assert R.render("⟦CLAIM:半額⟧ ⟦TITLE⟧", dict(PROD, discount_rate=0.3), NOW).text is None          # 30% を半額と言わない
    assert R.render("⟦CLAIM:最安値⟧ ⟦TITLE⟧", PROD, NOW).text is None                                 # 確かめられない主張は使わない
    assert R.render("⟦CLAIM:新作⟧ ⟦TITLE⟧", dict(PROD, release_date="2025-01-01"), NOW).text is None   # 古い作品を新作と言わない
    assert R.render("⟦RANK⟧ ⟦TITLE⟧", PROD, NOW).text is None                                          # 順位を作らない
    soft = R.render("⟦ACTRESS⟧｜⟦TITLE⟧｜⟦GENRE⟧", dict(PROD, actresses=[]), NOW)
    assert soft.text.startswith("サンプル作品A") and "｜人妻" in soft.text                               # 出演者なしは自然に省く
    free = R.render("⟦FREE:20⟧⟦GENRE⟧？\n⟦TITLE⟧\n⟦FREE:12⟧", PROD, NOW)
    assert free.text == "人妻の一本。\nサンプル作品A 温泉旅館の一夜\n【PR】"                                  # 固有表現の行は再現しない


def test_too_similar_to_source_is_rejected(db):
    # 元投稿と同じ商品・同じ数字だと、埋めた結果が元投稿とほぼ同文になる → 使わない
    src = "50%OFF｜990円\nサンプル作品A 温泉旅館の一夜\n人妻／架空 花子\n詳細はリプ欄"
    for i, a in enumerate(["a1", "a2", "a3"]):
        _post(db, f"s{i}", a, src, outlier=9.0)
    R.rebuild(db)
    top = R.top_skeletons(db, 1)[0]
    assert top["source"] == "research"
    cands = R.candidates_for(db, None, PROD, [], k=5, now=NOW)
    assert top["pattern_id"] not in {c["pattern_id"] for c in cands}
    assert cands and all(c["source_similarity"] < R.MAX_SOURCE_SIMILARITY for c in cands)


def test_low_fidelity_posts_are_not_treated_as_reproducible(db):
    _post(db, "f1", "a1", "これ本当に温泉旅館の話？\n後半の展開が想像以上だった\n「作品の名前です」", outlier=50.0)
    R.rebuild(db)
    assert not [s for s in R.top_skeletons(db, 50) if s["source"] == "research"]


def _seed_plan(db, settings):
    patterns.ensure_seed(db)
    products.upsert_products(db, demo_products("FANZA"), 0.2)
    products.rescore_all(db)


def test_strict_mode_plans_replicas_and_link_note_follows_source(db, settings):
    _seed_plan(db, settings)
    for i, a in enumerate(["a1", "a2", "a3", "a4"]):        # 本文末リンクで伸びている型
        _post(db, f"b{i}", a, f"{50 + i}%OFF\n「作品{i}の名前です」\nhttps://al.fanza.co.jp/?x={i}", outlier=20.0)
    R.rebuild(db)
    settings.replication_mode = "strict"
    planner.plan_day(db, settings, None, day_jst=datetime(2030, 1, 1, tzinfo=timezone.utc), rng=random.Random(5))
    pk = planner.today_packages(db, settings, "2030-01-01")
    assert pk and all(p["angle"].startswith("R:") for p in pk)
    body_link = [p for p in pk if R.skeleton_for_pattern(db, p["pattern_id"])["link_in"] == "body"]
    assert body_link and all(any("本文の最後" in n for n in p["notes"]) for p in body_link)
    assert all("再現元の型" in p["reason"] for p in pk)


def test_mode_off_uses_only_own_angles(db, settings):
    _seed_plan(db, settings)
    prod = products.top_candidates(db, limit=1)[0]
    ids = generate_for_product(db, None, prod, [], mode="off")
    angles = {db.one("SELECT angle FROM candidates WHERE id=?", (i,))["angle"] for i in ids}
    assert angles == {"A_short", "B_actress", "C_situation", "D_review", "E_price"}
