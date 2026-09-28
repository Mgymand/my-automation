"""素材（画像・動画）の候補化と権利記録。

- 優先: FANZA/DMM が API で返す公式素材（sample_image_urls / sample_movie_url / package image）→ rights_status=ok
- それ以外の URL（他者の投稿から取得した画像・動画など）は登録しない（転載禁止）
- AI 生成素材はタイトルカード・ランキングカード・比較カード・告知カード・背景・非写実的な補助デザインに限る。
  出演者本人の映像/写真や作品の場面と誤認させるもの、作品内容の虚偽表現は禁止（rights_status=ok, source_type=ai_card, note に用途）
"""
from __future__ import annotations

from .compliance import media_rights_ok
from .db import Database, loads, utcnow

AI_CARD_ALLOWED_USES = ("title_card", "ranking_card", "comparison_card", "campaign_card", "background", "abstract_design")


def register_official_assets(db: Database, product: dict) -> int:
    """商品の公式素材を media_assets に登録する。"""
    pid = product["content_id"]
    n = 0
    imgs = product.get("sample_image_urls")
    imgs = loads(imgs, []) if isinstance(imgs, str) else (imgs or [])
    for url in imgs[:6]:
        n += _add(db, pid, url, "sample_image", "image")
    if product.get("sample_movie_url"):
        n += _add(db, pid, product["sample_movie_url"], "sample_movie", "video")
    if product.get("image_url"):
        n += _add(db, pid, product["image_url"], "package", "image")
    return n


def _add(db: Database, pid: str, url: str, source_type: str, kind: str, note: str = "") -> int:
    if not url:
        return 0
    status = "ok" if media_rights_ok(url) else "ng"
    if status == "ng":
        db.log_event("warn", "media_rights_ng", f"{pid}: DMM 提供外の URL は登録しない", {"url": url[:120]})
        return 0
    cur = db.exec(
        "INSERT OR IGNORE INTO media_assets(product_id,source_url,source_type,rights_status,media_kind,note,created_at) VALUES(?,?,?,?,?,?,?)",
        (pid, url, source_type, status, kind, note, utcnow()))
    return cur.rowcount


def register_ai_card(db: Database, pid: str, url_or_path: str, use: str, note: str = "") -> int:
    if use not in AI_CARD_ALLOWED_USES:
        raise ValueError(f"AI 素材の用途 {use} は許可されていません: {AI_CARD_ALLOWED_USES}")
    cur = db.exec(
        "INSERT OR IGNORE INTO media_assets(product_id,source_url,source_type,rights_status,media_kind,note,created_at) VALUES(?,?,?,?,?,?,?)",
        (pid, url_or_path, "ai_card", "ok", "image", f"{use}: {note}（出演者本人・作品場面と誤認させない補助デザイン）", utcnow()))
    return cur.rowcount


def pick_asset(db: Database, pid: str, prefer: str = "image") -> dict | None:
    """パターンの推奨メディアに合う公式素材を 1 つ選ぶ。動画希望で動画が無ければ画像。"""
    order = ["sample_movie", "sample_image", "package"] if prefer == "video" else ["sample_image", "package", "sample_movie"]
    for st in order:
        r = db.one("SELECT * FROM media_assets WHERE product_id=? AND source_type=? AND rights_status='ok' ORDER BY id LIMIT 1", (pid, st))
        if r:
            return dict(r)
    return None


def assets_for(db: Database, pid: str) -> list[dict]:
    return [dict(r) for r in db.q("SELECT * FROM media_assets WHERE product_id=? ORDER BY source_type, id", (pid,))]
