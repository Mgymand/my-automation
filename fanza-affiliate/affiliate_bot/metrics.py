"""計測データの取り込みと学習（決定論的処理のみ）。

- 投稿後の X 指標をマイルストーン（既定 24h / 72h。6h / 7d は設定で追加）で取得。読取 $0.001/件（自分の投稿）
- X 読取が使えない場合は CSV / 手入力 fallback（`metrics --manual POST_ID views likes reposts replies bookmarks`）
- FANZA 成果 CSV の取り込みと確率的帰属（商品×時間帯 → 商品×日付 → channel）。attribution_confidence を保存
- 投稿ごとの利益からバンディットとパターン DB を更新
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

from . import bandit, patterns
from .config import Settings
from .db import Database, utcnow
from .x_client import to_jpy


# ---------------------------------------------------------------- X 指標（マイルストーン）
def due_milestones(db: Database, milestones: tuple[int, ...], now: datetime | None = None) -> list[tuple[int, str, int]]:
    """(post_id, x_post_id, milestone_hours) のうち、経過済みで未取得のもの。"""
    now = now or datetime.now(timezone.utc)
    out = []
    for r in db.q("SELECT post_id, x_post_id, posted_at FROM posts WHERE status='posted' AND x_post_id IS NOT NULL AND posted_at >= ?",
                  ((now - timedelta(days=10)).isoformat(timespec="seconds"),)):
        posted = datetime.fromisoformat(r["posted_at"])
        for h in sorted(milestones):
            if now >= posted + timedelta(hours=h) and not db.one(
                    "SELECT 1 FROM post_metrics WHERE post_id=? AND milestone_hours=?", (r["post_id"], h)):
                out.append((r["post_id"], r["x_post_id"], h))
    return out


def ingest_x_metrics(db: Database, settings: Settings, x, now: datetime | None = None) -> int:
    due = due_milestones(db, settings.metric_milestones_hours, now)
    if not due:
        return 0
    ids = sorted({xid for _, xid, _ in due})
    posts, cost = x.posts(ids, owned=True)
    if cost:
        db.add_cost("x_api", to_jpy(cost, settings.usd_jpy), ref="metrics")
    by_id = {p["x_post_id"]: p for p in posts}
    n = 0
    for post_id, xid, h in due:
        p = by_id.get(xid)
        if not p:
            continue
        db.exec("""INSERT INTO post_metrics(post_id,captured_at,milestone_hours,source,views,likes,reposts,replies,quotes,bookmarks)
                   VALUES(?,?,?,'x_api',?,?,?,?,?,?)""",
                (post_id, utcnow(), h, p["views"], p["likes"], p["reposts"], p["replies"], p["quotes"], p["bookmarks"]))
        n += 1
    return n


def ingest_manual_metrics(db: Database, post_id: int, views: int, likes: int = 0, reposts: int = 0, replies: int = 0,
                          bookmarks: int = 0, url_clicks: int = 0, milestone_hours: int | None = None, source: str = "manual") -> None:
    db.exec("""INSERT INTO post_metrics(post_id,captured_at,milestone_hours,source,views,likes,reposts,replies,bookmarks,url_clicks)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (post_id, utcnow(), milestone_hours, source, views, likes, reposts, replies, bookmarks, url_clicks))


def ingest_metrics_csv(db: Database, text: str) -> int:
    """列: post_id または x_post_id, views, likes, reposts, replies, bookmarks, url_clicks(任意), milestone_hours(任意)"""
    n = 0
    for row in csv.DictReader(io.StringIO(text)):
        pid = row.get("post_id")
        if not pid and row.get("x_post_id"):
            r = db.one("SELECT post_id FROM posts WHERE x_post_id=?", (row["x_post_id"].strip(),))
            pid = r["post_id"] if r else None
        if not pid:
            continue
        ingest_manual_metrics(db, int(pid), int(row.get("views") or 0), int(row.get("likes") or 0), int(row.get("reposts") or 0),
                              int(row.get("replies") or 0), int(row.get("bookmarks") or 0), int(row.get("url_clicks") or 0),
                              int(row["milestone_hours"]) if row.get("milestone_hours") else None, source="csv")
        n += 1
    return n


