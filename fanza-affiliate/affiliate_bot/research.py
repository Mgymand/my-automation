"""公開 X 投稿の継続調査（READ ONLY）。

- 検索クエリごとに公開投稿を収集し、文章そのものではなく「成果が出る構造」を特徴量として保存する
- 比率指標: views_per_follower / views_per_hour / engagement_rate / likes_per_1k_views / reposts_per_1k_views
- 小規模アカウントなのに成果が良い投稿を outlier_score で優先
- 分類（15 カテゴリ + α）はルールベース、LLM（Sonnet）が使えれば上書き・抽象化してパターン DB を更新
- 他者の文章・画像・動画は転載しない。保存する text は分析用で、生成には構造のみを渡す
"""
from __future__ import annotations

import csv
import io
import math
import re
from datetime import datetime, timezone

from .db import Database, dumps, loads, utcnow
from .llm import LLMRouter, LLMUnavailable
from .patterns import add_pattern, update_trend
from .x_client import to_jpy

# 複数ジャンル・複数アカウントから集めるための既定クエリ（1 クエリ最大 100 件・$0.005/件）。
# 2026-09 の公開調査（docs/ACCOUNT_RESEARCH.md）で活発だった型を網羅する。
DEFAULT_QUERIES = [
    "FANZA セール OFF -is:retweet lang:ja",                 # セール速報型
    "FANZA (100円 OR 10円 OR 半額) -is:retweet lang:ja",    # 激安・価格訴求型
    "FANZA 新作 配信 -is:retweet lang:ja",                  # 新作速報型
    "FANZA 女優 -is:retweet lang:ja has:media",             # 女優訴求型
    "FANZA レビュー -is:retweet lang:ja",                   # レビュー型 / 掘り出し物型
    "FANZA ランキング -is:retweet lang:ja",                 # ランキング型 / まとめ型
    "FANZA -is:retweet lang:ja has:videos",                 # 動画主導型
    "FANZA (今夜 OR 今日の1本 OR おすすめ) -is:retweet lang:ja",  # キャラクター人格型 / 一言フック型
]

CATEGORIES = ["女優訴求型", "作品タイトル訴求型", "シチュエーション訴求型", "新作訴求型", "割引訴求型", "ランキング型", "掘り出し物型",
              "動画主導型", "画像主導型", "短文型", "長文レビュー型", "問いかけ型", "意外性フック型", "数字型", "シリーズ型",
              "セール速報型", "激安・価格訴求型", "まとめ型", "キャラクター人格型", "その他"]
PERSONA_RE = re.compile(r"(おはよ|こんばんは|にゃ|ぼく|わたし|今日の1本|今夜の一本|今日のおすすめ|案内人|発掘|チェックしてきました)")
ROUNDUP_RE = re.compile(r"(まとめ|\d+選|(?:[2-9]|\d{2,})本|安い順|多い順|TOP\d|上位\d)")
DEADLINE_RE = re.compile(r"(まで|締切|残り|期限|\d{1,2}:\d{2}|\d{1,2}/\d{1,2})")

EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐‼⁉\U0001F900-\U0001F9FF]")
CTA_RE = re.compile(r"(続き|リプ欄|↓|詳細|こちら|チェック|見て|プロフ|固定|サンプル)")
QUESTION_RE = re.compile(r"[？?]|どっち|派\b|思って")
SURPRISE_RE = re.compile(r"本当に|マジで|まさか|ヤバ|やば|意外|想像以上|嘘でしょ|え、")
NUMBER_RE = re.compile(r"\d+(分|時間|本|作品|件|%|％|円|位)")
ACTRESS_RE = re.compile(r"([一-龥ぁ-んァ-ヶ]{2,4}[ 　]?[一-龥ぁ-んァ-ヶ]{2,5})(?:ちゃん|さん)")
GENRE_WORDS = ["人妻", "OL", "素人", "巨乳", "痴女", "熟女", "美少女", "ギャル", "コスプレ", "温泉", "ナース", "教師", "NTR", "寝取", "企画", "ドラマ", "ベスト", "総集編", "VR"]


