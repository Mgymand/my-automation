"""計測データの取り込みと学習の更新（決定論的処理のみ）。

- X の指標（views/likes/reposts/replies/bookmarks/profile_visits/url_clicks）を取り込む
- DMM の成果 CSV を取り込み、投稿へ帰属させる
- 投稿ごとの利益から バンディット と パターン DB を更新する
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

from . import bandit, patterns
from .config import Settings
from .db import Database, utcnow
from .tracking import attribute_conversion
from .x_client import to_jpy


def ingest_x_metrics(db: Database, settings: Settings, x, max_age_days: int = 14) -> int:
    since = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat(timespec="seconds")
    rows = db.q("SELECT post_id, x_post_id FROM posts WHERE status='posted' AND x_post_id IS NOT NULL AND posted_at>=?", (since,))
    if not rows:
        return 0
    id_map = {r["x_post_id"]: r["post_id"] for r in rows if not str(r["x_post_id"]).startswith("dry-")}
    if not id_map:
        return 0
    metrics, cost_usd = x.post_metrics(list(id_map.keys()))
    if cost_usd:
        db.add_cost("x_api", to_jpy(cost_usd, settings.usd_jpy), ref="metrics")
    n = 0
    for xid, m in metrics.items():
        db.exec(
            "INSERT INTO post_metrics(post_id,captured_at,views,likes,reposts,replies,quotes,bookmarks,profile_visits,url_clicks) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (id_map[xid], utcnow(), m["views"], m["likes"], m["reposts"], m["replies"], m["quotes"], m["bookmarks"],
             m["profile_visits"], m["url_clicks"]),
        )
        n += 1
    return n


def ingest_conversions_csv(db: Database, settings: Settings, text: str, source: str = "dmm_csv") -> int:
    """DMM アフィリエイト管理画面の成果レポート CSV を取り込む。
    想定列（ヘッダ名で判定・柔軟）: 日時/date, 商品ID/content_id, 報酬/revenue, 注文ID/order_ref
    """
    reader = csv.DictReader(io.StringIO(text))
    n = 0
    for row in reader:
        def pick(*keys):
            for k in keys:
                for rk in row:
                    if rk and rk.strip().lower() == k.lower():
                        return (row[rk] or "").strip()
            return ""
        ts_s = pick("date", "日時", "成果日時", "発生日時", "日付")
        rev_s = pick("revenue", "報酬", "報酬額", "成果報酬", "amount").replace(",", "").replace("円", "")
        pid = pick("content_id", "商品ID", "商品id", "cid") or None
        order = pick("order_ref", "注文ID", "注文番号", "id") or None
        try:
            revenue = float(rev_s)
        except ValueError:
            continue
        try:
            ts = datetime.fromisoformat(ts_s.replace("/", "-")[:19])
        except ValueError:
            ts = datetime.now(timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if order and db.one("SELECT 1 FROM conversions WHERE order_ref=?", (order,)):
            continue
        post_id, attr = attribute_conversion(db, pid, ts, settings.attribution_window_hours)
        db.exec("INSERT INTO conversions(ts,post_id,product_id,revenue_jpy,order_ref,source,attribution,created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (ts.isoformat(timespec="seconds"), post_id, pid, revenue, order, source, attr, utcnow()))
        n += 1
    return n


def post_profit_rows(db: Database, days: int = 30) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    rows = db.q(
        """SELECT p.*, 
             (SELECT views FROM post_metrics m WHERE m.post_id=p.post_id ORDER BY captured_at DESC LIMIT 1) views,
             (SELECT url_clicks FROM post_metrics m WHERE m.post_id=p.post_id ORDER BY captured_at DESC LIMIT 1) url_clicks,
             (SELECT COUNT(*) FROM clicks c WHERE c.tracking_code=p.tracking_code) clicks,
             (SELECT COALESCE(SUM(revenue_jpy),0) FROM conversions cv WHERE cv.post_id=p.post_id) revenue,
             (SELECT COUNT(*) FROM conversions cv WHERE cv.post_id=p.post_id) conv
           FROM posts p WHERE p.status='posted' AND p.posted_at>=?""",
        (since,),
    )
    out = []
    for r in rows:
        d = dict(r)
        d["views"] = d["views"] or 0
        d["clicks"] = max(d["clicks"] or 0, d["url_clicks"] or 0)
        d["profit"] = (d["revenue"] or 0) - (d["api_cost_jpy"] or 0) - (d["ai_cost_jpy"] or 0)
        d["profit_per_view"] = d["profit"] / d["views"] if d["views"] else 0.0
        out.append(d)
    return out


def learn(db: Database, min_age_hours: int = 24) -> int:
    """投稿から一定時間経過した投稿の成果でバンディットとパターン DB を更新する。
    二重更新を避けるため settings.learned_post_ids に記録する。"""
    learned = set((db.get_setting("learned_post_ids", "") or "").split(","))
    rows = post_profit_rows(db, days=30)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=min_age_hours)
    eligible = [r for r in rows if str(r["post_id"]) not in learned and r["posted_at"]
                and datetime.fromisoformat(r["posted_at"]) <= cutoff]
    if not eligible:
        return 0
    ppvs = sorted(r["profit_per_view"] for r in rows if r["views"] > 0)
    baseline = ppvs[len(ppvs) // 2] if ppvs else 0.0
    baseline = max(baseline, 1e-4)
    n = 0
    for r in eligible:
        reward = bandit.normalize_reward(r["profit_per_view"], baseline) if r["views"] > 0 else 0.3
        bandit.update(db, "hour_slot", bandit.hour_slot(int(r["slot_hour"] or 21)), reward)
        bandit.update(db, "pattern", r["pattern_id"], reward)
        if r.get("genre"):
            bandit.update(db, "genre", r["genre"], reward)
        bandit.update(db, "media", r.get("media_type") or "none", reward)
        learned.add(str(r["post_id"]))
        n += 1
    db.set_setting("learned_post_ids", ",".join(sorted(x for x in learned if x)))
    patterns.update_from_results(db)
    patterns.decay_stale(db)
    return n
