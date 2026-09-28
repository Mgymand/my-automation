"""API 価格の設定・検証。価格はコードに固定せず、環境変数 → DB（settings.x_pricing）の順で上書きできる。

- X API 価格: docs.x.com/x-api/getting-started/pricing を取得して既知ラベルの数値を抽出し、
  設定値と差があれば DB に保存して events / Attention Queue へ記録する（利益計算が古い価格で壊れないようにする）。
- LLM 価格: `LLM_PRICING_JSON`（{"model": {"in":..,"out":..,"cache":..}} USD/1M tok）で上書き可能。
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

import requests

from .config import Settings

X_PRICING_URL = "https://docs.x.com/x-api/getting-started/pricing"

# ページ上のラベル → 設定キー。ラベル表記が変わると抽出できないため、その場合は「未検証」として扱う
X_LABELS = {
    "post": ["Post creation", "Create Post", "Post create"],
    "post_url": ["Post with URL", "Post containing a link", "with link"],
    "read_post": ["Posts", "Post read"],
    "owned_read": ["Owned Reads", "Owned read"],
    "read_user": ["Users"],
}


@dataclass
class XPricing:
    post: float
    post_url: float
    read_post: float
    owned_read: float
    read_user: float
    source: str = "env"

    def as_dict(self) -> dict:
        return {"post": self.post, "post_url": self.post_url, "read_post": self.read_post,
                "owned_read": self.owned_read, "read_user": self.read_user, "source": self.source}


def x_pricing(settings: Settings, db=None) -> XPricing:
    p = XPricing(settings.x_price_post_usd, settings.x_price_post_url_usd, settings.x_price_read_post_usd,
                 settings.x_price_owned_read_usd, settings.x_price_read_user_usd, "env")
    if db is not None:
        raw = db.get_setting("x_pricing")
        if raw:
            try:
                d = json.loads(raw)
                return XPricing(float(d["post"]), float(d["post_url"]), float(d["read_post"]),
                                float(d["owned_read"]), float(d["read_user"]), d.get("source", "db"))
            except (ValueError, KeyError, TypeError):
                pass
    return p


def _extract_price(text: str, labels: list[str]) -> float | None:
    for lab in labels:
        m = re.search(re.escape(lab) + r"[^$]{0,80}\$\s*([0-9]+(?:\.[0-9]+)?)", text, flags=re.I)
        if m:
            return float(m.group(1))
    return None


def verify_x_pricing(settings: Settings, db, session: requests.Session | None = None) -> dict:
    """公式価格ページを取得して差分を検出する。取得・抽出できなければ現在値を維持し status=unverified。"""
    s = session or requests.Session()
    current = x_pricing(settings, db)
    try:
        r = s.get(X_PRICING_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0 (compatible; affiliate-bot)"})
        if r.status_code != 200:
            return {"status": "unverified", "reason": f"HTTP {r.status_code}", "pricing": current.as_dict()}
        text = re.sub(r"<[^>]+>", " ", r.text)
        text = re.sub(r"\s+", " ", text)
    except requests.RequestException as e:
        return {"status": "unverified", "reason": e.__class__.__name__, "pricing": current.as_dict()}
    found = {k: _extract_price(text, v) for k, v in X_LABELS.items()}
    if found["post"] is None or found["post_url"] is None:
        return {"status": "unverified", "reason": "ラベル抽出失敗（ページ構成変更の可能性）", "pricing": current.as_dict(), "found": found}
    new = XPricing(found["post"], found["post_url"], found["read_post"] or current.read_post,
                   found["owned_read"] or current.owned_read, found["read_user"] or current.read_user, "official_page")
    changed = {k: (getattr(current, k), getattr(new, k)) for k in ("post", "post_url", "read_post", "owned_read", "read_user")
               if abs(getattr(current, k) - getattr(new, k)) > 1e-9}
    db.set_setting("x_pricing", json.dumps(new.as_dict()))
    db.set_setting("x_pricing_verified_at", __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds"))
    if changed:
        db.log_event("warn", "x_pricing_changed", f"X API 価格の変更を検出: {changed}", {"changed": changed})
    return {"status": "changed" if changed else "ok", "pricing": new.as_dict(), "changed": changed}


def llm_pricing_overrides() -> dict:
    raw = os.environ.get("LLM_PRICING_JSON", "").strip()
    if not raw:
        return {}
    try:
        d = json.loads(raw)
        return {k: {"in": float(v["in"]), "out": float(v["out"]), "cache": float(v.get("cache", 0))} for k, v in d.items()}
    except (ValueError, KeyError, TypeError):
        return {}