def text_features(text: str, post: dict | None = None) -> dict:
    """投稿から構造特徴を抽出（LLM なし）。"""
    t = text or ""
    body = re.sub(r"https?://\S+", "", t).strip()
    lines = [ln for ln in body.split("\n")]
    first = lines[0] if lines else ""
    url_pos = None
    if "http" in t:
        idx = t.find("http")
        url_pos = "head" if idx < 20 else ("tail" if idx > len(t) - 40 else "middle")
    price = re.search(r"(\d{2,5})円", body)
    disc = re.search(r"(\d{1,2})[%％]\s?(OFF|off|オフ|引)", body)
    rank = re.search(r"(\d{1,3})位", body)
    genres = [g for g in GENRE_WORDS if g in body]
    actress = ACTRESS_RE.search(body)
    p = post or {}
    return {
        "length": len(body), "lines": len(lines), "first_len": len(first), "first_chars": first[:12],
        "cta": bool(CTA_RE.search(body)), "emoji": len(EMOJI_RE.findall(body)),
        "hashtags": len(re.findall(r"[#＃]\S+", body)),
        "media_types": p.get("media_types", []), "image_count": p.get("image_count", 0),
        "has_video": bool(p.get("has_video")), "video_seconds": p.get("video_seconds", 0.0),
        "link_position": url_pos, "actress": actress.group(1) if actress else None,
        "genres": genres, "is_new": bool(re.search(r"新作|配信開始|本日", body)), "price": int(price.group(1)) if price else None,
        "discount": int(disc.group(1)) if disc else None, "ranking": int(rank.group(1)) if rank else None,
        "question": bool(QUESTION_RE.search(first)), "surprise": bool(SURPRISE_RE.search(first)),
        "number_first": bool(NUMBER_RE.search(first)), "series": bool(re.search(r"シリーズ|第\d+弾|最新作", body)),
        "review_words": bool(re.search(r"レビュー|評価|★|☆", body)),
        "persona": bool(PERSONA_RE.search(first)), "roundup": bool(ROUNDUP_RE.search(first)), "deadline": bool(DEADLINE_RE.search(body)),
        "cta_position": ("tail" if CTA_RE.search(lines[-1] if lines else "") else ("head" if CTA_RE.search(first) else ("middle" if CTA_RE.search(body) else None))),
    }


def rule_category(f: dict) -> tuple[str, str]:
    """(category, hook_type)"""
    if f["surprise"]:
        return "意外性フック型", "違和感→期待"
    if f["question"]:
        return "問いかけ型", "問い"
    if f["ranking"] or re.search(r"ランキング|TOP|上位", f["first_chars"]):
        return "ランキング型", "枠組み提示"
    if f.get("roundup"):
        return "まとめ型", "集計の切り口"
    if f["discount"] and f.get("deadline"):
        return "セール速報型", "割引＋期限"
    if f["price"] is not None and f["price"] <= 300:
        return "激安・価格訴求型", "具体価格先頭"
    if f["discount"]:
        return "割引訴求型", "割引先頭"
    if f.get("persona") and f["lines"] >= 2:
        return "キャラクター人格型", "挨拶＋人格"
    if f["number_first"]:
        return "数字型", "数字先頭"
    if f["series"]:
        return "シリーズ型", "シリーズ名"
    if f["has_video"] and f["length"] < 50:
        return "動画主導型", "最小文＋動画"
    if f["image_count"] >= 2 and f["length"] < 60:
        return "画像主導型", "一言＋画像"
    if f["is_new"]:
        return "新作訴求型", "日付先頭"
    if f["review_words"]:
        return "長文レビュー型" if f["length"] >= 100 else "掘り出し物型", "実データ先頭"
    if f["actress"] and f["first_len"] <= 20:
        return "女優訴求型", "出演者名先頭"
    if f["length"] < 35:
        return "短文型", "一言"
    if f["lines"] >= 3:
        return "シチュエーション訴求型", "情景描写"
    return "作品タイトル訴求型", "体験の一文"


