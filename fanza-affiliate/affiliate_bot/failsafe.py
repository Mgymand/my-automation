"""自動停止ルール。条件に該当したら settings.paused=1 にして人間レビューへ回す。
回避策は考えない。原因を解決してから `cli resume` で再開する。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from .config import Settings
from .db import Database

MIN_VIEWS_FOR_CTR_CHECK = 5000
MIN_CLICKS_FOR_CVR_CHECK = 100
DROP_RATIO = 0.5   # 直近 3 日が過去 14 日の半分未満なら異常


def is_paused(db: Database) -> tuple[bool, str]:
    return db.get_setting("paused", "0") == "1", db.get_setting("paused_reason", "") or ""


def halt(db: Database, code: str, message: str, data: dict | None = None) -> None:
    db.set_setting("paused", "1")
    db.set_setting("paused_reason", f"{code}: {message}")
    db.log_event("halt", code, message, data)


def resume(db: Database) -> None:
    db.set_setting("paused", "0")
    db.set_setting("paused_reason", "")
    db.log_event("info", "resume", "人間により再開")


def _window_stats(db: Database, days_from: int, days_to: int) -> dict:
    now = datetime.now(timezone.utc)
    a = (now - timedelta(days=days_from)).isoformat(timespec="seconds")
    b = (now - timedelta(days=days_to)).isoformat(timespec="seconds")
    row = db.one(
        """SELECT COUNT(*) n,
             COALESCE(SUM((SELECT views FROM post_metrics m WHERE m.post_id=p.post_id ORDER BY captured_at DESC LIMIT 1)),0) views,
             COALESCE(SUM((SELECT COUNT(*) FROM clicks c WHERE c.tracking_code=p.tracking_code)),0) clicks,
             COALESCE(SUM((SELECT COUNT(*) FROM conversions cv WHERE cv.post_id=p.post_id)),0) conv
           FROM posts p WHERE p.status='posted' AND p.posted_at>=? AND p.posted_at<?""",
        (a, b),
    )
    return dict(row)


def check_metrics_anomaly(db: Database) -> list[str]:
    """CTR / CVR の異常低下。サンプルサイズを満たすときだけ判定。"""
    reasons = []
    recent = _window_stats(db, 3, 0)
    base = _window_stats(db, 17, 3)
    if recent["views"] >= MIN_VIEWS_FOR_CTR_CHECK and base["views"] >= MIN_VIEWS_FOR_CTR_CHECK:
        r_ctr = recent["clicks"] / recent["views"]
        b_ctr = base["clicks"] / base["views"]
        if b_ctr > 0 and r_ctr < b_ctr * DROP_RATIO:
            reasons.append(f"CTR 異常低下 {b_ctr:.4f}→{r_ctr:.4f}")
    if recent["clicks"] >= MIN_CLICKS_FOR_CVR_CHECK and base["clicks"] >= MIN_CLICKS_FOR_CVR_CHECK:
        r_cvr = recent["conv"] / recent["clicks"]
        b_cvr = base["conv"] / base["clicks"]
        if b_cvr > 0 and r_cvr < b_cvr * DROP_RATIO:
            reasons.append(f"CVR 異常低下 {b_cvr:.4f}→{r_cvr:.4f}")
    return reasons


def check_tracking_health(db: Database) -> list[str]:
    """X 側の url_clicks はあるのに自前クリックが 0 → トラッキング障害。"""
    row = db.one(
        """SELECT COALESCE(SUM(m.url_clicks),0) xc,
             COALESCE(SUM((SELECT COUNT(*) FROM clicks c WHERE c.tracking_code=p.tracking_code)),0) oc
           FROM posts p JOIN post_metrics m ON m.post_id=p.post_id
           WHERE p.posted_at >= datetime('now','-2 days')"""
    )
    if row and row["xc"] >= 30 and row["oc"] == 0:
        return [f"トラッキング障害の疑い: X url_clicks={row['xc']} に対し自前クリック 0"]
    return []


def check_duplicates(db: Database) -> list[str]:
    row = db.one(
        """SELECT text, COUNT(*) c FROM posts WHERE status IN('posted','scheduled')
           AND created_at >= datetime('now','-3 days') GROUP BY text HAVING c>=2 LIMIT 1"""
    )
    return [f"同一本文の重複投稿を検出: {row['text'][:40]}…"] if row else []


def check_links(db: Database, sample: int = 3, session: requests.Session | None = None) -> list[str]:
    """本日投稿予定の商品のアフィリエイト URL が生きているか（HEAD/GET, リダイレクト許可）。"""
    s = session or requests.Session()
    rows = db.q(
        """SELECT pr.affiliate_url FROM posts p JOIN products pr ON pr.content_id=p.product_id
           WHERE p.status='scheduled' LIMIT ?""", (sample,))
    bad = []
    for r in rows:
        url = r["affiliate_url"]
        if not url:
            bad.append("アフィリエイト URL が空")
            continue
        try:
            resp = s.get(url, timeout=15, allow_redirects=True, stream=True)
            if resp.status_code >= 400:
                bad.append(f"リンク障害 HTTP {resp.status_code}: {url[:60]}")
        except requests.RequestException as e:
            bad.append(f"リンク障害: {e.__class__.__name__}")
    return bad


def run_checks(db: Database, settings: Settings, check_network: bool = False) -> list[str]:
    reasons = []
    reasons += check_metrics_anomaly(db)
    reasons += check_tracking_health(db)
    reasons += check_duplicates(db)
    if check_network:
        reasons += check_links(db)
    # 人間による警告フラグ（アカウント警告など）
    if db.get_setting("account_warning", "0") == "1":
        reasons.append("アカウント警告フラグが立っています")
    for r in reasons:
        halt(db, "auto_check", r)
    return reasons
