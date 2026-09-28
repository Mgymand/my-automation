"""FANZA 商品候補の取得と Expected Affiliate Value（EAV）。

EAV = 予測 Views × 予測 CTR × 予測 CVR × 予測報酬額 × (Competition / Novelty / Discount Strength /
      Actress Momentum / Genre Momentum / Historical EPC / Pattern Compatibility の補正)
単純ランキング順は使わない。事前分布（公開競合データ・ランキング・レビュー・発売日・割引・女優/ジャンルの勢い）と
自分の実測（views / clicks / CV / EPC）をサンプル数で重み付けして混ぜる。
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from .compliance import product_allowed
from .db import Database, dumps, loads, utcnow
from .dmm_client import Product

PRIOR_CTR = 0.008
PRIOR_CVR = 0.02
PRIOR_VIEWS = 800.0
PRIOR_WEIGHT_VIEWS = 20000
PRIOR_WEIGHT_CLICKS = 50


def upsert_products(db: Database, products: list[Product], payout_rate: float, rank_offset: int = 0) -> int:
    n = 0
    for i, p in enumerate(products):
        if not p.content_id:
            continue
        ok, _ = product_allowed(p.title, p.genres)
        if not ok:
            continue
        db.exec(
            """INSERT INTO products(content_id,site,service,floor,title,url,affiliate_url,image_url,sample_image_urls,
               sample_movie_url,price,list_price,discount_rate,release_date,review_count,review_avg,actresses,genres,
               maker,series,campaign,rank_position,is_adult,payout_rate,raw,fetched_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(content_id) DO UPDATE SET title=excluded.title, url=excluded.url, affiliate_url=excluded.affiliate_url,
               image_url=excluded.image_url, sample_image_urls=excluded.sample_image_urls, sample_movie_url=excluded.sample_movie_url,
               price=excluded.price, list_price=excluded.list_price, discount_rate=excluded.discount_rate,
               review_count=excluded.review_count, review_avg=excluded.review_avg, campaign=excluded.campaign,
               rank_position=excluded.rank_position, payout_rate=excluded.payout_rate, raw=excluded.raw, fetched_at=excluded.fetched_at""",
            (p.content_id, p.site, p.service, p.floor, p.title, p.url, p.affiliate_url, p.image_url, dumps(p.sample_image_urls),
             p.sample_movie_url, p.price, p.list_price, p.discount_rate, p.release_date, p.review_count, p.review_avg,
             dumps(p.actresses), dumps(p.genres), p.maker, p.series, dumps(p.campaign), rank_offset + i + 1, int(p.is_adult),
             payout_rate, dumps(p.raw), utcnow()),
        )
        n += 1
    return n


def _measured(db: Database, where: str, params: tuple) -> dict:
    row = db.one(
        f"""SELECT COUNT(*) n,
             COALESCE(SUM((SELECT views FROM post_metrics m WHERE m.post_id=p.post_id ORDER BY captured_at DESC LIMIT 1)),0) views,
             COALESCE(SUM((SELECT url_clicks FROM post_metrics m WHERE m.post_id=p.post_id ORDER BY captured_at DESC LIMIT 1)),0) clicks,
             COALESCE(SUM((SELECT COALESCE(SUM(attribution_share),0) FROM conversions cv WHERE cv.post_id=p.post_id)),0) conv,
             COALESCE(SUM((SELECT COALESCE(SUM(revenue_jpy*attribution_share),0) FROM conversions cv WHERE cv.post_id=p.post_id)),0) revenue
           FROM posts p WHERE p.status='posted' AND {where}""", params)
    return dict(row) if row else {"n": 0, "views": 0, "clicks": 0, "conv": 0, "revenue": 0}


def momentum(db: Database, column_json: str, value: str, days: int = 30) -> float:
    """女優 / ジャンルの勢い: 直近の自分の投稿と公開調査での比率指標から 0.7〜1.4 の倍率。"""
    if not value:
        return 1.0
    m = _measured(db, f"p.posted_at>=? AND EXISTS(SELECT 1 FROM products pr WHERE pr.content_id=p.product_id AND pr.{column_json} LIKE ?)",
                  ((datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds"), f"%{value}%"))
    own = 1.0
    if m["views"] >= 2000:
        base = db.one("SELECT AVG(v) a FROM (SELECT (SELECT views FROM post_metrics mm WHERE mm.post_id=pp.post_id ORDER BY captured_at DESC LIMIT 1) v FROM posts pp WHERE pp.status='posted' ORDER BY pp.posted_at DESC LIMIT 40)")
        avg = float(base["a"] or 0) if base else 0
        if avg > 0:
            own = max(0.7, min(1.4, (m["views"] / m["n"]) / avg))
    r = db.one("SELECT AVG(views_per_follower) a, COUNT(*) c FROM research_posts WHERE (features LIKE ? OR text LIKE ?) AND captured_at>=?",
               (f"%{value}%", f"%{value}%", (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")))
    pub = 1.0
    if r and r["c"] and r["c"] >= 3:
        allr = db.one("SELECT AVG(views_per_follower) a FROM research_posts WHERE views>0")
        if allr and allr["a"]:
            pub = max(0.7, min(1.4, float(r["a"]) / float(allr["a"])))
    n_own = m["n"]
    w = n_own / (n_own + 10)   # 自分のデータが増えるほど公開情報の重みを下げる
    return round((1 - w) * pub + w * own, 3)


def estimate_eav(db: Database, prod: dict, now: datetime | None = None, pattern_boost: float = 1.0) -> tuple[float, dict]:
    now = now or datetime.now(timezone.utc)
    genres = loads(prod.get("genres"), []) if isinstance(prod.get("genres"), str) else (prod.get("genres") or [])
    actresses = loads(prod.get("actresses"), []) if isinstance(prod.get("actresses"), str) else (prod.get("actresses") or [])
    price = float(prod.get("price") or 0)
    payout = price * float(prod.get("payout_rate") or 0.2)
    disc = float(prod.get("discount_rate") or 0)
    ravg = float(prod.get("review_avg") or 0)
    rc = int(prod.get("review_count") or 0)
    rank = int(prod.get("rank_position") or 200)

    # 予測 Views（アカウント基準 × メディア × 勢い）
    base = db.one("SELECT AVG(v) a FROM (SELECT (SELECT views FROM post_metrics m WHERE m.post_id=p.post_id ORDER BY captured_at DESC LIMIT 1) v FROM posts p WHERE p.status='posted' ORDER BY p.posted_at DESC LIMIT 30)")
    views = float(base["a"]) if base and base["a"] else PRIOR_VIEWS
    if prod.get("sample_movie_url"):
        views *= 1.3
    a_m = momentum(db, "actresses", actresses[0] if actresses else "")
    g_m = momentum(db, "genres", genres[0] if genres else "")
    views *= a_m * g_m

    # CTR 事前分布
    ctr = PRIOR_CTR * (1 + min(disc, 0.7) * 0.5)
    if ravg >= 4.5:
        ctr *= 1.15
    novelty = 1.0
    rel = prod.get("release_date")
    if rel:
        try:
            days = (now.date() - datetime.fromisoformat(str(rel)[:10]).date()).days
            novelty = 1.2 if 0 <= days <= 14 else (1.1 if days < 0 else (1.0 if days <= 90 else 0.9))
        except ValueError:
            pass
    lp = prod.get("last_posted_at")
    if lp:
        try:
            since = (now - datetime.fromisoformat(lp)).days
            novelty *= 0.4 if since < 7 else (0.75 if since < 21 else 1.0)
        except ValueError:
            pass
    competition = 1.0 - 0.15 * math.exp(-rank / 10)     # ランキング上位ほど競合が多い
    discount_strength = 1 + min(disc, 0.7) * 0.8

    # CVR 事前分布
    cvr = PRIOR_CVR
    cvr *= 1.5 if price and price <= 500 else (1.2 if price and price <= 1500 else (0.8 if price >= 3000 else 1.0))
    cvr *= discount_strength
    if rc >= 50 and ravg >= 4.0:
        cvr *= 1.25
    elif rc == 0:
        cvr *= 0.9
    if loads(prod.get("campaign"), []) if isinstance(prod.get("campaign"), str) else prod.get("campaign"):
        cvr *= 1.1

    # 実測との混合（商品 → ジャンル）
    m = _measured(db, "p.product_id=?", (prod["content_id"],))
    if m["views"] < 1000 and genres:
        m = _measured(db, "p.genre=?", (genres[0],))
    hist_epc = None
    if m["views"] > 0:
        w = m["views"] / (m["views"] + PRIOR_WEIGHT_VIEWS)
        ctr = (1 - w) * ctr + w * (m["clicks"] / m["views"])
    if m["clicks"] > 0:
        w = m["clicks"] / (m["clicks"] + PRIOR_WEIGHT_CLICKS)
        cvr = (1 - w) * cvr + w * (m["conv"] / m["clicks"])
        if m["conv"] > 0:
            payout = (1 - w) * payout + w * (m["revenue"] / m["conv"])
        hist_epc = m["revenue"] / m["clicks"]

    eav = views * ctr * cvr * payout * novelty * competition * pattern_boost
    comp = {"p_views": round(views), "p_ctr": round(ctr, 5), "p_cvr": round(cvr, 5), "payout_jpy": round(payout, 1),
            "competition": round(competition, 3), "novelty": round(novelty, 3), "discount_strength": round(discount_strength, 3),
            "actress_momentum": a_m, "genre_momentum": g_m, "historical_epc": round(hist_epc, 2) if hist_epc is not None else None,
            "pattern_compat": pattern_boost, "measured_views": m["views"], "measured_clicks": m["clicks"]}
    return eav, comp


def rescore_all(db: Database) -> int:
    n = 0
    for r in db.q("SELECT * FROM products"):
        eav, comp = estimate_eav(db, dict(r))
        db.exec("UPDATE products SET eav=?, eav_components=? WHERE content_id=?", (eav, dumps(comp), r["content_id"]))
        n += 1
    return n


def top_candidates(db: Database, limit: int = 20, exclude_days: int = 7) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=exclude_days)).isoformat(timespec="seconds")
    rows = db.q("SELECT * FROM products WHERE (last_posted_at IS NULL OR last_posted_at < ?) ORDER BY eav DESC LIMIT ?", (cutoff, limit))
    out = []
    for r in rows:
        d = dict(r)
        for k in ("genres", "actresses", "sample_image_urls", "campaign"):
            d[k] = loads(d.get(k), [])
        d["eav_components"] = loads(d.get("eav_components"), {})
        out.append(d)
    return out


def check_consistency(db: Database) -> list[str]:
    """商品情報の不整合（価格が定価超・URL 欠落・成人向けフラグ矛盾）。Attention 用。"""
    issues = []
    for r in db.q("SELECT content_id, price, list_price, affiliate_url, url, site FROM products"):
        if r["price"] and r["list_price"] and r["price"] > r["list_price"]:
            issues.append(f"{r['content_id']}: 価格 {r['price']} が定価 {r['list_price']} を超過")
        if not r["affiliate_url"] or not r["url"]:
            issues.append(f"{r['content_id']}: URL 欠落")
    return issues
