"""人間が投稿した後の登録: `posted --url URL`。

- URL / ID から Post ID を解析し、本日（または直近）の planned パッケージへ紐付ける
  （--post N 指定 / 未指定なら未登録の中で予定時刻が現在に最も近いもの）
- 実際の本文・時刻・素材が予定と違う場合は actual_* に記録
- X 読取が使えれば投稿を取得して actual_text / actual_post_time を自動補完
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .config import Settings
from .db import Database, utcnow
from .x_client import parse_post_id


def register(db: Database, settings: Settings, url_or_id: str, seq: int | None = None, day: str | None = None,
             actual_text: str | None = None, actual_time: str | None = None, actual_media: str | None = None, x=None) -> dict:
    pid = parse_post_id(url_or_id)
    if not pid:
        raise ValueError("Post ID を URL / 文字列から解析できません（例: https://x.com/user/status/123…）")
    tz = ZoneInfo(settings.timezone)
    day = day or datetime.now(tz).strftime("%Y-%m-%d")
    if db.one("SELECT 1 FROM posts WHERE x_post_id=?", (pid,)):
        raise ValueError(f"Post ID {pid} は登録済みです")
    if seq is not None:
        row = db.one("SELECT * FROM posts WHERE day=? AND seq=? ", (day, seq))
    else:
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        row = db.one("""SELECT * FROM posts WHERE status='planned' AND day<=? ORDER BY ABS(strftime('%s',scheduled_at)-strftime('%s',?)) LIMIT 1""",
                     (day, now_iso))
    if not row:
        raise ValueError("紐付ける予定投稿がありません（plan を実行するか --post N を指定）")
    url = url_or_id if url_or_id.startswith("http") else None
    posted_at = utcnow()
    fetched = None
    if x is not None:
        try:
            posts, cost = x.posts([pid], owned=True)
            if posts:
                fetched = posts[0]
                if cost:
                    db.add_cost("x_api", round(cost * settings.usd_jpy, 3), ref=f"posted:{pid}")
        except Exception as e:  # noqa: BLE001
            db.log_event("warn", "posted_fetch_failed", f"{pid}: {e.__class__.__name__}")
    if fetched:
        actual_text = actual_text or (fetched["text"] if fetched["text"].strip() != row["text"].strip() else None)
        actual_time = actual_time or fetched.get("created_at")
        if fetched.get("media_types") and not actual_media:
            actual_media = ",".join(fetched["media_types"])
        if fetched.get("author_username") and not url:
            url = f"https://x.com/{fetched['author_username']}/status/{pid}"
        if fetched.get("created_at"):
            posted_at = fetched["created_at"].replace("Z", "+00:00")
    db.exec("""UPDATE posts SET status='posted', x_post_id=?, x_url=?, posted_at=?, actual_text=?, actual_post_time=?, actual_media=?
               WHERE post_id=?""",
            (pid, url, posted_at, actual_text, actual_time, actual_media, row["post_id"]))
    db.exec("UPDATE products SET last_posted_at=? WHERE content_id=?", (posted_at, row["product_id"]))
    if fetched:
        db.exec("""INSERT INTO post_metrics(post_id,captured_at,milestone_hours,source,views,likes,reposts,replies,quotes,bookmarks)
                   VALUES(?,?,0,'x_api',?,?,?,?,?,?)""",
                (row["post_id"], utcnow(), fetched["views"], fetched["likes"], fetched["reposts"], fetched["replies"], fetched["quotes"], fetched["bookmarks"]))
    db.log_event("info", "posted", f"POST {row['seq']}（{row['day']}）を {pid} に紐付け", {"post_id": row["post_id"]})
    return {"post_id": row["post_id"], "day": row["day"], "seq": row["seq"], "product_id": row["product_id"], "pattern_id": row["pattern_id"],
            "x_post_id": pid, "x_url": url, "posted_at": posted_at, "actual_text": actual_text, "actual_post_time": actual_time,
            "actual_media": actual_media}


def skip(db: Database, day: str, seq: int, reason: str = "") -> None:
    db.exec("UPDATE posts SET status='skipped', notes=json_insert(COALESCE(notes,'[]'),'$[#]',?) WHERE day=? AND seq=? AND status='planned'",
            (f"skipped: {reason}", day, seq))
