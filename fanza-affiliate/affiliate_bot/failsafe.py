"""自動停止ルール。条件に該当したら settings.paused=1 にして人間レビューへ回す。
回避策は考えない。原因を解決してから `cli resume` で再開する。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from . import attention
from .config import Settings
from .db import Database

# 停止コード → Attention Queue のカテゴリ
HALT_CATEGORY = {
    "x_api_error": "auth_expired", "x_billing": "billing_cap", "ctr_drop": "metric_anomaly", "cvr_drop": "metric_anomaly",
    "tracking": "tracking_failure", "link": "tracking_failure", "duplicate": "prod_outage", "account_warning": "account_warning",
    "manual": "account_warning", "auto_check": "prod_outage", "policy": "policy_change",
}

MIN_VIEWS_FOR_CTR_CHECK = 5000
MIN_CLICKS_FOR_CVR_CHECK = 100
DROP_RATIO = 0.5   # 直近 3 日が過去 14 日の半分未満なら異常


def is_paused(db: Database) -> tuple[bool, str]:
    return db.get_setting("paused", "0") == "1", db.get_setting("paused_reason", "") or ""


def halt(db: Database, code: str, message: str, data: dict | None = None, category: str | None = None) -> None:
    db.set_setting("paused", "1")
    db.set_setting("paused_reason", f"{code}: {message}")
    db.log_event("halt", code, message, data)
    attention.raise_item(db, category or HALT_CATEGORY.get(code, "prod_outage"), f"自動停止: {message[:80]}",
                         detail=str(data or ""), action="原因を解決してから `python -m affiliate_bot resume`",
                         severity="critical", dedupe_key=f"halt:{code}")


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
            reasons.append(("ctr_drop", f"CTR 異常低下 {b_ctr:.4f}→{r_ctr:.4f}"))
    if recent["clicks"] >= MIN_CLICKS_FOR_CVR_CHECK and base["clicks"] >= MIN_CLICKS_FOR_CVR_CHECK:
        r_cvr = recent["conv"] / recent["clicks"]
        b_cvr = base["conv"] / base["clicks"]
        if b_cvr > 0 and r_cvr < b_cvr * DROP_RATIO:
            reasons.append(("cvr_drop", f"CVR 異常低下 {b_cvr:.4f}→{r_cvr:.4f}"))
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
        return [("tracking", f"トラッキング障害の疑い: X url_clicks={row['xc']} に対し自前クリック 0")]
    return []


def check_tracking_endpoint(settings: Settings, session: requests.Session | None = None) -> list[tuple[str, str]]:
    """トラッキング URL の healthz と署名付きリダイレクトの動作確認（本番障害検知）。"""
    if not settings.tracking_base_url:
        return []
    from .tracking import sign_payload, tracking_mode
    s = session or requests.Session()
    base = settings.tracking_base_url.rstrip("/")
    try:
        r = s.get(f"{base}/healthz", timeout=15)
        if r.status_code != 200:
            return [("tracking", f"トラッキング healthz HTTP {r.status_code}")]
        if tracking_mode(settings) == "stateless":
            tok = sign_payload(settings.tracking_secret, "chk", "https://www.dmm.com/")
            r = s.get(f"{base}/r/{tok}", timeout=15, allow_redirects=False)
            if r.status_code not in (301, 302, 307, 308):
                return [("tracking", f"署名付きリダイレクトが失敗 HTTP {r.status_code}（TRACKING_SECRET の不一致?）")]
    except requests.RequestException as e:
        return [("tracking", f"トラッキング到達不能: {e.__class__.__name__}")]
    return []


def check_duplicates(db: Database) -> list[str]:
    row = db.one(
        """SELECT text, COUNT(*) c FROM posts WHERE status IN('posted','scheduled')
           AND created_at >= datetime('now','-3 days') GROUP BY text HAVING c>=2 LIMIT 1"""
    )
    return [("duplicate", f"同一本文の重複投稿を検出: {row['text'][:40]}…")] if row else []


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
            bad.append(("link", "アフィリエイト URL が空"))
            continue
        try:
            resp = s.get(url, timeout=15, allow_redirects=True, stream=True)
            if resp.status_code >= 400:
                bad.append(("link", f"リンク障害 HTTP {resp.status_code}: {url[:60]}"))
        except requests.RequestException as e:
            bad.append(("link", f"リンク障害: {e.__class__.__name__}"))
    return bad


def run_checks(db: Database, settings: Settings, check_network: bool = False) -> list[str]:
    reasons: list[tuple[str, str]] = []
    reasons += check_metrics_anomaly(db)
    reasons += check_tracking_health(db)
    reasons += check_duplicates(db)
    if check_network:
        reasons += check_links(db)
        reasons += check_tracking_endpoint(settings)
    # 人間による警告フラグ（アカウント警告など）
    if db.get_setting("account_warning", "0") == "1":
        reasons.append(("account_warning", "アカウント警告フラグが立っています"))
    for code, msg in reasons:
        halt(db, code, msg)
    attention.check_profit_negative(db)
    return [m for _, m in reasons]
