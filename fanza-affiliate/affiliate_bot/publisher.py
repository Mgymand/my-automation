"""予定投稿の公開。X 公式 API のみ使用。エラー時は回避せず停止する。"""
from __future__ import annotations

from datetime import datetime, timezone

import requests

from . import compliance, failsafe
from .config import Settings
from .db import Database, utcnow
from .x_client import XError, to_jpy


def _fetch_media(url: str, session: requests.Session) -> tuple[bytes, str]:
    r = session.get(url, timeout=60)
    r.raise_for_status()
    ctype = r.headers.get("Content-Type", "").split(";")[0].strip() or "image/jpeg"
    return r.content, ctype


def publish_due(db: Database, settings: Settings, x, session: requests.Session | None = None,
                now: datetime | None = None) -> list[int]:
    """scheduled_at <= now の投稿を公開する。"""
    now = now or datetime.now(timezone.utc)
    paused, reason = failsafe.is_paused(db)
    if paused:
        db.log_event("warn", "publish_skipped", f"停止中: {reason}")
        return []
    session = session or requests.Session()
    due = db.q("SELECT * FROM posts WHERE status='scheduled' AND scheduled_at<=? ORDER BY scheduled_at",
               (now.isoformat(timespec="seconds"),))
    done: list[int] = []
    for row in due:
        post = dict(row)
        prod = db.one("SELECT * FROM products WHERE content_id=?", (post["product_id"],))
        if not prod:
            db.exec("UPDATE posts SET status='failed', error='product missing' WHERE post_id=?", (post["post_id"],))
            continue
        # 公開直前の最終ゲート（設定が変わっている可能性）
        pol = compliance.check_post(post["text"], post["reply_text"], post["media_source"], bool(prod["is_adult"]), settings)
        if not pol.ok:
            db.exec("UPDATE posts SET status='blocked', error=? WHERE post_id=?", ("; ".join(pol.reasons), post["post_id"]))
            db.log_event("warn", "blocked", f"post {post['post_id']} をブロック", {"reasons": pol.reasons})
            continue
        # 最低投稿間隔
        last = db.one("SELECT posted_at FROM posts WHERE status='posted' ORDER BY posted_at DESC LIMIT 1")
        if last and last["posted_at"]:
            gap = (now - datetime.fromisoformat(last["posted_at"])).total_seconds() / 60
            if gap < settings.min_post_interval_min:
                continue
        try:
            media_ids = []
            if post["media_type"] in ("image", "video") and post["media_source"]:
                if not compliance.media_rights_ok(post["media_source"]):
                    raise XError("media rights unverified")
                cat = "tweet_video" if post["media_type"] == "video" else "tweet_image"
                if settings.dry_run:
                    content, ctype = b"", ("video/mp4" if cat == "tweet_video" else "image/jpeg")
                else:
                    content, ctype = _fetch_media(post["media_source"], session)
                media_ids.append(x.upload_media(content, ctype, cat))
            main = x.create_post(post["text"], media_ids=media_ids or None,
                                 paid_partnership=settings.use_paid_partnership_label)
            cost = main.cost_usd
            reply_id = None
            if post["reply_text"]:
                rep = x.create_post(post["reply_text"], reply_to=main.post_id, paid_partnership=settings.use_paid_partnership_label)
                reply_id = rep.post_id
                cost += rep.cost_usd
            cost_jpy = to_jpy(cost, settings.usd_jpy)
            db.exec("UPDATE posts SET status='posted', posted_at=?, x_post_id=?, x_reply_id=?, api_cost_jpy=? WHERE post_id=?",
                    (utcnow(), main.post_id, reply_id, cost_jpy, post["post_id"]))
            db.exec("UPDATE products SET last_posted_at=? WHERE content_id=?", (utcnow(), post["product_id"]))
            db.add_cost("x_api", cost_jpy, ref=f"post:{post['post_id']}")
            done.append(post["post_id"])
            now = datetime.now(timezone.utc)
        except XError as e:
            db.exec("UPDATE posts SET status='failed', error=? WHERE post_id=?", (str(e)[:300], post["post_id"]))
            if e.is_auth_or_policy or e.is_rate_limit:
                failsafe.halt(db, "x_api_error", f"X API {e.status}: {e.body[:200]}")
                break
            db.log_event("warn", "x_post_failed", str(e), {"post_id": post["post_id"]})
        except requests.RequestException as e:
            db.exec("UPDATE posts SET status='failed', error=? WHERE post_id=?", (str(e)[:300], post["post_id"]))
            db.log_event("warn", "media_fetch_failed", str(e), {"post_id": post["post_id"]})
    return done
