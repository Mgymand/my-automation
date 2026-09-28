"""商品候補の取得と ERPI（Expected Revenue Per Impression）推定。

ERPI = pCTR × pCVR × 平均報酬（円）
事前分布（ヒューリスティック）と実測値をサンプル数で重み付けして混ぜる（ベイズ的縮小）。
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from .compliance import product_allowed
from .db import Database, dumps, loads, utcnow
from .dmm_client import Product

PRIOR_CTR = 0.008     # 表示→リンククリック。公開情報からの控えめな初期値
PRIOR_CVR = 0.02      # クリック→購入
PRIOR_WEIGHT_VIEWS = 20000   # 実測 views がこの程度で事前分布と同等の重み
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
               ON CONFLICT(content_id) DO UPDATE SET title=excluded.title, url=excluded.url,
               affiliate_url=excluded.affiliate_url, image_url=excluded.image_url,
               sample_image_urls=excluded.sample_image_urls, sample_movie_url=excluded.sample_movie_url,
               price=excluded.price, list_price=excluded.list_price, discount_rate=excluded.discount_rate,
               review_count=excluded.review_count, review_avg=excluded.review_avg, campaign=excluded.campaign,
               rank_position=excluded.rank_position, payout_rate=excluded.payout_rate, raw=excluded.raw,
               fetched_at=excluded.fetched_at""",
            (p.content_id, p.site, p.service, p.floor, p.title, p.url, p.affiliate_url, p.image_url,
             dumps(p.sample_image_urls), p.sample_movie_url, p.price, p.list_price, p.discount_rate, p.release_date,
             p.review_count, p.review_avg, dumps(p.actresses), dumps(p.genres), p.maker, p.series, dumps(p.campaign),
             rank_offset + i + 1, int(p.is_adult), payout_rate, dumps(p.raw), utcnow()),
        )
        n += 1
    return n


def _measured(db: Database, where: str, params: tuple) -> dict:
    row = db.one(
        f"""
        SELECT COUNT(*) n,
          COALESCE(SUM((SELECT views FROM post_metrics m WHERE m.post_id=p.post_id ORDER BY captured_at DESC LIMIT 1)),0) views,
          COALESCE(SUM((SELECT COUNT(*) FROM clicks c WHERE c.tracking_code=p.tracking_code)),0) clicks,
          COALESCE(SUM((SELECT COUNT(*) FROM conversions cv WHERE cv.post_id=p.post_id)),0) conv,
          COALESCE(SUM((SELECT COALESCE(SUM(revenue_jpy),0) FROM conversions cv WHERE cv.post_id=p.post_id)),0) revenue
        FROM posts p WHERE p.status='posted' AND {where}
        """,
        params,
    )
    return dict(row) if row else {"n": 0, "views": 0, "clicks": 0, "conv": 0, "revenue": 0}


def estimate_erpi(db: Database, prod: dict, now: datetime | None = None) -> tuple[float, dict]:
    now = now or datetime.now(timezone.utc)
    genres = loads(prod.get("genres"), [])
    price = float(prod.get("price") or 0)
    payout = price * float(prod.get("payout_rate") or 0.2)

    # --- 事前 CTR ---
    ctr = PRIOR_CTR
    if prod.get("sample_movie_url"):
        ctr *= 1.3                       # 動画素材あり（公開調査: 動画 > 画像）
    if loads(prod.get("sample_image_urls"), []):
        ctr *= 1.1
    disc = float(prod.get("discount_rate") or 0)
    ctr *= 1 + min(disc, 0.7) * 0.5      # 割引は興味を引く
    ravg = float(prod.get("review_avg") or 0)
    if ravg >= 4.5:
        ctr *= 1.15
    # 新規性: 発売から日が浅いほど（14 日以内 +20%）、最近投稿済みなら下げる
    rel = prod.get("release_date")
    if rel:
        try:
            days = (now.date() - datetime.fromisoformat(str(rel)[:10]).date()).days
            if 0 <= days <= 14:
                ctr *= 1.2
            elif days < 0:
                ctr *= 1.1   # 予約
        except ValueError:
            pass
    lp = prod.get("last_posted_at")
    if lp:
        try:
            since = (now - datetime.fromisoformat(lp)).days
            if since < 7:
                ctr *= 0.4
            elif since < 21:
                ctr *= 0.75
        except ValueError:
            pass
    # 競合度: ランキング上位ほど他のアフィリエイターも扱う → 差別化しづらい（軽い減点）
    rank = int(prod.get("rank_position") or 100)
    competition = 1.0 - 0.15 * math.exp(-rank / 10)
    ctr *= competition

    # --- 事前 CVR ---
    cvr = PRIOR_CVR
    if price:
        if price <= 500:
            cvr *= 1.5
        elif price <= 1500:
            cvr *= 1.2
        elif price >= 3000:
            cvr *= 0.8
    cvr *= 1 + min(disc, 0.7) * 0.8
    rc = int(prod.get("review_count") or 0)
    if rc >= 50 and ravg >= 4.0:
        cvr *= 1.25
    elif rc == 0:
        cvr *= 0.9
    if loads(prod.get("campaign"), []):
        cvr *= 1.1

    # --- 実測との混合（商品→ジャンル→全体の順で使えるものを使う） ---
    m = _measured(db, "p.product_id=?", (prod["content_id"],))
    if m["views"] < 1000 and genres:
        m = _measured(db, "p.genre=?", (genres[0],))
    if m["views"] > 0:
        w = m["views"] / (m["views"] + PRIOR_WEIGHT_VIEWS)
        ctr = (1 - w) * ctr + w * (m["clicks"] / m["views"])
    if m["clicks"] > 0:
        w = m["clicks"] / (m["clicks"] + PRIOR_WEIGHT_CLICKS)
        cvr = (1 - w) * cvr + w * (m["conv"] / m["clicks"])
        if m["conv"] > 0:
            payout = (1 - w) * payout + w * (m["revenue"] / m["conv"])

    erpi = ctr * cvr * payout
    comp = {"p_ctr": round(ctr, 5), "p_cvr": round(cvr, 5), "payout_jpy": round(payout, 1),
            "competition": round(competition, 3), "measured_views": m["views"], "measured_clicks": m["clicks"]}
    return erpi, comp


def rescore_all(db: Database) -> int:
    n = 0
    for r in db.q("SELECT * FROM products"):
        erpi, comp = estimate_erpi(db, dict(r))
        db.exec("UPDATE products SET erpi=?, erpi_components=? WHERE content_id=?", (erpi, dumps(comp), r["content_id"]))
        n += 1
    return n


def top_candidates(db: Database, limit: int = 20, exclude_days: int = 7, adult_allowed: bool = True) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=exclude_days)).isoformat(timespec="seconds")
    rows = db.q(
        "SELECT * FROM products WHERE (last_posted_at IS NULL OR last_posted_at < ?) AND (? OR is_adult=0) "
        "ORDER BY erpi DESC LIMIT ?",
        (cutoff, 1 if adult_allowed else 0, limit),
    )
    out = []
    for r in rows:
        d = dict(r)
        for k in ("genres", "actresses", "sample_image_urls", "campaign", "erpi_components"):
            d[k] = loads(d.get(k), [] if k != "erpi_components" else {})
        out.append(d)
    return out
