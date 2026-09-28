"""投稿前スコアリング（決定論的）。

Predicted CTR / Predicted CVR / Novelty / Spam Risk / Policy Risk / Similarity / Expected Revenue / Confidence
Similarity が高い候補は 'rewrite' に回す。
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .compliance import PolicyResult, check_post
from .config import Settings
from .db import Database, dumps, loads
from .similarity import max_similarity

SIMILARITY_REWRITE = 0.55   # これ以上似ていたら書き直し
SIMILARITY_REJECT = 0.80
MIN_EXPECTED_REVENUE_JPY = 0.0


@dataclass
class Scores:
    p_ctr: float
    p_cvr: float
    novelty: float
    spam_risk: float
    policy_risk: float
    similarity: float
    expected_views: float
    expected_revenue_jpy: float
    expected_cost_jpy: float
    expected_profit_jpy: float
    confidence: float
    decision: str            # accept|rewrite|reject|human
    reasons: list[str]


def spam_risk_score(text: str, same_product_recent: int) -> float:
    risk = 0.0
    if len(re.findall(r"#\S+", text)) > 2:
        risk += 0.3
    if text.count("http") > 0:
        risk += 0.2   # 本文にリンク（想定外）
    if re.search(r"(.)\1{4,}", text):
        risk += 0.2   # 同一文字連打
    if len(text) < 15:
        risk += 0.2
    if same_product_recent >= 2:
        risk += 0.3
    return min(1.0, risk)


def expected_views(db: Database, pattern: dict, account_baseline: float) -> float:
    pv = float(pattern.get("recent30_views") or pattern.get("avg_views") or 0)
    if pv > 0 and (pattern.get("uses") or 0) >= 3:
        return 0.6 * pv + 0.4 * account_baseline
    return account_baseline


def account_baseline_views(db: Database, default: float = 800.0) -> float:
    row = db.one(
        """SELECT AVG(v) a FROM (
             SELECT (SELECT views FROM post_metrics m WHERE m.post_id=p.post_id ORDER BY captured_at DESC LIMIT 1) v
             FROM posts p WHERE p.status='posted' ORDER BY p.posted_at DESC LIMIT 30)"""
    )
    if row and row["a"]:
        return float(row["a"])
    return default


def score_candidate(db: Database, settings: Settings, cand: dict, product: dict, pattern: dict,
                    recent_texts: list[str], post_cost_jpy: float, ai_cost_jpy: float) -> Scores:
    text = cand["text"]
    reasons: list[str] = []
    comp = product.get("erpi_components") or {}
    if isinstance(comp, str):
        comp = loads(comp, {})
    p_ctr = float(comp.get("p_ctr") or 0.008)
    p_cvr = float(comp.get("p_cvr") or 0.02)
    payout = float(comp.get("payout_jpy") or (float(product.get("price") or 0) * 0.2))

    # パターン実績で CTR を補正
    if (pattern.get("uses") or 0) >= 5 and pattern.get("recent30_ctr"):
        p_ctr = 0.5 * p_ctr + 0.5 * float(pattern["recent30_ctr"])

    sim = max_similarity(text, recent_texts)
    novelty = round(1 - sim, 3)
    same_recent = db.one(
        "SELECT COUNT(*) c FROM posts WHERE product_id=? AND status IN('posted','scheduled') "
        "AND created_at >= datetime('now','-14 days')", (product["content_id"],))
    spam = spam_risk_score(text, int(same_recent["c"]) if same_recent else 0)

    media_url = (product.get("sample_image_urls") or [None])[0] if pattern.get("media") != "video" else product.get("sample_movie_url")
    if isinstance(media_url, list):
        media_url = media_url[0] if media_url else None
    pol: PolicyResult = check_post(text, cand.get("reply_text"), media_url, bool(product.get("is_adult")), settings,
                                   site=product.get("site"), genres=product.get("genres") or [])

    views = expected_views(db, pattern, account_baseline_views(db))
    # 新規性・スパムリスクは表示数に効く（アルゴリズムの減衰を近似）
    views *= (0.6 + 0.4 * novelty) * (1 - 0.5 * spam)
    exp_rev = views * p_ctr * p_cvr * payout
    exp_cost = post_cost_jpy + ai_cost_jpy
    profit = exp_rev - exp_cost

    conf = float(pattern.get("confidence") or 0.2)
    if comp.get("measured_views", 0) > 5000:
        conf = min(0.95, conf + 0.2)

    if not pol.ok:
        decision = "human" if (pol.requires_human and not pol.hard_block) else "reject"
        reasons += pol.reasons
    elif sim >= SIMILARITY_REJECT:
        decision, reasons = "reject", reasons + [f"既存投稿と酷似 ({sim:.2f})"]
    elif sim >= SIMILARITY_REWRITE:
        decision, reasons = "rewrite", reasons + [f"類似度が高い ({sim:.2f})"]
    elif spam >= 0.7:
        decision, reasons = "reject", reasons + ["スパムリスク高"]
    elif profit < MIN_EXPECTED_REVENUE_JPY:
        decision, reasons = "reject", reasons + [f"期待利益がマイナス ({profit:.1f}円)"]
    else:
        decision = "accept"

    return Scores(round(p_ctr, 5), round(p_cvr, 5), novelty, round(spam, 3), round(pol.risk, 3), round(sim, 3),
                  round(views), round(exp_rev, 2), round(exp_cost, 2), round(profit, 2), round(conf, 3), decision, reasons)


def persist_scores(db: Database, candidate_id: int, s: Scores) -> None:
    status = {"accept": "scored", "rewrite": "rewrite", "reject": "rejected", "human": "human_review"}[s.decision]
    db.exec("UPDATE candidates SET scores=?, status=? WHERE id=?", (dumps(asdict(s)), status, candidate_id))
