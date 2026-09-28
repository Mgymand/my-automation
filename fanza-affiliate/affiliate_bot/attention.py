"""Human Attention Queue。

通常運用では人間に何も報告しない。以下のカテゴリのみ起票し、通知（Slack Webhook / stdout）する。
  auth_expired       API 認証失効（X/DMM/Anthropic の 401/403）
  policy_change      規約変更の検知（policy.verify_policy / 価格変更）
  account_warning    アカウント警告（人間フラグ or X API 403 with policy text）
  review_needed      審査対応（媒体登録の非承認・再申請）
  billing_cap        課金上限（AI 日次予算の連続超過・X クレジット不足 402/429）
  metric_anomaly     異常な CTR/CVR
  tracking_failure   トラッキング障害
  policy_undecidable ポリシー判定不能（成人向けか判定できない商品・センシティブ設定未確認）
  profit_negative    利益が一定期間マイナス
  prod_outage        本番環境障害（ループ連続エラー・トラッキング healthz 失敗・デプロイ失敗）
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import requests

from .config import Settings
from .db import Database, utcnow

CATEGORIES = {
    "auth_expired", "policy_change", "account_warning", "review_needed", "billing_cap", "metric_anomaly",
    "tracking_failure", "policy_undecidable", "profit_negative", "prod_outage",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS attention_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  category TEXT NOT NULL,
  severity TEXT NOT NULL,          -- info|warn|critical
  title TEXT NOT NULL,
  detail TEXT,
  action TEXT,                     -- 人間がやること（1〜2 行）
  status TEXT NOT NULL DEFAULT 'open',  -- open|acked|resolved
  notified_at TEXT,
  resolved_at TEXT,
  dedupe_key TEXT
);
CREATE INDEX IF NOT EXISTS idx_attention_status ON attention_queue(status, category);
"""


def ensure_schema(db: Database) -> None:
    db.conn.executescript(SCHEMA)


def raise_item(db: Database, category: str, title: str, detail: str = "", action: str = "",
               severity: str = "warn", dedupe_key: str | None = None) -> int | None:
    """起票。同じ dedupe_key の open 項目があれば再起票しない（None を返す）。"""
    assert category in CATEGORIES, category
    ensure_schema(db)
    key = dedupe_key or f"{category}:{title}"
    if db.one("SELECT id FROM attention_queue WHERE dedupe_key=? AND status='open'", (key,)):
        return None
    cur = db.exec(
        "INSERT INTO attention_queue(ts,category,severity,title,detail,action,status,dedupe_key) VALUES(?,?,?,?,?,?,?,?)",
        (utcnow(), category, severity, title, detail[:2000], action[:500], "open", key),
    )
    db.log_event("warn", f"attention:{category}", title, {"id": cur.lastrowid})
    return cur.lastrowid


def open_items(db: Database) -> list[dict]:
    ensure_schema(db)
    return [dict(r) for r in db.q("SELECT * FROM attention_queue WHERE status='open' ORDER BY id")]


def resolve(db: Database, item_id: int) -> None:
    ensure_schema(db)
    db.exec("UPDATE attention_queue SET status='resolved', resolved_at=? WHERE id=?", (utcnow(), item_id))


def resolve_by_category(db: Database, category: str) -> int:
    ensure_schema(db)
    cur = db.exec("UPDATE attention_queue SET status='resolved', resolved_at=? WHERE status='open' AND category=?",
                  (utcnow(), category))
    return cur.rowcount


def notify_pending(db: Database, settings: Settings, session: requests.Session | None = None) -> int:
    """未通知の open 項目を通知する。Slack Webhook がなければ stdout（cron ログ）に出す。"""
    ensure_schema(db)
    rows = db.q("SELECT * FROM attention_queue WHERE status='open' AND notified_at IS NULL ORDER BY id")
    if not rows:
        return 0
    lines = [f"[{r['severity']}] {r['category']}: {r['title']}" + (f"\n  → {r['action']}" if r['action'] else "") for r in rows]
    text = "【要対応】affiliate-bot\n" + "\n".join(lines)
    sent = False
    if settings.slack_webhook_url:
        s = session or requests.Session()
        try:
            r = s.post(settings.slack_webhook_url, json={"text": text}, timeout=15)
            sent = r.status_code < 300
        except requests.RequestException:
            sent = False
    if not sent:
        print(text)
    now = utcnow()
    for r in rows:
        db.exec("UPDATE attention_queue SET notified_at=? WHERE id=?", (now, r["id"]))
    return len(rows)


def check_profit_negative(db: Database, days: int = 7, min_posts: int = 20) -> None:
    """一定期間の利益がマイナスなら起票。サンプルが少ない場合は判定しない。"""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    row = db.one(
        """SELECT COUNT(*) n,
             COALESCE(SUM((SELECT COALESCE(SUM(revenue_jpy),0) FROM conversions cv WHERE cv.post_id=p.post_id)),0) rev,
             COALESCE(SUM(p.api_cost_jpy + p.ai_cost_jpy),0) cost
           FROM posts p WHERE p.status='posted' AND p.posted_at>=?""", (since,))
    if not row or row["n"] < min_posts:
        return
    infra = float(db.get_setting("infra_cost_day_jpy", "0") or 0) * days
    profit = row["rev"] - row["cost"] - infra
    if profit < 0:
        raise_item(db, "profit_negative", f"直近 {days} 日の利益がマイナス（{profit:,.0f} 円, 投稿 {row['n']} 件）",
                   detail=json.dumps({"revenue": row["rev"], "cost": row["cost"], "infra": infra}),
                   action="経営判断: 継続 / 投稿数・予算の見直し / 停止。週次レビューの提案を確認",
                   severity="critical", dedupe_key=f"profit_negative:{days}d")