def latest_metrics(db: Database, post_id: int) -> dict:
    r = db.one("SELECT * FROM post_metrics WHERE post_id=? ORDER BY captured_at DESC LIMIT 1", (post_id,))
    return dict(r) if r else {"views": 0, "likes": 0, "reposts": 0, "replies": 0, "bookmarks": 0, "url_clicks": 0}


# ---------------------------------------------------------------- 成果（FANZA CSV）の確率的帰属
def _pick(row: dict, *keys: str) -> str:
    for k in keys:
        for rk in row:
            if rk and rk.strip().lower() == k.lower():
                return (row[rk] or "").strip()
    return ""


def attribute(db: Database, product_id: str | None, ts: datetime, window_hours: int, channel: str | None = None) -> list[tuple[int | None, str, str, float]]:
    """成果 1 件を投稿へ帰属。戻り値: [(post_id, attribution, confidence, share)]。
    1) 商品一致 × 時間窓内の投稿が 1 件 → last_post / high
    2) 商品一致 × 時間窓内に複数 → views 比で按分 / medium
    3) 商品一致 × 同日（窓外）→ product_day / low
    4) 一致なし → unattributed / low（投稿には紐付けない）"""
    start = (ts - timedelta(hours=window_hours)).isoformat(timespec="seconds")
    end = ts.isoformat(timespec="seconds")
    if product_id:
        rows = db.q("SELECT post_id FROM posts WHERE status='posted' AND product_id=? AND posted_at BETWEEN ? AND ? ORDER BY posted_at DESC",
                    (product_id, start, end))
        if len(rows) == 1:
            return [(rows[0]["post_id"], "product_window", "high", 1.0)]
        if len(rows) > 1:
            views = {r["post_id"]: max(latest_metrics(db, r["post_id"]).get("views") or 0, 1) for r in rows}
            tot = sum(views.values())
            return [(pid, "product_window_split", "medium", round(v / tot, 3)) for pid, v in views.items()]
        day = ts.astimezone(timezone.utc).strftime("%Y-%m-%d")
        rows = db.q("SELECT post_id FROM posts WHERE status='posted' AND product_id=? AND substr(posted_at,1,10)=? ORDER BY posted_at DESC LIMIT 1",
                    (product_id, day))
        if rows:
            return [(rows[0]["post_id"], "product_day", "low", 1.0)]
    return [(None, "unattributed", "low", 1.0)]


