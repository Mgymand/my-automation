"""投稿パッケージ（人間が手動投稿する完成品）の規約・法令チェック。

- 自動投稿のゲートではない（Phase 3 では投稿を実行するコードが存在しない）。
- 成人向け商品の X 自動投稿 HARD BLOCK は policy.py に残る。人間投稿の可否は投稿者本人の判断（HUMAN_POSTING_NOTICE を添付）。
- ここでは「PR 表記」「NG ワード」「素材の権利」「文字数」「ハッシュタグ過多」を検査する。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

NG_WORDS = [
    "未成年", "中学生", "小学生", "高校生", "女子高生", "女子校生", "JK", "JC", "JS", "ロリ", "幼", "少女", "児童", "学生服",
    "レイプ", "強姦", "無理やり", "薬物", "盗撮", "痴漢", "監禁",
    "無修正", "流出", "本物の", "リアル流出",
    "絶対に儲かる", "必ず", "100%", "限定公開", "RTで見れる", "フォローで見れる",
]
NG_PRODUCT_WORDS = ["未成年", "中学", "小学", "児童", "ロリ", "盗撮", "痴漢", "レイプ", "強姦", "無修正"]

DMM_MEDIA_HOSTS = (
    "pics.dmm.co.jp", "pics.dmm.com", "cc3001.dmm.co.jp", "cc3001.dmm.com",
    "awsimgsrc.dmm.co.jp", "awsimgsrc.dmm.com", "litevideo.dmm.co.jp", "www.dmm.co.jp", "www.dmm.com",
)
DISCLOSURE_PATTERNS = [r"【PR】", r"#PR\b", r"\bPR\b", r"広告", r"宣伝", r"プロモーション", r"アフィリエイト"]
MAX_HASHTAGS = 3
MAX_JP_LEN = 140


@dataclass
class PolicyResult:
    ok: bool
    risk: float
    reasons: list[str] = field(default_factory=list)


def weighted_len(text: str) -> int:
    t = re.sub(r"https?://\S+", "x" * 23, text)
    return sum(1 if ord(ch) < 0x0800 else 2 for ch in t)


def has_disclosure(text: str) -> bool:
    return any(re.search(p, text) for p in DISCLOSURE_PATTERNS)


def find_ng_words(text: str) -> list[str]:
    return [w for w in NG_WORDS if w.lower() in text.lower()]


def product_allowed(title: str, genres: list[str]) -> tuple[bool, str]:
    hay = (title + " " + " ".join(genres)).lower()
    for w in NG_PRODUCT_WORDS:
        if w.lower() in hay:
            return False, f"商品に取り扱い不可ワード: {w}"
    return True, ""


def media_rights_ok(url: str | None) -> bool:
    """DMM API が返した URL（= DMM 提供のアフィリエイト素材）のみ許可。"""
    if not url:
        return True
    host = urlparse(url).netloc.lower()
    return any(host == h or host.endswith("." + h) for h in DMM_MEDIA_HOSTS)


def check_text(text: str, media_url: str | None = None) -> PolicyResult:
    """投稿本文の検査。risk ≥ 0.7 は採用しない。"""
    reasons: list[str] = []
    risk = 0.0
    if not has_disclosure(text):
        reasons.append("広告表示（【PR】等）がない")
        risk = max(risk, 1.0)
    ng = find_ng_words(text)
    if ng:
        reasons.append("NG ワード: " + ", ".join(ng))
        risk = max(risk, 1.0)
    if len(text) > MAX_JP_LEN and weighted_len(text) > 280:
        reasons.append("本文が長すぎる")
        risk = max(risk, 0.9)
    if len(re.findall(r"#\S+", text)) > MAX_HASHTAGS:
        reasons.append("ハッシュタグ過多")
        risk = max(risk, 0.6)
    if "http" in text:
        reasons.append("本文に URL（リンクはリプ欄・プロフィール等、投稿者が判断）")
        risk = max(risk, 0.3)
    if not media_rights_ok(media_url):
        reasons.append("メディアが DMM 提供素材ではない（権利確認不能）")
        risk = max(risk, 1.0)
    return PolicyResult(ok=risk < 0.7, risk=risk, reasons=reasons)
