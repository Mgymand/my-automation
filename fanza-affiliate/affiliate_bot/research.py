"""初回の市場調査パイプライン（X API の検索を使う。読取は $0.005/ポスト）。

- 検索クエリごとに公開ポストを収集し、Views/フォロワー、Views/経過時間、Engagement/Views を計算
- 「有名アカウント」ではなく「小規模でも異常に高い」投稿を抽出（views_per_follower 上位）
- 分類は Sonnet 5（使えなければルールベース）。文章はコピーせず、構造（フック/文章量/CTA/メディア）だけを特徴化
- 結果からパターン DB に新パターンを追加（confidence 0.3）
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone

from .db import Database, dumps, loads, utcnow
from .llm import LLMRouter, LLMUnavailable
from .patterns import add_pattern
from .x_client import to_jpy

DEFAULT_QUERIES = [
    "FANZA -is:retweet lang:ja has:media",
    "DMM 動画 -is:retweet lang:ja has:media",
    "新作 配信開始 動画 PR -is:retweet lang:ja",
    "セール OFF 動画 PR -is:retweet lang:ja",
]

CATEGORIES = ["女優訴求型", "作品訴求型", "シチュエーション訴求型", "期間限定訴求型", "ランキング型", "新作型",
              "発掘作品型", "画像主導型", "動画主導型", "短文型", "レビュー型", "ストーリー型", "その他"]


def features_of(text: str, media_type: str | None) -> dict:
    t = text or ""
    return {
        "length": len(re.sub(r"https?://\S+", "", t)),
        "lines": t.count("\n") + 1,
        "has_url": "http" in t,
        "hashtags": len(re.findall(r"#\S+", t)),
        "has_price": bool(re.search(r"\d+円|OFF|%|割引", t)),
        "has_date": bool(re.search(r"\d+/\d+|\d+月\d+日|本日|今日|配信開始", t)),
        "has_review_words": bool(re.search(r"レビュー|評価|★|☆", t)),
        "has_rank_words": bool(re.search(r"ランキング|1位|TOP|上位", t)),
        "first_chars": t[:12],
        "media_type": media_type or "none",
        "has_pr": bool(re.search(r"PR|広告|宣伝", t)),
    }


def rule_category(f: dict) -> str:
    if f["media_type"] == "video" and f["length"] < 40:
        return "動画主導型"
    if f["has_rank_words"]:
        return "ランキング型"
    if f["has_price"]:
        return "期間限定訴求型"
    if f["has_date"]:
        return "新作型"
    if f["has_review_words"]:
        return "レビュー型"
    if f["length"] < 30:
        return "短文型"
    if f["lines"] >= 3:
        return "ストーリー型"
    return "作品訴求型"


def collect(db: Database, x, usd_jpy: float, queries: list[str] | None = None, per_query: int = 100) -> int:
    n = 0
    total_cost = 0.0
    now = datetime.now(timezone.utc)
    for q in (queries or DEFAULT_QUERIES):
        data, cost = x.search_recent(q, max_results=min(per_query, 100))
        total_cost += cost
        users = {u["id"]: u for u in (data.get("includes") or {}).get("users", [])}
        media = {m["media_key"]: m for m in (data.get("includes") or {}).get("media", [])}
        for t in data.get("data") or []:
            pm = t.get("public_metrics") or {}
            u = users.get(t.get("author_id"), {})
            followers = int((u.get("public_metrics") or {}).get("followers_count") or 0)
            keys = (t.get("attachments") or {}).get("media_keys") or []
            mtype = media.get(keys[0], {}).get("type") if keys else None
            created = t.get("created_at")
            age_h = max(0.5, (now - datetime.fromisoformat(created.replace("Z", "+00:00"))).total_seconds() / 3600) if created else 24.0
            views = int(pm.get("impression_count") or 0)
            eng = sum(int(pm.get(k) or 0) for k in ("like_count", "retweet_count", "reply_count", "bookmark_count", "quote_count"))
            f = features_of(t.get("text", ""), mtype)
            db.exec(
                """INSERT OR IGNORE INTO research_posts(x_post_id,author_id,author_followers,text,has_media,media_type,created_at,
                   captured_at,views,likes,reposts,replies,bookmarks,quotes,age_hours,views_per_follower,views_per_hour,
                   engagement_rate,category,features) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (t["id"], t.get("author_id"), followers, t.get("text"), int(bool(keys)), mtype, created, utcnow(), views,
                 int(pm.get("like_count") or 0), int(pm.get("retweet_count") or 0), int(pm.get("reply_count") or 0),
                 int(pm.get("bookmark_count") or 0), int(pm.get("quote_count") or 0), age_h,
                 views / max(followers, 50), views / age_h, eng / views if views else 0, rule_category(f), dumps(f)),
            )
            n += 1
    if total_cost:
        db.add_cost("x_api", to_jpy(total_cost, usd_jpy), ref="research")
    return n


