"""X API v2 クライアント（公式 API のみ。画面操作の自動化は行わない）。

- 認証: OAuth 1.0a User Context（標準ライブラリのみで署名）
- 投稿: POST /2/tweets（text, media.media_ids, reply, paid_partnership）
- メディア: POST /2/media/upload/initialize → /append → /finalize → STATUS
- 計測: GET /2/tweets?ids=...&tweet.fields=public_metrics,non_public_metrics
- 調査: GET /2/tweets/search/recent
料金（2026-09 時点の pay-per-use）: 投稿 $0.015、URL 付き投稿 $0.20、ポスト読取 $0.005、
自分のデータ読取 $0.001/リソース。詳細は docs/COMPLIANCE.md。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any

import requests

API = "https://api.x.com/2"
UPLOAD = "https://api.x.com/2/media/upload"

# 料金の既定値（USD）。docs.x.com/x-api/getting-started/pricing より（2026-09 取得）。
# 実際の計算は XClient(pricing=...) / DryRunXClient(pricing=...) に渡した pricing.XPricing を使う
# （環境変数 → DB settings.x_pricing の順で上書き可能。pricing.verify_x_pricing が公式ページと照合する）。
PRICE_POST_USD = 0.015
PRICE_POST_WITH_URL_USD = 0.20
PRICE_READ_POST_USD = 0.005
PRICE_OWNED_READ_USD = 0.001
PRICE_READ_USER_USD = 0.010


class _DefaultPricing:
    post = PRICE_POST_USD
    post_url = PRICE_POST_WITH_URL_USD
    read_post = PRICE_READ_POST_USD
    owned_read = PRICE_OWNED_READ_USD
    read_user = PRICE_READ_USER_USD


class XError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body

    @property
    def is_auth_or_policy(self) -> bool:
        return self.status in (401, 403)

    @property
    def is_rate_limit(self) -> bool:
        return self.status == 429


def _pct(s: str) -> str:
    return urllib.parse.quote(str(s), safe="-._~")


class OAuth1:
    def __init__(self, ck: str, cs: str, at: str, ats: str):
        self.ck, self.cs, self.at, self.ats = ck, cs, at, ats

    def header(self, method: str, url: str, query: dict | None = None) -> str:
        oauth = {
            "oauth_consumer_key": self.ck,
            "oauth_nonce": secrets.token_hex(16),
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_token": self.at,
            "oauth_version": "1.0",
        }
        params = dict(oauth)
        params.update(query or {})
        norm = "&".join(f"{_pct(k)}={_pct(v)}" for k, v in sorted(params.items()))
        base = "&".join([method.upper(), _pct(url), _pct(norm)])
        key = f"{_pct(self.cs)}&{_pct(self.ats)}".encode()
        sig = base64.b64encode(hmac.new(key, base.encode(), hashlib.sha1).digest()).decode()
        oauth["oauth_signature"] = sig
        return "OAuth " + ", ".join(f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(oauth.items()))


@dataclass
class PostResult:
    post_id: str
    text: str
    cost_usd: float


class XClient:
    def __init__(self, ck: str, cs: str, at: str, ats: str, session: requests.Session | None = None, pricing=None):
        if not all([ck, cs, at, ats]):
            raise XError("X API の認証情報が未設定です")
        self.auth = OAuth1(ck, cs, at, ats)
        self.s = session or requests.Session()
        self.pricing = pricing or _DefaultPricing()

    # ---- 低レベル ----
    def _req(self, method: str, url: str, *, params: dict | None = None, json_body: Any = None,
             files: dict | None = None, data: dict | None = None) -> dict:
        # JSON ボディ / multipart は署名対象に含めない。query は含める。
        headers = {"Authorization": self.auth.header(method, url, params)}
        r = self.s.request(method, url, params=params, json=json_body, files=files, data=data,
                           headers=headers, timeout=60)
        if r.status_code >= 400:
            raise XError(f"X API {method} {url} HTTP {r.status_code}", r.status_code, r.text[:500])
        if not r.text:
            return {}
        try:
            return r.json()
        except ValueError:
            return {}

    # ---- 投稿 ----
    def create_post(self, text: str, media_ids: list[str] | None = None, reply_to: str | None = None,
                    paid_partnership: bool = False) -> PostResult:
        body: dict[str, Any] = {"text": text}
        if media_ids:
            body["media"] = {"media_ids": media_ids}
        if reply_to:
            body["reply"] = {"in_reply_to_tweet_id": reply_to}
        if paid_partnership:
            # docs.x.com/x-api/posts/manage-tweets: 有料パートナーシップ（コンテンツ開示）ラベル
            body["paid_partnership"] = True
        data = self._req("POST", f"{API}/tweets", json_body=body)
        d = data.get("data") or {}
        cost = self.pricing.post_url if ("http://" in text or "https://" in text) else self.pricing.post
        return PostResult(post_id=str(d.get("id", "")), text=d.get("text", text), cost_usd=cost)

    def delete_post(self, post_id: str) -> None:
        self._req("DELETE", f"{API}/tweets/{post_id}")

    # ---- メディア ----
    def upload_media(self, content: bytes, media_type: str, category: str = "tweet_image") -> str:
        """チャンクアップロード。category: tweet_image | tweet_gif | tweet_video"""
        init = self._req("POST", f"{UPLOAD}/initialize", json_body={
            "media_type": media_type, "total_bytes": len(content), "media_category": category,
        })
        media_id = str((init.get("data") or init).get("id") or (init.get("data") or init).get("media_id"))
        chunk = 4 * 1024 * 1024
        for i in range(0, max(len(content), 1), chunk):
            self._req("POST", f"{UPLOAD}/{media_id}/append",
                      data={"segment_index": str(i // chunk)},
                      files={"media": ("blob", content[i:i + chunk], media_type)})
        fin = self._req("POST", f"{UPLOAD}/{media_id}/finalize")
        info = (fin.get("data") or fin).get("processing_info")
        # 動画は非同期処理。STATUS をポーリング
        waited = 0
        while info and info.get("state") in ("pending", "in_progress") and waited < 300:
            secs = int(info.get("check_after_secs", 5))
            time.sleep(secs)
            waited += secs
            st = self._req("GET", UPLOAD, params={"command": "STATUS", "media_id": media_id})
            info = (st.get("data") or st).get("processing_info")
        if info and info.get("state") == "failed":
            raise XError(f"media processing failed: {info}")
        return media_id

    # ---- 計測 ----
    def me(self) -> dict:
        return self._req("GET", f"{API}/users/me", params={"user.fields": "public_metrics"})

    def post_metrics(self, ids: list[str]) -> tuple[dict[str, dict], float]:
        """自分の投稿の指標を取得。(post_id -> metrics, cost_usd)"""
        out: dict[str, dict] = {}
        cost = 0.0
        for i in range(0, len(ids), 100):
            batch = ids[i:i + 100]
            data = self._req("GET", f"{API}/tweets", params={
                "ids": ",".join(batch),
                "tweet.fields": "public_metrics,non_public_metrics,created_at",
            })
            for t in data.get("data") or []:
                pm = t.get("public_metrics") or {}
                npm = t.get("non_public_metrics") or {}
                out[str(t["id"])] = {
                    "views": int(pm.get("impression_count") or npm.get("impression_count") or 0),
                    "likes": int(pm.get("like_count") or 0),
                    "reposts": int(pm.get("retweet_count") or 0),
                    "replies": int(pm.get("reply_count") or 0),
                    "quotes": int(pm.get("quote_count") or 0),
                    "bookmarks": int(pm.get("bookmark_count") or 0),
                    "profile_visits": int(npm.get("user_profile_clicks") or 0),
                    "url_clicks": int(npm.get("url_link_clicks") or 0),
                }
            cost += self.pricing.owned_read * len(batch)
        return out, cost

    def search_recent(self, query: str, max_results: int = 50, next_token: str | None = None) -> tuple[dict, float]:
        """市場調査用。公開ポストの検索（$0.005/ポスト + 著者 $0.01/ユーザー）。"""
        params = {
            "query": query,
            "max_results": max(10, min(max_results, 100)),
            "tweet.fields": "public_metrics,created_at,attachments,entities,possibly_sensitive",
            "expansions": "author_id,attachments.media_keys",
            "user.fields": "public_metrics",
            "media.fields": "type",
        }
        if next_token:
            params["next_token"] = next_token
        data = self._req("GET", f"{API}/tweets/search/recent", params=params)
        n_posts = len(data.get("data") or [])
        n_users = len((data.get("includes") or {}).get("users") or [])
        return data, self.pricing.read_post * n_posts + self.pricing.read_user * n_users


class DryRunXClient:
    """DRY_RUN 用。API を呼ばず、ログだけ残す。"""

    def __init__(self, pricing=None):
        self.calls: list[dict] = []
        self._n = 0
        self.pricing = pricing or _DefaultPricing()

    def create_post(self, text: str, media_ids=None, reply_to=None, paid_partnership=False) -> PostResult:
        self._n += 1
        self.calls.append({"op": "create_post", "text": text, "media_ids": media_ids, "reply_to": reply_to,
                           "paid_partnership": paid_partnership})
        cost = self.pricing.post_url if "http" in text else self.pricing.post
        return PostResult(post_id=f"dry-{int(time.time())}-{self._n}", text=text, cost_usd=cost)

    def upload_media(self, content: bytes, media_type: str, category: str = "tweet_image") -> str:
        self._n += 1
        self.calls.append({"op": "upload_media", "bytes": len(content), "media_type": media_type, "category": category})
        return f"dry-media-{self._n}"

    def post_metrics(self, ids):
        return {}, 0.0

    def me(self):
        return {"data": {"id": "0", "username": "dryrun"}}

    def search_recent(self, query, max_results=50, next_token=None):
        return {"data": [], "includes": {}}, 0.0

    def delete_post(self, post_id):
        self.calls.append({"op": "delete_post", "id": post_id})


def to_jpy(usd: float, rate: float) -> float:
    return round(usd * rate, 3)
