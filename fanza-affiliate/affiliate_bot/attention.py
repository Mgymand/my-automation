"""Human Attention Queue（Phase 3）。

通常運用では人間に何も報告しない。以下のカテゴリのみ起票・通知する:
  fanza_auth           FANZA API 認証失効
  x_read_auth          X READ API 認証失効
  policy_change        規約変更（policy.verify_policy / 価格変更）
  media_rights         素材権利が判断できない
  product_inconsistency 商品情報の不整合
  csv_ingest_failed    成果 CSV 取込失敗
  data_stale           7 日以上データ取得不能（指標 / 成果 / 商品）
  profit_negative      利益が一定期間マイナス
  prod_outage          本番システム障害
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import requests

from .config import Settings
from .db import Database, utcnow

CATEGORIES = {"fanza_auth", "x_read_auth", "policy_change", "media_rights", "product_inconsistency", "csv_ingest_failed",
              "data_stale", "profit_negative", "prod_outage"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS attention_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, category TEXT NOT NULL, severity TEXT NOT NULL,
  title TEXT NOT NULL, detail TEXT, action TEXT, status TEXT NOT NULL DEFAULT 'open', notified_at TEXT, resolved_at TEXT, dedupe_key TEXT
);
CREATE INDEX IF NOT EXISTS idx_attention_status ON attention_queue(status, category);
"""


def ensure_schema(db: Database) -> None:
    db.conn.executescript(SCHEMA)


def raise_item(db: Database, category: str, title: str, detail: str = "", action: str = "", severity: str = "warn",
               dedupe_key: str | None = None) -> int | None:
    assert category in CATEGORIES, category
    ensure_schema(db)
    key = dedupe_key or f"{category}:{title}"
    if db.one("SELECT id FROM attention_queue WHERE dedupe_key=? AND status='open'", (key,)):
        return None
    cur = db.exec("INSERT INTO attention_queue(ts,category,severity,title,detail,action,status,dedupe_key) VALUES(?,?,?,?,?,?,?,?)",
                  (utcnow(), category, severity, title, detail[:2000], action[:500], "open", key))
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
    return db.exec("UPDATE attention_queue SET status='resolved', resolved_at=? WHERE status='open' AND category=?", (utcnow(), category)).rowcount


def notify_pending(db: Database, settings: Settings, session: requests.Session | None = None) -> int:
    """Slack 成功時のみ配送確定。console は NOTIFY_CONSOLE_DELIVERY=true のときだけ配送成功とみなす。"""
    ensure_schema(db)
    rows = db.q("SELECT * FROM attention_queue WHERE status='open' AND notified_at IS NULL ORDER BY id")
    if not rows:
        return 0
    text = "【要対応】affiliate-bot\n" + "\n".join(
        f"[{r['severity']}] {r['category']}: {r['title']}" + (f"\n  → {r['action']}" if r["action"] else "") for r in rows)
    delivered = False
    if settings.slack_webhook_url:
        s = session or requests.Session()
        try:
            r = s.post(settings.slack_webhook_url, json={"text": text}, timeout=15)
            delivered = r.status_code < 300
            if not delivered:
                db.log_event("warn", "notify_failed", f"Slack HTTP {r.status_code}（次回再送）")
        except requests.RequestException as e:
            db.log_event("warn", "notify_failed", f"Slack {e.__class__.__name__}（次回再送）")
    if not delivered:
        print(text)
        delivered = settings.notify_console_delivery
        if not delivered and not db.get_setting("notify_channel_warned"):
            db.log_event("warn", "notify_channel_missing", "SLACK_WEBHOOK_URL を設定するか、stdout を監視している場合は NOTIFY_CONSOLE_DELIVERY=true")
            db.set_setting("notify_channel_warned", "1")
    if not delivered:
        return 0
    now = utcnow()
    for r in rows:
        db.exec("UPDATE attention_queue SET notified_at=? WHERE id=?", (now, r["id"]))
    return len(rows)


# ---- 検知ルール（failsafe から呼ばれる）----
def check_profit_negative(db: Database, days: int = 7, min_posts: int = 20) -> None:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    row = db.one("""SELECT COUNT(*) n,
                      COALESCE(SUM((SELECT COALESCE(SUM(revenue_jpy*attribution_share),0) FROM conversions cv WHERE cv.post_id=p.post_id)),0) rev,
                      COALESCE(SUM(p.api_cost_jpy + p.ai_cost_jpy),0) cost
                    FROM posts p WHERE p.status='posted' AND p.posted_at>=?""", (since,))
    if not row or row["n"] < min_posts:
        return
    ai = db.cost_between(since, utcnow(), "ai")
    profit = row["rev"] - ai - row["cost"]
    if profit < 0:
        raise_item(db, "profit_negative", f"直近 {days} 日の利益がマイナス（{profit:,.0f} 円, 投稿 {row['n']} 件）",
                   detail=json.dumps({"revenue": row["rev"], "ai": ai}), action="経営判断: 継続 / 投稿数・予算の見直し / 停止。週次レビューの提案を確認",
                   severity="critical", dedupe_key=f"profit_negative:{days}d")


def check_data_stale(db: Database, days: int = 7) -> None:
    limit = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    posted = db.one("SELECT COUNT(*) c FROM posts WHERE status='posted' AND posted_at>=?", (limit,))
    if posted and posted["c"] > 0:
        m = db.one("SELECT COUNT(*) c FROM post_metrics WHERE captured_at>=?", (limit,))
        if not m or m["c"] == 0:
            raise_item(db, "data_stale", f"{days} 日以上、投稿指標が取得できていません",
                       action="X_BEARER_TOKEN を確認するか `metrics --csv` / `metrics --manual` で入力", severity="warn", dedupe_key="metrics_stale")
    fetched = db.one("SELECT MAX(fetched_at) f FROM products")
    if fetched and fetched["f"] and fetched["f"] < limit:
        raise_item(db, "data_stale", f"{days} 日以上、FANZA 商品情報が更新されていません", action="`fetch-products` の失敗ログを確認",
                   severity="warn", dedupe_key="products_stale")