def import_csv(db: Database, text: str) -> int:
    """手動で集めた投稿データ（x_post_id,followers,text,media_type,created_at,views,likes,reposts,replies,bookmarks）"""
    n = 0
    now = datetime.now(timezone.utc)
    for row in csv.DictReader(io.StringIO(text)):
        views = int(row.get("views") or 0)
        followers = int(row.get("followers") or 0)
        created = row.get("created_at") or ""
        try:
            age_h = max(0.5, (now - datetime.fromisoformat(created)).total_seconds() / 3600)
        except ValueError:
            age_h = 24.0
        eng = sum(int(row.get(k) or 0) for k in ("likes", "reposts", "replies", "bookmarks"))
        f = features_of(row.get("text", ""), row.get("media_type"))
        db.exec(
            """INSERT OR IGNORE INTO research_posts(x_post_id,author_followers,text,has_media,media_type,created_at,captured_at,
               views,likes,reposts,replies,bookmarks,age_hours,views_per_follower,views_per_hour,engagement_rate,category,features)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (row.get("x_post_id"), followers, row.get("text"), int(bool(row.get("media_type"))), row.get("media_type"), created,
             utcnow(), views, int(row.get("likes") or 0), int(row.get("reposts") or 0), int(row.get("replies") or 0),
             int(row.get("bookmarks") or 0), age_h, views / max(followers, 50), views / age_h, eng / views if views else 0,
             rule_category(f), dumps(f)),
        )
        n += 1
    return n


def analyze(db: Database, llm: LLMRouter | None, top_n: int = 40) -> dict:
    """views_per_follower 上位を対象に、カテゴリ別の共通構造を抽出しパターン DB へ反映。"""
    rows = [dict(r) for r in db.q("SELECT * FROM research_posts WHERE views>0 ORDER BY views_per_follower DESC LIMIT ?", (top_n,))]
    if not rows:
        return {"analyzed": 0}
    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    summary = {}
    for cat, items in by_cat.items():
        fs = [loads(i["features"], {}) for i in items]
        summary[cat] = {
            "n": len(items),
            "avg_views_per_follower": sum(i["views_per_follower"] for i in items) / len(items),
            "avg_engagement": sum(i["engagement_rate"] for i in items) / len(items),
            "avg_length": sum(f.get("length", 0) for f in fs) / len(fs),
            "video_share": sum(1 for f in fs if f.get("media_type") == "video") / len(fs),
            "url_share": sum(1 for f in fs if f.get("has_url")) / len(fs),
            "pr_share": sum(1 for f in fs if f.get("has_pr")) / len(fs),
        }
    if llm is not None and llm.enabled:
        try:
            res = llm.call(
                "sonnet",
                "SNS 投稿の分析者です。与えられた投稿群から『なぜ伸びているか』を、文章をコピーせず構造（フック/文章量/訴求軸/CTA/メディア/時間帯）として抽象化し、パターン定義を JSON で返してください。",
                dumps({"summary": summary, "samples": [{"category": r["category"], "features": loads(r["features"], {}), "hour_utc": (r["created_at"] or "")[11:13],
                        "text_excerpt": (r["text"] or "")[:60]} for r in rows[:25]]}),
                schema={"type": "object", "properties": {"patterns": {"type": "array", "items": {"type": "object", "properties": {
                    "pattern_id": {"type": "string"}, "category": {"type": "string"}, "target": {"type": "string"}, "hook": {"type": "string"},
                    "structure": {"type": "string"}, "cta": {"type": "string"}, "media": {"type": "string"},
                    "best_hours": {"type": "array", "items": {"type": "integer"}}, "why_it_works": {"type": "string"}},
                    "required": ["pattern_id", "category", "target", "hook", "structure", "cta", "media", "best_hours", "why_it_works"],
                    "additionalProperties": False}}}, "required": ["patterns"], "additionalProperties": False},
                max_tokens=3000, ref="research_analyze",
            )
            for p in res.parsed.get("patterns", []):
                p["pattern_id"] = "R_" + re.sub(r"[^A-Za-z0-9_]", "", p["pattern_id"])[:20]
                p["confidence"] = 0.3
                add_pattern(db, p, source="research:x_search")
            summary["_llm_patterns"] = len(res.parsed.get("patterns", []))
        except LLMUnavailable as e:
            db.log_event("warn", "research_llm_skip", str(e))
    return {"analyzed": len(rows), "by_category": summary}
