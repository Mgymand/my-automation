"""投稿文の類似度（文字 3-gram の Jaccard）。LLM を使わない決定論的処理。"""
from __future__ import annotations

import re


def normalize(text: str) -> str:
    t = re.sub(r"https?://\S+", "", text)
    t = re.sub(r"[#＃]\S+", "", t)
    t = re.sub(r"\s+", "", t)
    return t.lower()


def ngrams(text: str, n: int = 3) -> set[str]:
    t = normalize(text)
    if len(t) < n:
        return {t} if t else set()
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def jaccard(a: str, b: str, n: int = 3) -> float:
    ga, gb = ngrams(a, n), ngrams(b, n)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def max_similarity(text: str, corpus: list[str]) -> float:
    return max((jaccard(text, c) for c in corpus), default=0.0)
