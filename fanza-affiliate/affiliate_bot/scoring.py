"""投稿候補のスコアリング（決定論的）と最良案の選択。

Predicted CTR / Predicted Engagement / Novelty / Pattern Confidence / Similarity Risk / Policy Risk
→ 総合スコア（期待利益ベース）で最良案 1 つを選び、代替案 1〜2 個を添える。
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .compliance import check_text
from .db import Database, dumps, loads

SIMILARITY_REJECT = 0.80


@dataclass
class Scores:
    p_ctr: float
    p_engagement: float
    novelty: float
    pattern_confidence: float
    similarity_risk: float
    policy_risk: float
    expected_views: float
    expected_revenue_jpy: float
    total: float
    decision: str            # accept|reject
    reasons: list[str]


def _spam(text: str) -> float:
    risk = 0.0
    if len(re.findall(r"#\S+", text)) > 2:
        risk += 0.3
    if re.search(r"(.)\1{4,}", text):
        risk += 0.2
    if len(text) < 12:
        risk += 0.2
    return min(1.0, risk)


def score_candidate(db: Database, cand: dict, product: dict, pattern: dict, media_url: str | None,
                    all_texts_for_product: list[str]) -> Scores:
    text = cand["text"]
    comp = product.get("eav_components") or {}
    if isinstance(comp, str):
        comp = loads(comp, {})
    p_ctr = float(comp.get("p_ctr") or 0.008)
    p_cvr = float(comp.get("p_cvr") or 0.02)
    payout = float(comp.get("payout_jpy") or (float(product.get("price") or 0) * 0.2))
    views = float(comp.get("p_views") or 800)

    # パターン実績で補正
    if (pattern.get("uses") or 0) >= 5 and pattern.get("recent30_ctr"):
        p_ctr = 0.5 * p_ctr + 0.5 * float(pattern["recent30_ctr"])
    p_eng = float(pattern.get("engagement_rate") or 0) or 0.01
    p_eng *= 1.1 if re.search(r"[？?]", text[:30]) else 1.0
    conf = float(pattern.get("confidence") or 0.2)
    if pattern.get("trend_score"):
        conf = min(0.95, conf + 0.2 * float(pattern["trend_score"]))

    # 長さがパターンの理想から離れるほど減点
    ideal = int(pattern.get("ideal_length") or 80)
    length_fit = max(0.85, 1 - abs(len(text) - ideal) / max(ideal, 40) * 0.5)

    sim = float(cand.get("similarity_score") or 0)
    novelty = round(1 - sim, 3)
    pol = check_text(text, media_url)
    spam = _spam(text)
    policy_risk = max(pol.risk, spam)

    exp_views = views * (0.6 + 0.4 * novelty) * length_fit
    exp_rev = exp_views * p_ctr * p_cvr * payout
    total = exp_rev * (0.5 + conf) * (1 - policy_risk) * (1 + p_eng * 5)
    reasons = list(pol.reasons)
    if sim >= SIMILARITY_REJECT:
        reasons.append(f"既存投稿と酷似 ({sim:.2f})")
    decision = "accept" if (pol.ok and sim < SIMILARITY_REJECT and spam < 0.7) else "reject"
    return Scores(round(p_ctr, 5), round(p_eng, 4), novelty, round(conf, 3), round(sim, 3), round(policy_risk, 3),
                  round(exp_views), round(exp_rev, 2), round(total, 4), decision, reasons)


def persist_scores(db: Database, candidate_id: int, s: Scores) -> None:
    db.exec("UPDATE candidates SET scores=?, status=? WHERE id=?",
            (dumps(asdict(s)), "scored" if s.decision == "accept" else "rejected", candidate_id))


def choose_best(scored: list[tuple[dict, Scores]]) -> tuple[tuple[dict, Scores] | None, list[tuple[dict, Scores]]]:
    """最良案 1 つと代替案（最大 2 つ）。"""
    ok = [x for x in scored if x[1].decision == "accept"]
    if not ok:
        return None, []
    ok.sort(key=lambda x: x[1].total, reverse=True)
    best = ok[0]
    alts = [x for x in ok[1:] if x[0]["angle"] != best[0]["angle"]][:2]
    return best, alts
