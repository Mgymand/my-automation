"""本日の投稿計画を作る。

1. 商品候補（ERPI 上位 + 多様性）
2. 各枠ごとに バンディットで 時間帯・パターン を選ぶ
3. 候補文を生成（Sonnet or テンプレ）→ スコアリング → 採用
4. posts に scheduled として保存
固定時刻には投稿しない。時間帯は探索・活用で決める。
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import bandit, patterns, products
from .config import Settings
from .db import Database, dumps, loads, utcnow
from .generation import build_reply_text, generate_for_product
from .llm import LLMRouter
from .scoring import persist_scores, score_candidate
from .tracking import new_code, tracking_url
from .x_client import PRICE_POST_USD, PRICE_POST_WITH_URL_USD, to_jpy


def recent_post_texts(db: Database, n: int = 60) -> list[str]:
    return [r["text"] for r in db.q("SELECT text FROM posts ORDER BY created_at DESC LIMIT ?", (n,))]


def _slot_to_datetime(slot: str, day: datetime, rng: random.Random, used: list[datetime], min_gap_min: int) -> datetime:
    a, b = (int(x) for x in slot.split("-"))
    for _ in range(20):
        h = rng.randint(a, b - 1)
        m = rng.randint(0, 59)
        t = day.replace(hour=h, minute=m, second=0, microsecond=0)
        if all(abs((t - u).total_seconds()) >= min_gap_min * 60 for u in used):
            return t
    # 枠が埋まっている場合: 枠の先頭から 15 分刻みで、間隔を満たす最初の時刻（当日内）を探す
    t = day.replace(hour=a, minute=0, second=0, microsecond=0)
    end = day.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    while t < end:
        if all(abs((t - u).total_seconds()) >= min_gap_min * 60 for u in used):
            return t
        t += timedelta(minutes=15)
    return day.replace(hour=a, minute=0, second=0, microsecond=0)


def plan_day(db: Database, settings: Settings, llm: LLMRouter | None, day_jst: datetime | None = None,
             rng: random.Random | None = None) -> list[int]:
    rng = rng or random.Random()
    tz = ZoneInfo(settings.timezone)
    day = (day_jst or datetime.now(tz)).replace(tzinfo=tz) if (day_jst and day_jst.tzinfo is None) else (day_jst or datetime.now(tz))
    day0 = day.replace(hour=0, minute=0, second=0, microsecond=0)

    patterns.ensure_seed(db)
    products.rescore_all(db)
    pats = patterns.active_patterns(db)
    if not pats:
        return []
    adult_ok = settings.adult_on_x_acknowledged
    cands = products.top_candidates(db, limit=settings.posts_per_day * 4, adult_allowed=True)
    if not cands:
        db.log_event("warn", "no_products", "商品候補がありません。fetch-products を実行してください")
        return []

    slots = [f"{a:02d}-{b:02d}" for a, b in bandit.SLOTS]
    pat_ids = [p["pattern_id"] for p in pats]
    pat_bonus = {p["pattern_id"]: float(p.get("confidence") or 0.2) for p in pats}
    recent = recent_post_texts(db)
    used_times: list[datetime] = []
    used_products: set[str] = set()
    used_genres: dict[str, int] = {}
    scheduled: list[int] = []
    post_cost = to_jpy(PRICE_POST_USD + (PRICE_POST_WITH_URL_USD if settings.link_in_reply else 0), settings.usd_jpy)

    for i in range(settings.posts_per_day):
        # 商品: ERPI 順に、同一商品・同一ジャンル偏りを避ける
        prod = None
        for c in cands:
            g = (c["genres"] or ["-"])[0]
            if c["content_id"] in used_products or used_genres.get(g, 0) >= 2:
                continue
            if c["is_adult"] and not adult_ok:
                continue
            prod = c
            break
        if prod is None:
            db.log_event("warn", "plan_short", f"{i} 件で候補が尽きました（成人向けゲート未承認の可能性）")
            break
        slot = bandit.choose(db, "hour_slot", slots, rng)
        pid = bandit.choose(db, "pattern", pat_ids, rng, prior_bonus=pat_bonus)
        pat = next(p for p in pats if p["pattern_id"] == pid)

        cids = generate_for_product(db, llm, prod, pat, recent)
        best, best_s = None, None
        for cid in cids:
            row = dict(db.one("SELECT * FROM candidates WHERE id=?", (cid,)))
            ai_cost = 0.0
            s = score_candidate(db, settings, row, prod, pat, recent, post_cost, ai_cost)
            persist_scores(db, cid, s)
            if s.decision == "accept" and (best_s is None or s.expected_profit_jpy > best_s.expected_profit_jpy):
                best, best_s = row, s
        if best is None:
            # 人間レビュー待ち or 全滅。理由をログに残して次へ
            last = db.one("SELECT scores FROM candidates WHERE product_id=? ORDER BY id DESC LIMIT 1", (prod["content_id"],))
            db.log_event("warn", "no_accept", f"{prod['content_id']} の候補が採用されず", loads(last["scores"], {}) if last else {})
            used_products.add(prod["content_id"])
            continue

        when = _slot_to_datetime(slot, day0, rng, used_times, settings.min_post_interval_min)
        now_tz = datetime.now(tz)
        if when < now_tz - timedelta(minutes=5) and day0.date() == now_tz.date():
            # 既に過ぎた枠は翌日に回さず、今日の残り時間で投稿間隔を守りつつ最も早い時刻に置く
            when = now_tz.replace(second=0, microsecond=0) + timedelta(minutes=10)
            while any(abs((when - u).total_seconds()) < settings.min_post_interval_min * 60 for u in used_times):
                when += timedelta(minutes=15)
        used_times.append(when)
        code = new_code()
        reply = build_reply_text(tracking_url(settings, code) if settings.tracking_base_url else prod["affiliate_url"],
                                 settings.disclosure_text) if settings.link_in_reply else None
        media_type = "video" if (pat["media"] == "video" and prod.get("sample_movie_url")) else ("image" if prod.get("sample_image_urls") or prod.get("image_url") else "none")
        media_src = prod.get("sample_movie_url") if media_type == "video" else ((prod.get("sample_image_urls") or [prod.get("image_url")])[0])
        cur = db.exec(
            """INSERT INTO posts(candidate_id,account,product_id,pattern_id,genre,angle,text,reply_text,media_type,media_source,
               scheduled_at,slot_hour,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (best["id"], settings.x_account_name, prod["content_id"], pid, (prod["genres"] or [None])[0], best["angle"],
             best["text"], reply, media_type, media_src, when.astimezone(timezone.utc).isoformat(timespec="seconds"),
             when.hour, "scheduled", utcnow()),
        )
        db.exec("UPDATE posts SET tracking_code=? WHERE post_id=?", (code, cur.lastrowid))
        db.exec("UPDATE candidates SET status='selected' WHERE id=?", (best["id"],))
        patterns.mark_used(db, pid)
        scheduled.append(cur.lastrowid)
        recent.append(best["text"])
        used_products.add(prod["content_id"])
        g = (prod["genres"] or ["-"])[0]
        used_genres[g] = used_genres.get(g, 0) + 1
    db.log_event("info", "plan", f"{len(scheduled)} 件を予定", {"ids": scheduled})
    return scheduled
