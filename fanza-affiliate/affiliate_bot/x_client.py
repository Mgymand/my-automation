"""X API v2 クライアント — **READ ONLY**。

Phase 3 の方針により、このモジュールには投稿・メディアアップロード・削除など書込系のメソッドは存在しない
（tests/test_phase3_policy.py が書込エンドポイントの不在を検証する）。
認証: App-only Bearer Token（`X_BEARER_TOKEN`）。投稿権限（tweet.write）は不要。
用途:
- 公開投稿の検索（市場調査）: GET /2/tweets/search/recent
- 自分の投稿の指標取得: GET /2/tweets?ids=…（public_metrics に impression_count を含む）
- ユーザー情報: GET /2/users/by/username/:name
料金（pay-per-use, 2026-09）: ポスト読取 $0.005、ユーザー読取 $0.010、自分のデータ読取 $0.001（pricing.py で上書き可）。
"""
from __future__ import annotations

import re
from typing import Any

import requests

API = "https://api.x.com/2"
POST_FIELDS = "public_metrics,created_at,entities,attachments,possibly_sensitive,author_id"
EXPANSIONS = "author_id,attachments.media_keys"
USER_FIELDS = "public_metrics,username,created_at"
MEDIA_FIELDS = "type,duration_ms,public_metrics"

PRICE_READ_POST_USD = 0.005
PRICE_OWNED_READ_USD = 0.001
PRICE_READ_USER_USD = 0.010

POST_URL_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:x|twitter)\.com/(?:i/web/|[A-Za-z0-9_]{1,15}/)status(?:es)?/(\d{5,25})")


class XError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body

    @property
    def is_auth(self) -> bool:
        return self.status in (401, 403)

    @property
    def is_rate_limit(self) -> bool:
        return self.status == 429


class _DefaultPricing:
    read_post = PRICE_READ_POST_USD
    owned_read = PRICE_OWNED_READ_USD
    read_user = PRICE_READ_USER_USD


def parse_post_id(url_or_id: str) -> str | None:
    """X の投稿 URL または ID 文字列から Post ID を取り出す。"""
    s = (url_or_id or "").strip()
    if re.fullmatch(r"\d{5,25}", s):
        return s
    m = POST_URL_RE.search(s)
    return m.group(1) if m else None


def normalize_post(t: dict, users: dict[str, dict], media: dict[str, dict]) -> dict:
    """API の投稿 JSON を共通形式へ。"""
    pm = t.get("public_metrics") or {}
    u = users.get(str(t.get("author_id")), {})
    keys = (t.get("attachments") or {}).get("media_keys") or []
    medias = [media.get(k, {}) for k in keys]
    mtypes = [m.get("type") for m in medias if m]
    video_ms = max((int(m.get("duration_ms") or 0) for m in medias if m), default=0)
    ents = t.get("entities") or {}
    urls = [x.get("expanded_url") or x.get("url") for x in ents.get("urls", [])]
    return {
        "x_post_id": str(t.get("id")),
        "author_id": str(t.get("author_id") or ""),
        "author_username": u.get("username"),
        "author_followers": int((u.get("public_metrics") or {}).get("followers_count") or 0),
        "text": t.get("text") or "",
        "created_at": t.get("created_at"),
        "views": int(pm.get("impression_count") or 0),
        "likes": int(pm.get("like_count") or 0),
        "reposts": int(pm.get("retweet_count") or 0),
        "replies": int(pm.get("reply_count") or 0),
        "quotes": int(pm.get("quote_count") or 0),
        "bookmarks": int(pm.get("bookmark_count") or 0),
        "media_types": mtypes,
        "image_count": sum(1 for m in mtypes if m == "photo"),
        "has_video": any(m in ("video", "animated_gif") for m in mtypes),
        "video_seconds": round(video_ms / 1000, 1) if video_ms else 0.0,
        "urls": urls,
        "hashtags": [h.get("tag") for h in ents.get("hashtags", [])],
        "possibly_sensitive": bool(t.get("possibly_sensitive")),
    }


class XReadClient:
    def __init__(self, bearer_token: str, session: requests.Session | None = None, pricing=None):
        if not bearer_token:
            raise XError("X_BEARER_TOKEN が未設定です")
        self.s = session or requests.Session()
        self.s.headers["Authorization"] = f"Bearer {bearer_token}"
        self.pricing = pricing or _DefaultPricing()

    def _get(self, path: str, params: dict[str, Any]) -> dict:
        r = self.s.get(f"{API}{path}", params=params, timeout=60)
        if r.status_code >= 400:
            raise XError(f"X API GET {path} HTTP {r.status_code}", r.status_code, r.text[:500])
        return r.json() if r.text else {}

    @staticmethod
    def _includes(data: dict) -> tuple[dict, dict]:
        inc = data.get("includes") or {}
        users = {str(u["id"]): u for u in inc.get("users", [])}
        media = {m["media_key"]: m for m in inc.get("media", [])}
        return users, media

    def user_by_username(self, username: str) -> dict:
        data = self._get(f"/users/by/username/{username.lstrip('@')}", {"user.fields": USER_FIELDS})
        return data.get("data") or {}

    def posts(self, ids: list[str], owned: bool = False) -> tuple[list[dict], float]:
        """投稿の取得（指標・著者・メディア含む）。owned=True は自分の投稿（安価な読取）。"""
        out: list[dict] = []
        cost = 0.0
        for i in range(0, len(ids), 100):
            batch = ids[i:i + 100]
            data = self._get("/tweets", {"ids": ",".join(batch), "tweet.fields": POST_FIELDS, "expansions": EXPANSIONS,
                                         "user.fields": USER_FIELDS, "media.fields": MEDIA_FIELDS})
            users, media = self._includes(data)
            out += [normalize_post(t, users, media) for t in data.get("data") or []]
            cost += (self.pricing.owned_read if owned else self.pricing.read_post) * len(batch)
        return out, cost

    def search_recent(self, query: str, max_results: int = 50, next_token: str | None = None) -> tuple[list[dict], str | None, float]:
        params = {"query": query, "max_results": max(10, min(max_results, 100)), "tweet.fields": POST_FIELDS,
                  "expansions": EXPANSIONS, "user.fields": USER_FIELDS, "media.fields": MEDIA_FIELDS}
        if next_token:
            params["next_token"] = next_token
        data = self._get("/tweets/search/recent", params)
        users, media = self._includes(data)
        posts = [normalize_post(t, users, media) for t in data.get("data") or []]
        cost = self.pricing.read_post * len(posts) + self.pricing.read_user * len(users)
        return posts, (data.get("meta") or {}).get("next_token"), cost


class DryRunXClient:
    """X 認証がない環境用。何も取得しない。"""

    def __init__(self, pricing=None):
        self.pricing = pricing or _DefaultPricing()

    def user_by_username(self, username):
        return {}

    def posts(self, ids, owned=False):
        return [], 0.0

    def search_recent(self, query, max_results=50, next_token=None):
        return [], None, 0.0


def to_jpy(usd: float, rate: float) -> float:
    return round(usd * rate, 3)
