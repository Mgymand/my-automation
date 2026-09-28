"""本日の投稿パッケージを作る（人間が手動投稿する完成品）。

1. 商品候補（EAV 上位 + 多様性: 同一商品・同一ジャンル偏り回避）
2. 各枠ごとにバンディットで時間帯・パターンを選ぶ（固定時刻に固定しない。人間の投稿しやすい時刻に丸める）
3. 5 案生成 → スコア → 最良案 1 つ + 代替 1〜2
4. 公式素材を選ぶ（権利状態を記録）、選定理由・類似成功投稿・注意事項を添えて posts に planned で保存
既定 5 件。運用実績（投稿数×投稿あたり利益）から最適投稿数を提案する。
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import bandit, media, patterns, products, research
from .config import Settings
from .db import Database, dumps, loads, utcnow
from .generation import generate_for_product
from .llm import LLMRouter
from .policy import HUMAN_POSTING_NOTICE
from .scoring import choose_best, persist_scores, score_candidate

ANGLE_LABEL = {"A_short": "極短文", "B_actress": "女優訴求", "C_situation": "シチュエーション", "D_review": "レビュー", "E_price": "価格・割引"}


def recent_post_texts(db: Database, n: int = 60) -> list[str]:
    return [r["text"] for r in db.q("SELECT text FROM posts ORDER BY created_at DESC LIMIT ?", (n,))]


def _slot_time(slot: str, day0: datetime, rng: random.Random, used: list[datetime], gap_min: int) -> datetime:
    a, b = (int(x) for x in slot.split("-"))
    for _ in range(30):
        h = rng.randint(a, b - 1)
        m = rng.choice([0, 30])                         # 人間が投稿しやすい 30 分刻み
        t = day0.replace(hour=h, minute=m)
        if all(abs((t - u).total_seconds()) >= gap_min * 60 for u in used):
            return t
    t = day0.replace(hour=a, minute=0)
    end = day0 + timedelta(days=1)
    while t < end:
        if all(abs((t - u).total_seconds()) >= gap_min * 60 for u in used):
            return t
        t += timedelta(minutes=30)
    return day0.replace(hour=a, minute=0)


# 2026-09 公開調査（Yahoo!リアルタイム検索で観測した FANZA 系投稿の JST 時刻分布）と一般的な X の反応時間帯から。
# 自分の実績・X READ の調査データが溜まるまでの初期値。固定時刻ではなく「枠の重み」。
DEFAULT_SLOT_PRIOR = {"21-24": 1.0, "18-21": 0.7, "12-15": 0.55, "09-12": 0.5, "15-18": 0.35}


def research_slot_prior(db: Database, tz_name: str) -> dict[str, float]:
    """公開調査の外れ値投稿の投稿時刻（JST）分布から、時間帯ごとの事前ボーナス（0..1）を作る。データが無ければ空。"""
    rows = db.q("SELECT created_at, outlier_score FROM research_posts WHERE created_at IS NOT NULL AND views>0 ORDER BY outlier_score DESC LIMIT 200")
    if len(rows) < 10:
        return {}
    tz = ZoneInfo(tz_name)
    weights: dict[str, float] = {}
    for r in rows:
        try:
            h = datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00")).astimezone(tz).hour
        except ValueError:
            continue
        slot = bandit.hour_slot(h)
        weights[slot] = weights.get(slot, 0.0) + float(r["outlier_score"] or 0)
    mx = max(weights.values(), default=0) or 1.0
    return {k: round(v / mx, 3) for k, v in weights.items()}


def suggest_posts_per_day(db: Database, current: int) -> tuple[int, str]:
    """投稿数 × 投稿あたり利益の実績から翌日の投稿数を提案（±1 の範囲で保守的に）。"""
    rows = db.q("""SELECT day, COUNT(*) n,
                     SUM((SELECT COALESCE(SUM(revenue_jpy*attribution_share),0) FROM conversions cv WHERE cv.post_id=p.post_id)) rev,
                     SUM((SELECT views FROM post_metrics m WHERE m.post_id=p.post_id ORDER BY captured_at DESC LIMIT 1)) views
                   FROM posts p WHERE p.status='posted' GROUP BY day ORDER BY day DESC LIMIT 14""")
    if len(rows) < 7:
        return current, "実績 7 日未満のため既定値を維持"
    by_n: dict[int, list[float]] = {}
    for r in rows:
        by_n.setdefault(int(r["n"]), []).append(float(r["rev"] or 0) / max(int(r["n"]), 1))
    if len(by_n) < 2:
        return current, "投稿数の変化がないため維持（探索: 翌週 +1 を試す価値あり）"
    best_n = max(by_n, key=lambda k: sum(by_n[k]) / len(by_n[k]))
    if best_n > current:
        return min(current + 1, 8), f"{best_n} 件/日の投稿あたり売上が高いため +1"
    if best_n < current:
        return max(current - 1, 2), f"{best_n} 件/日の投稿あたり売上が高いため −1"
    return current, "現状の投稿数が最良"


def plan_day(db: Database, settings: Settings, llm: LLMRouter | None, day_jst: datetime | None = None,
             rng: random.Random | None = None, replace: bool = True) -> list[int]:
    rng = rng or random.Random()
    tz = ZoneInfo(settings.timezone)
    day = day_jst or datetime.now(tz)
    if day.tzinfo is None:
        day = day.replace(tzinfo=tz)
    day0 = day.replace(hour=0, minute=0, second=0, microsecond=0)
    day_label = day0.strftime("%Y-%m-%d")

    patterns.ensure_seed(db)
    products.rescore_all(db)
    pats = patterns.active_patterns(db)
    cands = products.top_candidates(db, limit=settings.posts_per_day * 4)
    if not cands:
        db.log_event("warn", "no_products", "商品候補がありません。fetch-products を実行してください")
        return []
    if replace:
        db.exec("DELETE FROM posts WHERE day=? AND status='planned'", (day_label,))

    n_posts, why = suggest_posts_per_day(db, settings.posts_per_day)
    db.set_setting("suggested_posts_per_day", dumps({"n": n_posts, "why": why}))
    slots = [f"{a:02d}-{b:02d}" for a, b in bandit.SLOTS if a >= 9]     # 深夜 0-9 時は既定で除外（人間が投稿できる時間）
    slot_prior = research_slot_prior(db, settings.timezone) or dict(DEFAULT_SLOT_PRIOR)   # 固定時刻の決め打ちはしない。調査 → 既定重み → バンディット
    slot_arms = bandit.get_arms(db, "hour_slot")
    pat_bonus = {p["pattern_id"]: float(p.get("confidence") or 0.2) + 0.2 * float(p.get("trend_score") or 0) for p in pats}
    recent = recent_post_texts(db)
    used_times: list[datetime] = []
    used_products: set[str] = set()
    used_genres: dict[str, int] = {}
    used_angles: dict[str, int] = {}
    scheduled: list[int] = []

    for seq in range(1, n_posts + 1):
        prod = next((c for c in cands if c["content_id"] not in used_products and used_genres.get((c["genres"] or ["-"])[0], 0) < 2), None)
        if prod is None:
            db.log_event("warn", "plan_short", f"{seq - 1} 件で候補が尽きました")
            break
        media.register_official_assets(db, prod)
        slot = bandit.choose(db, "hour_slot", slots, rng, prior_bonus=slot_prior or None)
        n_obs = slot_arms.get(slot, (1, 1, 0))[2]
        if n_obs >= 5:
            slot_reason = f"時間帯 {slot}: 自分の投稿実績（{n_obs} 件）のバンディット推定で選択"
        elif slot_prior is not DEFAULT_SLOT_PRIOR and slot_prior != DEFAULT_SLOT_PRIOR:
            slot_reason = f"時間帯 {slot}: 公開調査の外れ値投稿の JST 時刻分布（ボーナス {slot_prior.get(slot, 0):.2f}）と探索で選択（自分の実績 {n_obs} 件）"
        else:
            slot_reason = f"時間帯 {slot}: 2026-09 公開調査の既定重み（夜 21-24 が最大、次に 18-21・昼）と探索で選択（自分の実績 {n_obs} 件）"
        cids = generate_for_product(db, llm, prod, recent)
        scored = []
        texts = []
        for cid in cids:
            row = dict(db.one("SELECT * FROM candidates WHERE id=?", (cid,)))
            pat = patterns.get_pattern(db, row["source_pattern_id"]) or {"pattern_id": row["source_pattern_id"], "confidence": 0.2}
            asset = media.pick_asset(db, prod["content_id"], prefer=pat.get("media_type") or "image")
            s = score_candidate(db, row, prod, pat, asset["source_url"] if asset else None, texts)
            persist_scores(db, cid, s)
            scored.append((row, s))
            texts.append(row["text"])
        # バンディット（パターン次元）の推薦で最終選択に軽い重みを付ける
        chosen_pid = bandit.choose(db, "pattern", [r["source_pattern_id"] for r, _ in scored], rng, prior_bonus=pat_bonus)
        for row, s in scored:
            if row["source_pattern_id"] == chosen_pid and s.decision == "accept":
                s.total = round(s.total * 1.15, 4)
            # 同じ訴求軸ばかりにならないよう、当日 2 回以上使った訴求軸は減点（多様性）
            if used_angles.get(row["angle"], 0) >= 2:
                s.total = round(s.total * 0.7, 4)
        best, alts = choose_best(scored)
        if best is None:
            db.log_event("warn", "no_accept", f"{prod['content_id']} の候補が採用されず", {"reasons": [x[1].reasons for x in scored]})
            used_products.add(prod["content_id"])
            continue
        row, s = best
        pat = patterns.get_pattern(db, row["source_pattern_id"]) or {"pattern_id": row["source_pattern_id"], "category": "", "media_type": "image"}
        asset = media.pick_asset(db, prod["content_id"], prefer=pat.get("media_type") or "image")
        when = _slot_time(slot, day0, rng, used_times, settings.min_post_interval_min)
        used_times.append(when)
        comp = prod.get("eav_components") or {}
        reason = (f"EAV {prod['eav']:.3f}（予測表示 {comp.get('p_views')}・CTR {comp.get('p_ctr')}・CVR {comp.get('p_cvr')}・報酬 {comp.get('payout_jpy')}円）。"
                  f"新規性 {comp.get('novelty')}・競合 {comp.get('competition')}・女優勢い {comp.get('actress_momentum')}・ジャンル勢い {comp.get('genre_momentum')}。"
                  + (f"割引 {int(float(prod.get('discount_rate') or 0) * 100)}%。" if prod.get("discount_rate") else "")
                  + (f"レビュー {prod.get('review_avg')}（{prod.get('review_count')}件）。" if prod.get("review_avg") else ""))
        sim = research.similar_success(db, pat.get("category") or "", prod.get("genres"))
        notes = [HUMAN_POSTING_NOTICE, "本文はそのままコピー。素材は下記の公式 URL からのみ（改変・切り抜き・テロップ不可）。",
                 "リンクはリプ欄に。18 歳未満閲覧不可の注意を添える。", slot_reason]
        if s.reasons:
            notes.append("注意: " + "; ".join(s.reasons))
        priority = "高" if seq <= 2 else ("中" if seq <= 4 else "低")
        cur = db.exec(
            """INSERT INTO posts(day,seq,candidate_id,account,product_id,pattern_id,genre,angle,priority,text,alternatives,media_asset_id,
               media_type,media_source,reason,similar_post_id,similar_reason,notes,scheduled_at,slot_hour,predicted,status,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (day_label, seq, row["id"], settings.x_account_name, prod["content_id"], row["source_pattern_id"], (prod["genres"] or [None])[0],
             row["angle"], priority, row["text"], dumps([{"angle": a[0]["angle"], "text": a[0]["text"], "total": a[1].total} for a in alts]),
             asset["id"] if asset else None, asset["media_kind"] if asset else "none", asset["source_url"] if asset else None,
             reason, sim["x_post_id"] if sim else None, sim["reason"] if sim else None, dumps(notes),
             when.astimezone(timezone.utc).isoformat(timespec="seconds"), when.hour,
             dumps({"views": s.expected_views, "ctr": s.p_ctr, "cvr": comp.get("p_cvr"), "revenue": s.expected_revenue_jpy,
                    "engagement": s.p_engagement, "confidence": s.pattern_confidence}), "planned", utcnow()))
        db.exec("UPDATE candidates SET status='selected' WHERE id=?", (row["id"],))
        patterns.mark_used(db, row["source_pattern_id"])
        scheduled.append(cur.lastrowid)
        recent.append(row["text"])
        used_angles[row["angle"]] = used_angles.get(row["angle"], 0) + 1
        used_products.add(prod["content_id"])
        g = (prod["genres"] or ["-"])[0]
        used_genres[g] = used_genres.get(g, 0) + 1
    # 時刻順に POST 番号を振り直す（人間が上から順に投稿できるように）
    rows = db.q("SELECT post_id FROM posts WHERE day=? AND status='planned' ORDER BY scheduled_at", (day_label,))
    for i, r in enumerate(rows, 1):
        db.exec("UPDATE posts SET seq=?, priority=? WHERE post_id=?", (i, "高" if i <= 2 else ("中" if i <= 4 else "低"), r["post_id"]))
    db.log_event("info", "plan", f"{len(scheduled)} 件のパッケージを作成（{day_label}）", {"ids": scheduled, "posts_per_day": n_posts, "why": why})
    return scheduled


def today_packages(db: Database, settings: Settings, day: str | None = None) -> list[dict]:
    tz = ZoneInfo(settings.timezone)
    day = day or datetime.now(tz).strftime("%Y-%m-%d")
    out = []
    for r in db.q("SELECT p.*, pr.title, pr.actresses, pr.genres, pr.price, pr.list_price, pr.discount_rate, pr.url, pr.affiliate_url, pr.image_url, "
                  "pt.pattern_name FROM posts p JOIN products pr ON pr.content_id=p.product_id LEFT JOIN patterns pt ON pt.pattern_id=p.pattern_id "
                  "WHERE p.day=? ORDER BY p.seq", (day,)):
        d = dict(r)
        d["actresses"] = loads(d.get("actresses"), [])
        d["genres"] = loads(d.get("genres"), [])
        d["alternatives"] = loads(d.get("alternatives"), [])
        d["notes"] = loads(d.get("notes"), [])
        d["predicted"] = loads(d.get("predicted"), {})
        d["scheduled_local"] = datetime.fromisoformat(d["scheduled_at"]).astimezone(tz).strftime("%H:%M")
        d["assets"] = media.assets_for(db, d["product_id"])
        out.append(d)
    return out
