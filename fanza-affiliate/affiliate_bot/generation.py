"""投稿候補の生成（1 商品につき最低 5 案）。

A: 極短文 / B: 女優訴求 / C: シチュエーション訴求 / D: レビュー訴求 / E: 価格・割引訴求
- LLM（Sonnet 5）が使えればパターンの「構造」だけを渡して生成。使えなければ決定論的テンプレート
- 他者の投稿文は渡さない（構造のみ）。存在しない事実・レビュー・評価を作らない。クリックベイト禁止。PR 表記必須
- 各案に source_pattern_id / similarity_score を保存。既存投稿・他候補と似すぎる案は自動で書き直す
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .compliance import find_ng_words
from .db import Database, dumps, utcnow
from .llm import LLMRouter, LLMUnavailable
from .patterns import ANGLE_TO_PATTERN, get_pattern
from .similarity import max_similarity

ANGLES = [("A_short", "極短文"), ("B_actress", "女優訴求"), ("C_situation", "シチュエーション訴求"),
          ("D_review", "レビュー訴求"), ("E_price", "価格・割引訴求")]
SIMILARITY_REWRITE = 0.55
MAX_REWRITES = 2

GEN_SCHEMA = {
    "type": "object",
    "properties": {"candidates": {"type": "array", "items": {"type": "object", "properties": {
        "angle": {"type": "string"}, "text": {"type": "string"}, "hook_type": {"type": "string"}},
        "required": ["angle", "text", "hook_type"], "additionalProperties": False}}},
    "required": ["candidates"], "additionalProperties": False,
}

SYSTEM_PROMPT = """あなたは日本語 SNS の投稿ライターです。FANZA の作品を X で紹介する本文を、人間が手動で投稿するために作ります。
厳守事項:
- 与えられた商品データに存在しない事実（レビュー内容、評価、受賞、限定性、作品の場面）を書かない
- 誤解を招くクリックベイト、煽り、「必ず」「100%」のような断定を使わない
- 未成年・非同意・違法性を想起させる語を一切使わない（作品タイトルにあっても本文には入れない）
- 露骨な性的描写は書かない（作品名・出演者・ジャンル・価格・配信日などの客観情報と雰囲気の紹介に留める）
- 本文の末尾に必ず「【PR】」を入れる。リンクは本文に入れない（投稿者がリプ欄等に付ける）
- ハッシュタグは最大 2 個。日本語 120 文字以内（PR 表記込み）
- 与えられた『パターンの構造』を使い、他者の文章は再利用しない。各案は訴求軸と冒頭フックを変え、互いに似せない
出力は JSON のみ。"""


@dataclass
class Candidate:
    angle: str
    text: str
    hook_type: str
    source_pattern_id: str
    model: str


def _fmt_price(p: dict) -> str:
    return f"{int(p['price']):,}円" if p.get("price") else ""


def template_candidates(p: dict, pattern_ids: dict[str, str]) -> list[Candidate]:
    """LLM なしの決定論的 5 案。事実のみを並べる。"""
    title = p["title"]
    genres = [g for g in (p.get("genres") or []) if not find_ng_words(g)][:2]
    g = "・".join(genres) if genres else "新着"
    actresses = (p.get("actresses") or [])[:2]
    price = _fmt_price(p)
    disc = float(p.get("discount_rate") or 0)
    ravg, rc = p.get("review_avg"), int(p.get("review_count") or 0)
    rel = str(p.get("release_date") or "")[:10]
    pr = "【PR】"
    out = [
        Candidate("A_short", f"{title}。{g}。{pr}", "一言", pattern_ids["A_short"], "template"),
        Candidate("B_actress", (f"{'・'.join(actresses)} 出演。\n" if actresses else "") + f"{title}\n{g}。{('配信 ' + rel + '。') if rel else ''}{pr}",
                  "出演者名先頭", pattern_ids["B_actress"], "template"),
        Candidate("C_situation", f"{g}が舞台の一本。\n{title}\n{('出演: ' + '・'.join(actresses) + '。') if actresses else ''}{pr}",
                  "情景描写", pattern_ids["C_situation"], "template"),
        Candidate("D_review", (f"レビュー平均{ravg:.1f}（{rc}件）。\n" if (ravg and rc >= 5) else "レビュー掲載中。\n") + f"{title}\n{g}。{pr}",
                  "実データ先頭", pattern_ids["D_review"], "template"),
        Candidate("E_price", (f"{int(disc * 100)}%OFF 中。\n" if disc >= 0.1 else "") + f"{title}\n{('現在 ' + price + '。') if price else ''}{g}。{pr}",
                  "割引先頭" if disc >= 0.1 else "価格先頭", pattern_ids["E_price"], "template"),
    ]
    return out


def llm_candidates(llm: LLMRouter, p: dict, patterns: dict[str, dict], recent_texts: list[str]) -> list[Candidate]:
    facts = {k: p.get(k) for k in ("title", "maker", "series", "price", "list_price", "discount_rate", "release_date", "review_count", "review_avg")}
    facts["genres"] = (p.get("genres") or [])[:5]
    facts["actresses"] = (p.get("actresses") or [])[:3]
    facts["campaign"] = (p.get("campaign") or [])[:2]
    structures = {a: {"pattern_id": pt["pattern_id"], "name": pt["pattern_name"], "hook": pt["hook"], "body": pt["body_structure"],
                      "cta": pt["cta_structure"], "ideal_length": pt["ideal_length"]} for a, pt in patterns.items()}
    user = ("## 訴求軸とパターン構造（構造のみ。文章はコピーしない）\n" + dumps(structures) +
            "\n\n## 商品データ（これ以外の事実は書かない）\n" + dumps(facts) +
            "\n\n## 直近の自分の投稿（これらと似せない）\n" + "\n---\n".join(recent_texts[-8:]) +
            "\n\n5 つの訴求軸（A_short / B_actress / C_situation / D_review / E_price）それぞれ 1 案ずつ、JSON で出力。")
    res = llm.call("sonnet", SYSTEM_PROMPT, user, schema=GEN_SCHEMA, max_tokens=2500, ref=f"gen:{p['content_id']}")
    out = []
    for c in (res.parsed or {}).get("candidates", []):
        text = c.get("text", "").strip()
        angle = c.get("angle", "A_short")
        if not text or angle not in patterns:
            continue
        if "PR" not in text and "広告" not in text:
            text += " 【PR】"
        out.append(Candidate(angle, text, c.get("hook_type", ""), patterns[angle]["pattern_id"], res.model))
    return out


def rewrite_if_similar(llm: LLMRouter | None, cand: Candidate, corpus: list[str], p: dict) -> tuple[Candidate, float, int]:
    """既存投稿・他候補と似すぎる案を書き直す（最大 2 回）。LLM がなければ語順・表現を機械的に変える。"""
    sim = max_similarity(cand.text, corpus)
    rewrites = 0
    while sim >= SIMILARITY_REWRITE and rewrites < MAX_REWRITES:
        rewrites += 1
        new_text = None
        if llm is not None and llm.enabled:
            try:
                res = llm.call("sonnet", SYSTEM_PROMPT,
                               f"次の案は既存投稿と似すぎています（類似度 {sim:.2f}）。同じ訴求軸・同じ事実のまま、冒頭フックと語順・表現を変えて書き直してください。"
                               f"\n案: {cand.text}\n商品: {dumps({k: p.get(k) for k in ('title', 'genres', 'actresses', 'price', 'release_date')})}",
                               schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False},
                               max_tokens=400, ref=f"rewrite:{p['content_id']}")
                new_text = (res.parsed or {}).get("text", "").strip()
            except LLMUnavailable:
                new_text = None
        if not new_text:
            parts = [x for x in cand.text.replace("【PR】", "").split("\n") if x.strip()]
            parts = parts[::-1] if len(parts) > 1 else parts
            new_text = "\n".join(parts).strip() + f"（{p.get('maker') or 'FANZA'}）【PR】"
        cand = Candidate(cand.angle, new_text, cand.hook_type, cand.source_pattern_id, cand.model)
        sim = max_similarity(cand.text, corpus)
    return cand, sim, rewrites


def generate_for_product(db: Database, llm: LLMRouter | None, p: dict, recent_texts: list[str],
                         pattern_override: dict[str, str] | None = None) -> list[int]:
    """5 案を生成・類似チェックして DB に保存。candidate id を返す。"""
    pattern_ids = dict(ANGLE_TO_PATTERN)
    if pattern_override:
        pattern_ids.update(pattern_override)
    pats = {a: (get_pattern(db, pid) or {"pattern_id": pid, "pattern_name": pid, "hook": "", "body_structure": "", "cta_structure": "", "ideal_length": 80})
            for a, pid in pattern_ids.items()}
    cands: list[Candidate] = []
    if llm is not None and llm.enabled:
        try:
            cands = llm_candidates(llm, p, pats, recent_texts)
        except LLMUnavailable as e:
            db.log_event("warn", "llm_fallback", f"テンプレート生成に切替: {e}", {"product": p["content_id"]})
    have = {c.angle for c in cands}
    if len(have) < 5:
        cands += [c for c in template_candidates(p, pattern_ids) if c.angle not in have]
    ids = []
    # 類似度は「既存の投稿」に対してのみ測る（同一商品の 5 案同士は当然似るため比較しない。案同士の差は訴求軸で担保）
    corpus = list(recent_texts)
    for c in cands:
        c, sim, rewrites = rewrite_if_similar(llm, c, corpus, p)
        cur = db.exec(
            "INSERT INTO candidates(product_id,source_pattern_id,angle,text,hook_type,similarity_score,rewrite_count,status,model,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (p["content_id"], c.source_pattern_id, c.angle, c.text, c.hook_type, round(sim, 3), rewrites, "new", c.model, utcnow()))
        ids.append(cur.lastrowid)
    return ids
