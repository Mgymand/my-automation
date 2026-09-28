"""投稿候補の生成。1 商品につき複数の訴求軸で候補を作る。

- LLM（Sonnet 5）が使える場合: パターンの「構造」だけを渡し、商品データから文章を生成
- 使えない場合: 決定論的テンプレート（商品データを埋めるだけ。捏造しない）
どちらも「存在しないレビュー・評価を作らない」「クリックベイト禁止」「PR 表記必須」を守る。
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .compliance import find_ng_words
from .db import Database, dumps, utcnow
from .llm import LLMRouter, LLMUnavailable

ANGLES = ["content", "performer", "review", "price", "discount", "new_release", "situation"]

GEN_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "angle": {"type": "string"},
                    "text": {"type": "string"},
                    "hook_type": {"type": "string"},
                },
                "required": ["angle", "text", "hook_type"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["candidates"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """あなたは日本語 SNS の投稿ライターです。DMM/FANZA の商品を X に投稿する本文を作ります。
厳守事項:
- 与えられた商品データに存在しない事実（レビュー内容、評価、受賞、限定性）を書かない
- 誤解を招くクリックベイト、煽り、「必ず」「100%」のような断定を使わない
- 未成年・非同意・違法性を想起させる語を一切使わない（作品タイトルにあっても本文には入れない）
- 本文の末尾に必ず「【PR】」を入れる
- リンクは本文に入れない（リプライで別途付ける）
- ハッシュタグは最大 2 個
- 日本語 110 文字以内（PR 表記込み）
- 広告臭・コピー臭を抑え、人が自分の言葉で紹介している文体にする
- 各候補は訴求軸（angle）と冒頭フックの型（hook_type）を変え、互いに似せない
出力は JSON のみ。"""


@dataclass
class Candidate:
    angle: str
    text: str
    hook_type: str
    model: str


def _fmt_price(p: dict) -> str:
    price = p.get("price")
    if not price:
        return ""
    return f"{int(price):,}円"


def template_candidates(p: dict, pattern: dict, rng: random.Random | None = None) -> list[Candidate]:
    """LLM なしの決定論的生成。事実のみを並べる。"""
    rng = rng or random.Random(p["content_id"])
    title = p["title"]
    genres = [g for g in p.get("genres") or [] if not find_ng_words(g)][:2]
    actresses = (p.get("actresses") or [])[:2]
    price = _fmt_price(p)
    disc = float(p.get("discount_rate") or 0)
    ravg, rc = p.get("review_avg"), int(p.get("review_count") or 0)
    rel = str(p.get("release_date") or "")[:10]
    pr = "【PR】"
    out: list[Candidate] = []

    g = "・".join(genres) if genres else "新着"
    out.append(Candidate("content", f"{title}\n{g}。{('価格 ' + price + '。') if price else ''}詳細はリプ欄から。{pr}", "作品名先頭", "template"))
    if actresses:
        out.append(Candidate("performer", f"{'・'.join(actresses)} 出演。\n{title}\n{g}。リプ欄に配信ページ。{pr}", "出演者先頭", "template"))
    if ravg and rc >= 5:
        out.append(Candidate("review", f"レビュー平均{ravg:.1f}（{rc}件）。\n{title}\n{g}。詳しくはリプ欄。{pr}", "実データ先頭", "template"))
    if disc >= 0.1:
        out.append(Candidate("discount", f"{int(disc * 100)}%OFF 中。\n{title}\n{('今の価格 ' + price + '。') if price else ''}リプ欄から。{pr}", "割引先頭", "template"))
    elif price:
        out.append(Candidate("price", f"{price}。\n{title}\n{g}。リプ欄に配信ページ。{pr}", "価格先頭", "template"))
    if rel:
        out.append(Candidate("new_release", f"{rel} 配信。\n{title}\n{g}。配信ページはリプ欄。{pr}", "日付先頭", "template"))
    return out[:4]


def llm_candidates(llm: LLMRouter, p: dict, pattern: dict, recent_texts: list[str], n: int = 4) -> list[Candidate]:
    facts = {
        "title": p["title"],
        "genres": (p.get("genres") or [])[:5],
        "actresses": (p.get("actresses") or [])[:3],
        "maker": p.get("maker"),
        "series": p.get("series"),
        "price_jpy": p.get("price"),
        "list_price_jpy": p.get("list_price"),
        "discount_rate": p.get("discount_rate"),
        "release_date": p.get("release_date"),
        "review_count": p.get("review_count"),
        "review_avg": p.get("review_avg"),
        "campaign": (p.get("campaign") or [])[:2],
    }
    user = (
        f"## 使うパターン（構造のみ。文章はコピーしない）\n"
        f"カテゴリ: {pattern['category']}\nターゲット: {pattern.get('target')}\nフック: {pattern.get('hook')}\n"
        f"構成: {pattern.get('structure')}\nCTA: {pattern.get('cta')}\n\n"
        f"## 商品データ（これ以外の事実は書かない）\n{dumps(facts)}\n\n"
        f"## 直近の投稿（これらと似せない）\n" + "\n---\n".join(recent_texts[-8:]) + "\n\n"
        f"訴求軸を変えた候補を {n} 個、JSON で出力。angle は {ANGLES} から選ぶ。"
    )
    res = llm.call("sonnet", SYSTEM_PROMPT, user, schema=GEN_SCHEMA, max_tokens=2000, ref=f"gen:{p['content_id']}")
    out = []
    for c in (res.parsed or {}).get("candidates", []):
        text = c.get("text", "").strip()
        if not text:
            continue
        if "PR" not in text and "広告" not in text:
            text += " 【PR】"
        out.append(Candidate(c.get("angle", "content"), text, c.get("hook_type", ""), res.model))
    return out


def generate_for_product(db: Database, llm: LLMRouter | None, p: dict, pattern: dict, recent_texts: list[str]) -> list[int]:
    """候補を生成して DB に保存し、candidate id のリストを返す。"""
    cands: list[Candidate] = []
    if llm is not None and llm.enabled:
        try:
            cands = llm_candidates(llm, p, pattern, recent_texts)
        except LLMUnavailable as e:
            db.log_event("warn", "llm_fallback", f"テンプレート生成に切替: {e}", {"product": p["content_id"]})
    if not cands:
        cands = template_candidates(p, pattern)
    ids = []
    for c in cands:
        cur = db.exec(
            "INSERT INTO candidates(product_id,pattern_id,angle,text,reply_text,media_plan,status,model,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (p["content_id"], pattern["pattern_id"], c.angle, c.text, None, dumps({"hook_type": c.hook_type}),
             "new", c.model, utcnow()),
        )
        ids.append(cur.lastrowid)
    return ids


def build_reply_text(tracking_url: str, disclosure: str = "【PR】") -> str:
    return f"{disclosure} 配信ページはこちら\n{tracking_url}\n※18歳未満の方は閲覧・購入できません"
