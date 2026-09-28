"""規約・法令ゲート。すべての投稿はここを通過しないと公開されない。

根拠（docs/COMPLIANCE.md 参照）:
- X 自動化ルール: 公式 API のみ、スパム禁止、複数アカウントで同一内容禁止
- X 成人向けコンテンツ: メディアをセンシティブ設定、プロフィール画像/ヘッダー禁止、未成年 NG
- X 有料パートナーシップ方針: アフィリエイトは開示対象。「成人向け・性的な商品/サービス」「成人向けエンターテインメント」は
  禁止カテゴリ → 成人向け商品の X 投稿は policy.py により HARD BLOCK（設定で解除不可）
- DMM 参加規約/ガイドライン: 公式素材のみ、スパム禁止、児童ポルノ相当は一切禁止、「広告/PR」表記必須
- 景表法ステマ規制（2023-10-01〜）: 広告であることを一般消費者が判別できる表示
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .config import Settings
from .policy import x_affiliate_hard_block

# 未成年を想起させる表現・強制/非同意を想起させる表現・誤認を招く表現。
# 部分一致で判定する。作品タイトルに含まれていても投稿文には使わない。
NG_WORDS = [
    "未成年", "中学生", "小学生", "高校生", "女子高生", "女子校生", "JK", "JC", "JS", "ロリ", "幼", "少女", "児童", "学生服",
    "レイプ", "強姦", "無理やり", "薬物", "盗撮", "痴漢", "監禁",
    "無修正", "流出", "本物の", "リアル流出",
    "絶対に儲かる", "必ず", "100%", "限定公開", "RTで見れる", "フォローで見れる",
]
# タイトルに含まれる場合に投稿自体を見送るワード（商品自体を扱わない）
NG_PRODUCT_WORDS = ["未成年", "中学", "小学", "児童", "ロリ", "盗撮", "痴漢", "レイプ", "強姦", "無修正"]

DMM_MEDIA_HOSTS = (
    "pics.dmm.co.jp", "pics.dmm.com", "cc3001.dmm.co.jp", "cc3001.dmm.com",
    "awsimgsrc.dmm.co.jp", "awsimgsrc.dmm.com", "litevideo.dmm.co.jp", "www.dmm.co.jp", "www.dmm.com",
)

DISCLOSURE_PATTERNS = [r"【PR】", r"#PR\b", r"\bPR\b", r"広告", r"宣伝", r"プロモーション", r"アフィリエイト"]
MAX_HASHTAGS = 3
MAX_TEXT_LEN = 280  # 全角換算は X 側で 2 文字扱い。日本語は 140 文字が上限。
MAX_JP_LEN = 140


@dataclass
class PolicyResult:
    ok: bool
    risk: float                      # 0.0 (安全) 〜 1.0 (公開不可)
    reasons: list[str] = field(default_factory=list)
    requires_human: bool = False
    hard_block: bool = False         # 規約上禁止。人間の了承でも解除できない


def weighted_len(text: str) -> int:
    """X の文字数計算の近似（全角 2、半角 1、URL は 23）。"""
    t = re.sub(r"https?://\S+", "x" * 23, text)
    n = 0
    for ch in t:
        n += 1 if ord(ch) < 0x0800 else 2
    return n


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


SENSITIVE_HINT_WORDS = ("グラビア", "水着", "セクシー", "ランジェリー", "下着", "sexy", "gravure")


def _maybe_sensitive(genres: list[str] | None) -> bool:
    hay = " ".join(genres or []).lower()
    return any(w.lower() in hay for w in SENSITIVE_HINT_WORDS)


def check_post(text: str, reply_text: str | None, media_url: str | None, is_adult: bool,
               settings: Settings, site: str | None = None, genres: list[str] | None = None) -> PolicyResult:
    reasons: list[str] = []
    risk = 0.0
    requires_human = False

    # 0) HARD BLOCK: X 有料パートナーシップの禁止カテゴリ（成人向け商品）。設定では解除不可
    hb = x_affiliate_hard_block(site or ("FANZA" if is_adult else "DMM.com"), None, genres)
    if hb.blocked:
        return PolicyResult(ok=False, risk=1.0, reasons=[hb.reason], requires_human=False, hard_block=True)

    combined = text + "\n" + (reply_text or "")

    # 1) 広告表示（景表法ステマ規制 + DMM 規約）
    if not has_disclosure(combined):
        reasons.append("広告表示（【PR】等）がない")
        risk = max(risk, 1.0)

    # 2) NG ワード
    ng = find_ng_words(combined)
    if ng:
        reasons.append("NG ワード: " + ", ".join(ng))
        risk = max(risk, 1.0)

    # 3) 文字数
    if len(text) > MAX_JP_LEN and weighted_len(text) > MAX_TEXT_LEN:
        reasons.append("本文が長すぎる")
        risk = max(risk, 0.9)

    # 4) ハッシュタグ過多（スパム判定リスク）
    if len(re.findall(r"#\S+", text)) > MAX_HASHTAGS:
        reasons.append("ハッシュタグ過多")
        risk = max(risk, 0.6)

    # 5) 素材の権利
    if not media_rights_ok(media_url):
        reasons.append("メディアが DMM 提供素材ではない（権利確認不能）")
        risk = max(risk, 1.0)

    # 6) センシティブになり得るメディア（水着・グラビア等の非成人向け商品）はアカウント設定の確認を推奨
    if media_url and not settings.sensitive_media_setting_confirmed and _maybe_sensitive(genres):
        reasons.append("センシティブになり得るメディア: X の『メディアをセンシティブとしてマーク』設定の確認が未完了")
        risk = max(risk, 0.8)
        requires_human = True

    # 7) 媒体登録
    if not settings.dmm_media_registered:
        reasons.append("DMM アフィリエイトへの X アカウント媒体登録が未確認")
        risk = max(risk, 1.0)
        requires_human = True

    return PolicyResult(ok=risk < 0.7, risk=risk, reasons=reasons, requires_human=requires_human)
