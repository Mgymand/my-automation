"""API 価格の設定・検証。価格はコードに固定せず、環境変数 → DB（settings.x_pricing）の順で上書きできる。

- X API 読取価格: docs.x.com/x-api/getting-started/pricing を取得して既知ラベルの数値を抽出する（staged update）。
  * 必須項目（read_post / owned_read / read_user）が全件抽出できた場合のみ候補化
  * 現在値との最大変動率が AUTO_APPLY_MAX_CHANGE 以下なら自動適用（軽微なドリフト）
  * それを超える場合は候補（settings.x_pricing_candidate）として保存し Attention Queue で人間確認。確認前は旧価格を使う
  * 抽出失敗・誤マッチの疑い（負値や極端な値）は候補化しない
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
    "read_post": ["Posts", "Post read"],
    "owned_read": ["Owned Reads", "Owned read"],
    "read_user": ["Users"],
}


AUTO_APPLY_MAX_CHANGE = 0.10   # 10% 以内の変動は自動適用。それ以上は人間確認（旧価格を使い続ける）
REQUIRED_FIELDS = ("read_post", "owned_read", "read_user")
SANE_RANGE = (0.0001, 5.0)      # USD/req としてあり得る範囲（誤マッチ検出）


@dataclass
class XPricing:
    """X API 読取価格（USD）。Phase 3 では書込を行わないため投稿価格は持たない。"""
    read_post: float
    owned_read: float
    read_user: float
    source: str = "env"

    def as_dict(self) -> dict:
        return {"read_post": self.read_post, "owned_read": self.owned_read, "read_user": self.read_user, "source": self.source}


def x_pricing(settings: Settings, db=None) -> XPricing:
    p = XPricing(settings.x_price_read_post_usd, settings.x_price_owned_read_usd, settings.x_price_read_user_usd, "env")
    if db is not None:
        raw = db.get_setting("x_pricing")
        if raw:
            try:
                d = json.loads(raw)
                return XPricing(float(d["read_post"]), float(d["owned_read"]), float(d["read_user"]), d.get("source", "db"))
            except (ValueError, KeyError, TypeError):
                pass
    return p


def _extract_price(text: str, labels: list[str]) -> float | None:
    for lab in labels:
        m = re.search(re.escape(lab) + r"[^$]{0,80}\$\s*([0-9]+(?:\.[0-9]+)?)", text, flags=re.I)
        if m:
            return float(m.group(1))
    return None


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def evaluate_candidate(current: XPricing, found: dict) -> tuple[str, XPricing | None, dict]:
    """抽出結果を評価する。戻り値: (status, candidate, changed)
    status: unverified（必須項目不足/異常値）| ok（変化なし）| applied（軽微→自動適用）| staged（大きな変化→人間確認）"""
    if any(found.get(k) is None for k in REQUIRED_FIELDS):
        return "unverified", None, {}
    if any(not (SANE_RANGE[0] <= float(found[k]) <= SANE_RANGE[1]) for k in REQUIRED_FIELDS):
        return "unverified", None, {}
    cand = XPricing(*(float(found[k]) for k in REQUIRED_FIELDS), "official_page")
    changed = {k: (getattr(current, k), getattr(cand, k)) for k in REQUIRED_FIELDS
               if abs(getattr(current, k) - getattr(cand, k)) > 1e-9}
    if not changed:
        return "ok", cand, {}
    max_rel = max(abs(n - o) / o if o else 1.0 for o, n in changed.values())
    return ("applied" if max_rel <= AUTO_APPLY_MAX_CHANGE else "staged"), cand, changed


def verify_x_pricing(settings: Settings, db, session: requests.Session | None = None) -> dict:
    """公式価格ページを取得して差分を検出する（staged update）。
    取得・抽出できなければ現在値を維持し status=unverified。大きな変化は候補として保存し、人間確認まで旧価格を使う。"""
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
    status, cand, changed = evaluate_candidate(current, found)
    if status == "unverified":
        db.log_event("info", "x_pricing_unverified", "価格ページから必須項目を抽出できず（旧価格を継続）", {"found": found})
        return {"status": "unverified", "reason": "必須項目の抽出失敗または異常値（ページ構成変更の可能性）", "pricing": current.as_dict(), "found": found}
    db.set_setting("x_pricing_verified_at", _now_iso())
    if status == "ok":
        return {"status": "ok", "pricing": current.as_dict(), "changed": {}}
    if status == "applied":
        db.set_setting("x_pricing", json.dumps(cand.as_dict()))
        db.log_event("info", "x_pricing_applied", f"X API 価格の軽微な変更を自動適用: {changed}", {"changed": changed})
        return {"status": "applied", "pricing": cand.as_dict(), "changed": changed}
    db.set_setting("x_pricing_candidate", json.dumps({"pricing": cand.as_dict(), "changed": changed, "at": _now_iso()}))
    db.log_event("warn", "x_pricing_staged", f"X API 価格の大きな変更を検出（人間確認まで旧価格を使用）: {changed}", {"changed": changed})
    return {"status": "staged", "pricing": current.as_dict(), "candidate": cand.as_dict(), "changed": changed}


def apply_candidate(db) -> XPricing | None:
    """人間確認後に候補価格を適用する（`affiliate-bot pricing --apply`）。"""
    raw = db.get_setting("x_pricing_candidate")
    if not raw:
        return None
    d = json.loads(raw)["pricing"]
    db.set_setting("x_pricing", json.dumps(d))
    db.set_setting("x_pricing_candidate", "")
    db.log_event("info", "x_pricing_applied", "候補価格を人間確認後に適用", d)
    return XPricing(d["read_post"], d["owned_read"], d["read_user"], "official_page")


def llm_pricing_overrides() -> dict:
    raw = os.environ.get("LLM_PRICING_JSON", "").strip()
    if not raw:
        return {}
    try:
        d = json.loads(raw)
        return {k: {"in": float(v["in"]), "out": float(v["out"]), "cache": float(v.get("cache", 0))} for k, v in d.items()}
    except (ValueError, KeyError, TypeError):
        return {}