def ingest_conversions_csv(db: Database, settings: Settings, text: str, source: str = "dmm_csv") -> int:
    """FANZA アフィリエイト管理画面の成果 CSV。列名はヘッダで柔軟に判定:
    日時/date, 商品ID/content_id, 報酬/revenue, 注文ID/order_ref, アフィリエイトID/channel"""
    reader = csv.DictReader(io.StringIO(text))
    n = 0
    for row in reader:
        ts_s = _pick(row, "date", "日時", "成果日時", "発生日時", "日付", "成果発生日")
        rev_s = _pick(row, "revenue", "報酬", "報酬額", "成果報酬", "amount", "報酬金額").replace(",", "").replace("円", "")
        pid = _pick(row, "content_id", "商品ID", "商品id", "cid", "コンテンツID") or None
        order = _pick(row, "order_ref", "注文ID", "注文番号", "id", "成果ID") or None
        channel = _pick(row, "channel", "アフィリエイトID", "affiliate_id", "af_id") or None
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
        for post_id, attr, conf, share in attribute(db, pid, ts, settings.attribution_window_hours, channel):
            db.exec("""INSERT INTO conversions(ts,post_id,product_id,revenue_jpy,order_ref,channel,source,attribution,attribution_confidence,
                       attribution_share,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (ts.isoformat(timespec="seconds"), post_id, pid, revenue, order, channel, source, attr, conf, share, utcnow()))
        n += 1
    db.set_setting("last_conversions_ingest_at", utcnow())
    return n


# ---------------------------------------------------------------- 学習
def post_profit_rows(db: Database, days: int = 30) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    rows = db.q("""SELECT p.*,
                     (SELECT views FROM post_metrics m WHERE m.post_id=p.post_id ORDER BY captured_at DESC LIMIT 1) views,
                     (SELECT likes+reposts+replies+bookmarks FROM post_metrics m WHERE m.post_id=p.post_id ORDER BY captured_at DESC LIMIT 1) eng,
                     (SELECT url_clicks FROM post_metrics m WHERE m.post_id=p.post_id ORDER BY captured_at DESC LIMIT 1) clicks,
                     (SELECT COALESCE(SUM(revenue_jpy*attribution_share),0) FROM conversions cv WHERE cv.post_id=p.post_id) revenue,
                     (SELECT COALESCE(SUM(attribution_share),0) FROM conversions cv WHERE cv.post_id=p.post_id) conv
                   FROM posts p WHERE p.status='posted' AND p.posted_at>=?""", (since,))
    out = []
    for r in rows:
        d = dict(r)
        d["views"] = d["views"] or 0
        d["eng"] = d["eng"] or 0
        d["clicks"] = d["clicks"] or 0
        d["profit"] = (d["revenue"] or 0) - (d["api_cost_jpy"] or 0) - (d["ai_cost_jpy"] or 0)
        d["revenue_per_1k_views"] = (d["revenue"] or 0) / d["views"] * 1000 if d["views"] else 0.0
        out.append(d)
    return out


def blended_reward(row: dict, baselines: dict, conv_weight: float) -> float:
    """Revenue / Engagement / Views の 3 シグナルを信頼度に応じて合成（0..1）。
    Conversion データが増えるほど conv_weight（0..1）が上がり、Revenue 中心になる。"""
    def norm(v, base):
        return bandit.normalize_reward(v, max(base, 1e-6))
    rev_sig = norm(row["revenue_per_1k_views"], baselines["rev"]) if row["views"] else 0.3
    eng_sig = norm(row["eng"] / row["views"], baselines["eng"]) if row["views"] else 0.3
    views_sig = norm(row["views"], baselines["views"])
    w_rev = conv_weight
    w_eng = (1 - conv_weight) * 0.6
    w_views = (1 - conv_weight) * 0.4
    return w_rev * rev_sig + w_eng * eng_sig + w_views * views_sig


def learn(db: Database, min_age_hours: int = 24) -> int:
    learned = set((db.get_setting("learned_post_ids", "") or "").split(","))
    rows = post_profit_rows(db, days=30)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=min_age_hours)
    eligible = [r for r in rows if str(r["post_id"]) not in learned and r["posted_at"] and datetime.fromisoformat(r["posted_at"]) <= cutoff
                and (r["views"] > 0 or r["revenue"] > 0)]
    if not eligible:
        return 0
    def med(vals):
        vals = sorted(vals)
        return vals[len(vals) // 2] if vals else 0.0
    baselines = {"rev": med([r["revenue_per_1k_views"] for r in rows if r["views"]]) or 1.0,
                 "eng": med([r["eng"] / r["views"] for r in rows if r["views"]]) or 0.01,
                 "views": med([r["views"] for r in rows if r["views"]]) or 100.0}
    n_conv = sum(r["conv"] for r in rows)
    conv_weight = min(0.8, n_conv / (n_conv + 20))     # CV 20 件で 0.5、増えるほど売上中心
    n = 0
    for r in eligible:
        reward = blended_reward(r, baselines, conv_weight)
        bandit.update(db, "hour_slot", bandit.hour_slot(int(r["slot_hour"] or 21)), reward)
        bandit.update(db, "pattern", r["pattern_id"], reward)
        if r.get("genre"):
            bandit.update(db, "genre", r["genre"], reward)
        bandit.update(db, "media", r.get("media_type") or "none", reward)
        learned.add(str(r["post_id"]))
        n += 1
    db.set_setting("learned_post_ids", ",".join(sorted(x for x in learned if x)))
    db.set_setting("conv_weight", f"{conv_weight:.3f}")
    patterns.update_from_results(db)
    patterns.decay_stale(db)
    return n
