"""プラットフォーム規約の台帳（Policy Registry）。

設定ファイルや環境変数では **解除できない** ハードブロックの根拠をここに置く。
規約が変わった場合はこのファイルを（一次情報を確認した人間が）更新する。

X 有料パートナーシップ方針（Paid Partnerships Policy）
- 公式（日本語, 2026-09-28 取得・確認済）: https://help.x.com/ja/rules-and-policies/paid-partnerships
  「利用者が利益、インセンティブ、または報酬などを受け取れる可能性のあるアフィリエイトリンクや割引コードを含むポスト」は
  有料パートナーシップに該当し、明確な開示が必要。
- 公式（英語, 2026-09-28 運営者が原文を確認済）: https://help.x.com/en/rules-and-policies/paid-partnerships-policy
  affiliate links / discount codes による commission を Paid Partnership に含め、
  Prohibited Industries に「Adult and sexual products and services」を含むことを一次情報で確認済み。
  `verify_policy()` は本文のキーフレーズと本文ハッシュの変化を監視する。
  直接取得（source=direct）のみを一次情報確認として扱い、Reader プロキシ経由（source=proxy）の取得は
  参考情報として記録するだけで、台帳の確定・ハッシュ基準の更新には使わない。

結論: FANZA 成人向け商品のアフィリエイト投稿は「禁止カテゴリの有料パートナーシップ」に該当するため、
      X への投稿は HARD BLOCK。センシティブメディアとして投稿可能なことと、有料パートナーシップとして宣伝可能なことは別。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

import requests

POLICY_VERSION = "2026-09-28"

OFFICIAL_URLS = {
    "x_paid_partnerships_en": "https://help.x.com/en/rules-and-policies/paid-partnerships-policy",
    "x_paid_partnerships_ja": "https://help.x.com/ja/rules-and-policies/paid-partnerships",
    "x_adult_content": "https://help.x.com/en/rules-and-policies/adult-content",
    "x_automation": "https://help.x.com/en/rules-and-policies/x-automation",
    "dmm_terms": "https://terms.dmm.com/affiliate_service/",
    "dmm_guideline": "https://terms.dmm.com/affiliate_guideline/",
}

# X 有料パートナーシップの禁止カテゴリ（英語版の列挙。正規化キー）
X_PAID_PARTNERSHIP_PROHIBITED = {
    "adult_sexual_products": "Adult and sexual products and services",
    "adult_entertainment": "Adult entertainment",
    "alcohol": "Alcoholic beverages and related accessories",
    "contraceptives": "Contraceptives",
    "dating": "Dating & Marriage Services",
    "drugs": "Drugs and drug-related products or services",
    "political": "Geo-political, political, social issues or crises for commercial purposes",
    "supplements": "Health and wellness supplements",
    "pharma": "Pharmaceutical and medicine-related products or services",
    "tobacco": "Tobacco and tobacco-related products or services",
    "weapons": "Weapons and weapons-related products or services",
    "weight_loss": "Weight loss products and services",
}

# 取得できた場合に本文に含まれているべきキーフレーズ（含まれなければ「規約変更」として人間へ）
EXPECTED_PHRASES = {
    "x_paid_partnerships_en": ["affiliate", "Adult"],
    "x_paid_partnerships_ja": ["アフィリエイトリンク"],
}


@dataclass
class HardBlock:
    blocked: bool
    code: str
    reason: str
    policy: str = ""


def classify_product_category(site: str, floor: str | None, genres: list[str] | None = None) -> str:
    """商品を X 有料パートナーシップの観点でカテゴリ分類する。
    FANZA（成人向けサイト）の商品はフロアに関わらず 'adult_sexual_products' とみなす（保守的）。
    """
    if (site or "").upper() == "FANZA":
        return "adult_sexual_products"
    hay = " ".join(genres or []).lower()
    if any(k in hay for k in ("アダルト", "adult", "18禁", "r18", "成人")):
        return "adult_sexual_products"
    return "general"


def x_affiliate_hard_block(site: str, floor: str | None = None, genres: list[str] | None = None) -> HardBlock:
    """X へのアフィリエイト投稿が規約上禁止されるかを判定する。設定では上書きできない。"""
    cat = classify_product_category(site, floor, genres)
    if cat in X_PAID_PARTNERSHIP_PROHIBITED:
        return HardBlock(
            True,
            "x_paid_partnership_prohibited",
            f"X 有料パートナーシップ方針の禁止カテゴリ『{X_PAID_PARTNERSHIP_PROHIBITED[cat]}』に該当。"
            "アフィリエイトリンクを含む投稿は有料パートナーシップとみなされるため、X への投稿は不可（HARD BLOCK）",
            OFFICIAL_URLS["x_paid_partnerships_en"],
        )
    return HardBlock(False, "", "")


def _fetch_text(url: str, timeout: int = 30, session=None) -> tuple[str, str] | None:
    """公式ページ本文をテキスト化して (source, text) を返す。source は direct | proxy。取得不能なら None。
    direct: X のサーバーから直接取得（一次情報）。proxy: Reader プロキシ経由（参考情報。台帳確定には使わない）。"""
    ua = {"User-Agent": "Mozilla/5.0 (compatible; affiliate-bot policy check)"}
    s = session or requests
    for source, target in (("direct", url), ("proxy", f"https://r.jina.ai/{url}")):
        try:
            r = s.get(target, headers=ua, timeout=timeout)
        except requests.RequestException:
            continue
        if r.status_code != 200 or "Enable JavaScript and cookies" in r.text or "Just a moment" in r.text[:500]:
            continue
        t = re.sub(r"<script.*?</script>|<style.*?</style>", "", r.text, flags=re.S)
        t = re.sub(r"<[^>]+>", " ", t)
        t = re.sub(r"\s+", " ", t)
        if len(t) > 200:
            return source, t
    return None


def verify_policy(db, keys: tuple[str, ...] = ("x_paid_partnerships_en", "x_paid_partnerships_ja"), session=None) -> dict:
    """公式ページを取得して、キーフレーズと本文ハッシュの変化を確認する。
    戻り値: {key: {"status": ok|changed|phrase_missing|unreachable|proxy_only, "source": direct|proxy, ...}}
    - direct 取得のみが一次情報確認。ハッシュ基準（policy_hash:*）は direct のときだけ更新する
    - proxy 取得は参考情報（policy_proxy_hash:*）として記録し、変化があっても「要確認」を促すだけで台帳は確定しない
    変化があれば events に記録し、呼び出し側（bootstrap / 週次）が Attention Queue へ起票する。
    """
    out: dict[str, dict] = {}
    for key in keys:
        url = OFFICIAL_URLS[key]
        got = _fetch_text(url, session=session)
        if got is None:
            out[key] = {"status": "unreachable", "url": url, "source": None}
            continue
        source, text = got
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        missing = [p for p in EXPECTED_PHRASES.get(key, []) if p.lower() not in text.lower()]
        if source == "direct":
            prev = db.get_setting(f"policy_hash:{key}")
            status = "phrase_missing" if missing else ("changed" if prev and prev != h else "ok")
            db.set_setting(f"policy_hash:{key}", h)
            db.set_setting(f"policy_verified_direct_at:{key}", __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds"))
        else:
            prev = db.get_setting(f"policy_proxy_hash:{key}")
            # proxy は参考のみ。フレーズ欠落や変化は「人間が原文を確認」を促すが、台帳もハッシュ基準も確定しない
            status = "proxy_only" if (not missing and (not prev or prev == h)) else ("phrase_missing" if missing else "changed")
            db.set_setting(f"policy_proxy_hash:{key}", h)
        if status not in ("ok", "proxy_only"):
            db.log_event("warn", "policy_check", f"{key}: {status} (source={source})",
                         {"url": url, "missing": missing, "prev": prev, "now": h, "source": source})
        out[key] = {"status": status, "url": url, "hash": h, "missing": missing, "source": source}
    return out