def ratios(post: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    created = post.get("created_at")
    try:
        age_h = max(0.5, (now - datetime.fromisoformat(str(created).replace("Z", "+00:00"))).total_seconds() / 3600)
    except (ValueError, TypeError):
        age_h = 24.0
    views = int(post.get("views") or 0)
    followers = int(post.get("author_followers") or 0)
    eng = sum(int(post.get(k) or 0) for k in ("likes", "reposts", "replies", "bookmarks", "quotes"))
    vpf = views / max(followers, 50)
    vph = views / age_h
    er = eng / views if views else 0.0
    l1k = int(post.get("likes") or 0) / views * 1000 if views else 0.0
    r1k = int(post.get("reposts") or 0) / views * 1000 if views else 0.0
    # 小規模アカウントの外れ値: フォロワーが少ないほど、views/follower が高いほど大きい
    outlier = math.log1p(vpf) * (1 + 1 / math.log10(max(followers, 10) + 10)) * (1 + er * 10)
    return {"age_hours": round(age_h, 1), "views_per_follower": round(vpf, 4), "views_per_hour": round(vph, 2),
            "engagement_rate": round(er, 5), "likes_per_1k_views": round(l1k, 3), "reposts_per_1k_views": round(r1k, 3),
            "outlier_score": round(outlier, 4)}


def store_post(db: Database, post: dict, source: str = "x_api") -> bool:
    f = text_features(post.get("text", ""), post)
    cat, hook = rule_category(f)
    r = ratios(post)
    cur = db.exec(
        """INSERT OR IGNORE INTO research_posts(x_post_id,author_id,author_username,author_followers,text,created_at,captured_at,age_hours,
           views,likes,reposts,replies,bookmarks,quotes,views_per_follower,views_per_hour,engagement_rate,likes_per_1k_views,
           reposts_per_1k_views,outlier_score,category,hook_type,features,source)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (post.get("x_post_id"), post.get("author_id"), post.get("author_username"), int(post.get("author_followers") or 0),
         post.get("text"), post.get("created_at"), utcnow(), r["age_hours"], int(post.get("views") or 0), int(post.get("likes") or 0),
         int(post.get("reposts") or 0), int(post.get("replies") or 0), int(post.get("bookmarks") or 0), int(post.get("quotes") or 0),
         r["views_per_follower"], r["views_per_hour"], r["engagement_rate"], r["likes_per_1k_views"], r["reposts_per_1k_views"],
         r["outlier_score"], cat, hook, dumps(f), source),
    )
    return cur.rowcount > 0


def collect(db: Database, x, usd_jpy: float, queries: list[str] | None = None, per_query: int = 100) -> int:
    n = 0
    total_cost = 0.0
    for q in (queries or DEFAULT_QUERIES):
        posts, _, cost = x.search_recent(q, max_results=min(per_query, 100))
        total_cost += cost
        for p in posts:
            if store_post(db, p):
                n += 1
    if total_cost:
        db.add_cost("x_api", to_jpy(total_cost, usd_jpy), ref="research")
    db.set_setting("last_research_at", utcnow())
    return n


def import_csv(db: Database, text: str) -> int:
    """手動で集めた公開投稿データ。列: x_post_id, followers, text, media_type, created_at, views, likes, reposts, replies, bookmarks"""
    n = 0
    for row in csv.DictReader(io.StringIO(text)):
        mt = (row.get("media_type") or "").strip()
        post = {"x_post_id": row.get("x_post_id"), "author_followers": int(row.get("followers") or 0),
                "text": (row.get("text") or "").replace("\\n", "\n"),   # CSV 内の改行は \n 表記を許容
                "created_at": row.get("created_at"), "views": int(row.get("views") or 0), "likes": int(row.get("likes") or 0),
                "reposts": int(row.get("reposts") or 0), "replies": int(row.get("replies") or 0), "bookmarks": int(row.get("bookmarks") or 0),
                "media_types": [mt] if mt else [], "image_count": 1 if mt == "photo" else 0, "has_video": mt == "video",
                "video_seconds": float(row.get("video_seconds") or 0)}
        if store_post(db, post, source="csv"):
            n += 1
    return n


def top_outliers(db: Database, limit: int = 40) -> list[dict]:
    return [dict(r) for r in db.q("SELECT * FROM research_posts WHERE views>0 ORDER BY outlier_score DESC LIMIT ?", (limit,))]


def analyze(db: Database, llm: LLMRouter | None, top_n: int = 40) -> dict:
    """外れ値上位を対象にカテゴリ別の構造をまとめ、trend_score / last_seen を更新。LLM があれば新パターンを抽象化して追加。"""
    rows = top_outliers(db, top_n)
    if not rows:
        return {"analyzed": 0}
    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    summary: dict[str, dict] = {}
    max_score = max(r["outlier_score"] for r in rows) or 1.0
    for cat, items in by_cat.items():
        fs = [loads(i["features"], {}) for i in items]
        trend = sum(i["outlier_score"] for i in items) / len(rows) / max_score * len(items)
        summary[cat] = {
            "n": len(items), "trend_score": round(trend, 4),
            "avg_views_per_follower": round(sum(i["views_per_follower"] for i in items) / len(items), 3),
            "avg_engagement": round(sum(i["engagement_rate"] for i in items) / len(items), 4),
            "avg_length": round(sum(f.get("length", 0) for f in fs) / len(fs)),
            "avg_lines": round(sum(f.get("lines", 1) for f in fs) / len(fs), 1),
            "video_share": round(sum(1 for f in fs if f.get("has_video")) / len(fs), 2),
            "cta_share": round(sum(1 for f in fs if f.get("cta")) / len(fs), 2),
            "hours_utc": sorted({(i["created_at"] or "")[11:13] for i in items if i["created_at"]}),
        }
        update_trend(db, cat, trend, max((i["created_at"] or "") for i in items) or None)
    if llm is not None and llm.enabled:
        try:
            res = llm.call(
                "sonnet",
                "SNS 投稿の分析者です。与えられた投稿群から『なぜ伸びているか』を、文章をコピーせず構造（フック/本文構成/CTA/メディア/長さ/時間帯/対象ジャンル・女優タイプ）"
                "として抽象化し、既存カテゴリに無い新しい型があればパターン定義を JSON で返してください。文章の再利用・引用は禁止。",
                dumps({"summary": summary, "samples": [{"category": r["category"], "hook_type": r["hook_type"], "features": loads(r["features"], {}),
                                                        "hour_utc": (r["created_at"] or "")[11:13], "views_per_follower": r["views_per_follower"]} for r in rows[:25]]}),
                schema={"type": "object", "properties": {"patterns": {"type": "array", "items": {"type": "object", "properties": {
                    "pattern_id": {"type": "string"}, "pattern_name": {"type": "string"}, "category": {"type": "string"}, "hook": {"type": "string"},
                    "body_structure": {"type": "string"}, "cta_structure": {"type": "string"}, "media_type": {"type": "string"},
                    "ideal_length": {"type": "integer"}, "ideal_hours": {"type": "array", "items": {"type": "integer"}},
                    "target_genre": {"type": "string"}, "target_actress_type": {"type": "string"}, "why_it_works": {"type": "string"}},
                    "required": ["pattern_id", "pattern_name", "category", "hook", "body_structure", "cta_structure", "media_type", "ideal_length",
                                 "ideal_hours", "target_genre", "target_actress_type", "why_it_works"], "additionalProperties": False}}},
                        "required": ["patterns"], "additionalProperties": False},
                max_tokens=3000, ref="research_analyze",
            )
            added = 0
            for p in res.parsed.get("patterns", []):
                p["pattern_id"] = "R_" + re.sub(r"[^A-Za-z0-9_]", "", p["pattern_id"])[:20]
                if add_pattern(db, p, source="research:x_search"):
                    added += 1
            summary["_llm_patterns_added"] = added
        except LLMUnavailable as e:
            db.log_event("warn", "research_llm_skip", str(e))
    db.set_setting("last_research_analyze_at", utcnow())
    return {"analyzed": len(rows), "by_category": summary}


def similar_success(db: Database, category: str, genres: list[str] | None = None) -> dict | None:
    """投稿パッケージに添える『類似成功投稿』（Post ID と簡潔な成功理由）。"""
    rows = db.q("SELECT * FROM research_posts WHERE category=? AND views>0 ORDER BY outlier_score DESC LIMIT 5", (category,))
    if not rows:   # 同カテゴリが無ければ全体の外れ値上位（構造の参考として）
        rows = db.q("SELECT * FROM research_posts WHERE views>0 ORDER BY outlier_score DESC LIMIT 3")
    if not rows:
        return None
    best = rows[0]
    for r in rows:
        f = loads(r["features"], {})
        if genres and set(f.get("genres", [])) & set(genres):
            best = r
            break
    f = loads(best["features"], {})
    why = (f"{best['category']}。フォロワー {best['author_followers']:,} に対し表示 {best['views']:,}（{best['views_per_follower']:.1f}倍）、"
           f"文字数 {f.get('length')}・{f.get('lines')}行・{'動画' if f.get('has_video') else '画像' if f.get('image_count') else 'テキスト'}"
           f"{'・CTAあり' if f.get('cta') else ''}")
    return {"x_post_id": best["x_post_id"], "reason": why}
