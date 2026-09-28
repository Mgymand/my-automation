"""Thompson Sampling（Beta 分布）による探索・活用。

次元: hour_slot（3 時間刻み 8 枠）, pattern, genre, media, cta。
報酬は [0,1] に正規化した「表示あたり利益」（EPC × CTR を基準値で割ったもの）。
新規アームは Beta(1,1) から始まるため、自然に一定割合の探索が起きる。
"""
from __future__ import annotations

import random

from .db import Database, utcnow

SLOTS = [(0, 3), (3, 6), (6, 9), (9, 12), (12, 15), (15, 18), (18, 21), (21, 24)]
MIN_EXPLORE_RATE = 0.15   # 最低でもこの割合は非最良アームを試す（Thompson で足りない場合の保険）


def hour_slot(hour: int) -> str:
    for a, b in SLOTS:
        if a <= hour < b:
            return f"{a:02d}-{b:02d}"
    return "21-24"


def get_arms(db: Database, dimension: str) -> dict[str, tuple[float, float, int]]:
    return {r["arm"]: (r["alpha"], r["beta"], r["n"]) for r in db.q(
        "SELECT arm,alpha,beta,n FROM bandit_arms WHERE dimension=?", (dimension,))}


def ensure_arms(db: Database, dimension: str, arms: list[str]) -> None:
    for a in arms:
        db.exec("INSERT OR IGNORE INTO bandit_arms(dimension,arm,alpha,beta,n,reward_sum,updated_at) "
                "VALUES(?,?,1,1,0,0,?)", (dimension, a, utcnow()))


def choose(db: Database, dimension: str, candidates: list[str], rng: random.Random | None = None,
           prior_bonus: dict[str, float] | None = None) -> str:
    """Thompson Sampling。prior_bonus は事前知識（パターンの confidence 等）で平均を少し押し上げる。"""
    rng = rng or random.Random()
    if not candidates:
        raise ValueError("no candidates")
    ensure_arms(db, dimension, candidates)
    arms = get_arms(db, dimension)
    best, best_s = candidates[0], -1.0
    for c in candidates:
        a, b, _ = arms.get(c, (1.0, 1.0, 0))
        s = rng.betavariate(max(a, 0.01), max(b, 0.01))
        if prior_bonus and c in prior_bonus:
            s += prior_bonus[c] * 0.1
        if s > best_s:
            best, best_s = c, s
    # 探索の保険: 一定確率で未試行/試行数の少ないアームを選ぶ
    if rng.random() < MIN_EXPLORE_RATE:
        least = min(candidates, key=lambda c: arms.get(c, (1, 1, 0))[2])
        if arms.get(least, (1, 1, 0))[2] < 5:
            return least
    return best


def update(db: Database, dimension: str, arm: str, reward: float) -> None:
    reward = max(0.0, min(1.0, reward))
    ensure_arms(db, dimension, [arm])
    db.exec(
        "UPDATE bandit_arms SET alpha=alpha+?, beta=beta+?, n=n+1, reward_sum=reward_sum+?, updated_at=? "
        "WHERE dimension=? AND arm=?",
        (reward, 1 - reward, reward, utcnow(), dimension, arm),
    )


def normalize_reward(profit_per_view: float, baseline: float) -> float:
    """利益/表示 を 0..1 へ。baseline（直近中央値等）で 0.5 になるロジスティック。"""
    if baseline <= 0:
        baseline = 1e-4
    x = profit_per_view / baseline
    # x=0 → 0.27, x=1 → 0.5, x=3 → 0.82
    import math
    return 1 / (1 + math.exp(-(x - 1)))
