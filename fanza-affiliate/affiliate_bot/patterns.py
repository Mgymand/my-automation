"""Winning Pattern Database。

初期パターンは公開 Web 調査（docs/MARKET_RESEARCH.md）から構造だけを抽象化したもので、
confidence は低い（0.2）。実測が入るたびに update_from_results() で更新し、
30 日以上使われない／成績が悪いパターンは自動で減衰させる。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .db import Database, dumps, loads, utcnow

# category, target, hook(構造の説明。コピーではない), structure, cta, media, best_hours
SEED_PATTERNS: list[dict] = [
    {
        "pattern_id": "P01_actress",
        "category": "女優訴求型",
        "target": "特定女優のファン・名前検索層",
        "hook": "冒頭に出演者名＋作品の一言特徴（『◯◯の最新作、テーマは△△』）",
        "structure": "1行目: 出演者名+特徴 / 2行目: 見どころ1つ / 3行目: 価格or配信状況 / 末尾: PR表記",
        "cta": "詳細はリプ欄のリンクから",
        "media": "image",
        "best_hours": [21, 22, 23],
    },
    {
        "pattern_id": "P02_title",
        "category": "作品訴求型",
        "target": "ジャンル固定のフォロワー",
        "hook": "作品タイトルではなく『どんな体験か』を1文で言い切る",
        "structure": "体験の一文 / ジャンル・尺・形式 / PR表記",
        "cta": "サンプルはリプ欄",
        "media": "image",
        "best_hours": [12, 20, 22],
    },
    {
        "pattern_id": "P03_situation",
        "category": "シチュエーション訴求型",
        "target": "シチュエーション好き（特定ジャンル層）",
        "hook": "状況設定を短い情景描写で提示（3行以内）",
        "structure": "情景 → 展開の示唆 → PR表記",
        "cta": "続きはリプ欄",
        "media": "video",
        "best_hours": [22, 23, 0],
    },
    {
        "pattern_id": "P04_limited",
        "category": "期間限定訴求型",
        "target": "価格に敏感な購入検討層",
        "hook": "割引率と終了日を先頭に置く（『◯%OFF・△日まで』）",
        "structure": "割引情報 / 対象作品の特徴 / 終了日 / PR表記",
        "cta": "セール期間中に確認",
        "media": "image",
        "best_hours": [7, 12, 21],
    },
    {
        "pattern_id": "P05_ranking",
        "category": "ランキング型",
        "target": "何を見るか迷っている層",
        "hook": "『今週の◯◯ジャンル上位3本』のような枠組み提示",
        "structure": "枠組み / 3作品を1行ずつ / PR表記",
        "cta": "各作品の詳細はリプ欄",
        "media": "image",
        "best_hours": [19, 20, 21],
    },
    {
        "pattern_id": "P06_newrelease",
        "category": "新作型",
        "target": "新作をチェックする常連層",
        "hook": "『本日配信開始』『◯月◯日リリース』を先頭に",
        "structure": "日付 / 出演者・メーカー / 見どころ / PR表記",
        "cta": "配信ページはリプ欄",
        "media": "image",
        "best_hours": [10, 12, 21],
    },
    {
        "pattern_id": "P07_discovery",
        "category": "発掘作品型",
        "target": "定番に飽きた層",
        "hook": "『埋もれている』『レビュー数は少ないが評価が高い』という切り口",
        "structure": "発掘の理由 / 客観的な事実（レビュー平均・件数） / PR表記",
        "cta": "気になったらリプ欄",
        "media": "image",
        "best_hours": [23, 0, 1],
    },
    {
        "pattern_id": "P08_video",
        "category": "動画主導型",
        "target": "タイムラインで動画を見る層",
        "hook": "文章は最小限、DMM 提供サンプル動画（公式ツール）を主役に",
        "structure": "1文の説明 / PR表記 / 動画",
        "cta": "リプ欄に配信ページ",
        "media": "video",
        "best_hours": [21, 22, 23, 0],
    },
    {
        "pattern_id": "P09_short",
        "category": "短文型",
        "target": "スクロール速度の速い層",
        "hook": "20〜40文字の一言＋画像",
        "structure": "一言 / PR表記",
        "cta": "リプ欄",
        "media": "image",
        "best_hours": [12, 18, 22],
    },
    {
        "pattern_id": "P10_review",
        "category": "レビュー型",
        "target": "評価を重視する慎重な購入層",
        "hook": "『レビュー平均◯.◯（△件）』という実データを先頭に",
        "structure": "実データ / 評価されているポイント（ジャンル・出演者から推定、捏造しない） / PR表記",
        "cta": "レビュー全文はリプ欄から",
        "media": "image",
        "best_hours": [20, 21, 22],
    },
    {
        "pattern_id": "P11_story",
        "category": "ストーリー型",
        "target": "物語性を重視する層",
        "hook": "作品の設定を『あらすじ風』に2〜3行",
        "structure": "設定 / 転換点の示唆 / PR表記",
        "cta": "続きはリプ欄",
        "media": "image",
        "best_hours": [22, 23],
    },
    {
        "pattern_id": "P12_price",
        "category": "価格訴求型",
        "target": "低価格・お試し層",
        "hook": "価格（例: ◯◯円）を先頭に置き、コスパを訴求",
        "structure": "価格 / 内容の要約 / PR表記",
        "cta": "価格の確認はリプ欄",
        "media": "image",
        "best_hours": [7, 12, 19],
    },
]


def ensure_seed(db: Database) -> int:
    n = 0
    now = utcnow()
    for p in SEED_PATTERNS:
        if db.one("SELECT 1 FROM patterns WHERE pattern_id=?", (p["pattern_id"],)):
            continue
        db.exec(
            "INSERT INTO patterns(pattern_id,category,target,hook,structure,cta,media,best_hours,confidence,status,"
            "source,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (p["pattern_id"], p["category"], p["target"], p["hook"], p["structure"], p["cta"], p["media"],
             dumps(p["best_hours"]), 0.2, "active", "seed:public_web_research", now, now),
        )
        n += 1
    return n


def active_patterns(db: Database) -> list[dict]:
    rows = db.q("SELECT * FROM patterns WHERE status='active' ORDER BY pattern_id")
    out = []
    for r in rows:
        d = dict(r)
        d["best_hours"] = loads(d.get("best_hours"), [])
        out.append(d)
    return out


def mark_used(db: Database, pattern_id: str) -> None:
    db.exec("UPDATE patterns SET uses=uses+1, last_used_at=?, updated_at=? WHERE pattern_id=?",
            (utcnow(), utcnow(), pattern_id))


def update_from_results(db: Database) -> None:
    """投稿実績からパターン統計を再計算する（決定論的）。"""
    now = datetime.now(timezone.utc)
    d30 = (now - timedelta(days=30)).isoformat(timespec="seconds")
    rows = db.q("SELECT pattern_id FROM patterns")
    for r in rows:
        pid = r["pattern_id"]
        # 各投稿の最新メトリクス
        stats = db.q(
            """
            SELECT p.post_id, p.posted_at,
                   (SELECT views FROM post_metrics m WHERE m.post_id=p.post_id ORDER BY captured_at DESC LIMIT 1) views,
                   (SELECT url_clicks FROM post_metrics m WHERE m.post_id=p.post_id ORDER BY captured_at DESC LIMIT 1) url_clicks,
                   (SELECT COUNT(*) FROM clicks c WHERE c.tracking_code=p.tracking_code) clicks,
                   (SELECT COALESCE(SUM(revenue_jpy),0) FROM conversions cv WHERE cv.post_id=p.post_id) revenue,
                   (SELECT COUNT(*) FROM conversions cv WHERE cv.post_id=p.post_id) conv,
                   p.api_cost_jpy + p.ai_cost_jpy cost
            FROM posts p WHERE p.pattern_id=? AND p.status='posted'
            """,
            (pid,),
        )
        if not stats:
            continue
        def agg(subset):
            views = sum((s["views"] or 0) for s in subset)
            clicks = sum(max(s["clicks"] or 0, s["url_clicks"] or 0) for s in subset)
            rev = sum(s["revenue"] or 0 for s in subset)
            conv = sum(s["conv"] or 0 for s in subset)
            cost = sum(s["cost"] or 0 for s in subset)
            n = len(subset)
            return {
                "n": n,
                "avg_views": views / n if n else 0,
                "ctr": clicks / views if views else 0,
                "cvr": conv / clicks if clicks else 0,
                "epc": rev / clicks if clicks else 0,
                "profit": rev - cost,
            }
        all_ = agg(stats)
        recent = agg([s for s in stats if (s["posted_at"] or "") >= d30])
        # 信頼度: サンプル数に応じて 0.2 → 0.95 に漸近
        n = all_["n"]
        confidence = min(0.95, 0.2 + 0.75 * (1 - 1 / (1 + n / 15)))
        db.exec(
            "UPDATE patterns SET avg_views=?, avg_ctr=?, avg_cvr=?, avg_epc=?, recent30_views=?, recent30_ctr=?, "
            "recent30_epc=?, recent30_profit=?, confidence=?, updated_at=? WHERE pattern_id=?",
            (all_["avg_views"], all_["ctr"], all_["cvr"], all_["epc"], recent["avg_views"], recent["ctr"],
             recent["epc"], recent["profit"], confidence, utcnow(), pid),
        )


def decay_stale(db: Database, stale_days: int = 30) -> list[str]:
    """古いパターンの評価を自動で下げる。30 日超未使用は confidence を 20% 減らし、
    十分なサンプルがあり直近 30 日の利益がマイナスなら 'demoted' にする。"""
    now = datetime.now(timezone.utc)
    limit = (now - timedelta(days=stale_days)).isoformat(timespec="seconds")
    changed: list[str] = []
    for r in db.q("SELECT * FROM patterns WHERE status='active'"):
        pid = r["pattern_id"]
        last = r["last_used_at"] or r["created_at"]
        if last < limit:
            db.exec("UPDATE patterns SET confidence=MAX(0.05, confidence*0.8), updated_at=? WHERE pattern_id=?",
                    (utcnow(), pid))
            changed.append(pid)
        if (r["uses"] or 0) >= 20 and (r["recent30_profit"] or 0) < 0 and (r["confidence"] or 0) > 0.6:
            db.exec("UPDATE patterns SET status='demoted', updated_at=? WHERE pattern_id=?", (utcnow(), pid))
            changed.append(pid)
    return changed


def add_pattern(db: Database, p: dict, source: str) -> None:
    now = utcnow()
    db.exec(
        "INSERT OR IGNORE INTO patterns(pattern_id,category,target,hook,structure,cta,media,best_hours,confidence,"
        "status,source,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (p["pattern_id"], p["category"], p.get("target", ""), p.get("hook", ""), p.get("structure", ""),
         p.get("cta", ""), p.get("media", "image"), dumps(p.get("best_hours", [21, 22])), float(p.get("confidence", 0.2)),
         "active", source, now, now),
    )
