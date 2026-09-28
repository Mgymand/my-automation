"""Winning Pattern Database（Phase 3）。

各 Pattern は「成果が出る構造」の抽象化であり、他者の文章そのものは保持しない。
- 初期シードは公開調査からの仮説（confidence 0.2）。research が公開投稿から trend_score / last_seen を更新し、
  自分の投稿の実測（views_per_follower / engagement / CTR / EPC / conversions / profit）で上書きしていく。
- 30 日以上使われないパターンは減衰、十分な試行で直近利益がマイナスなら降格。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .db import Database, dumps, loads, utcnow

# pattern_id, pattern_name, category, hook, body_structure, cta_structure, media_type, ideal_length, ideal_hours,
# target_genre, target_actress_type
SEED_PATTERNS: list[dict] = [
    dict(pattern_id="P01_actress", pattern_name="女優訴求型", category="女優訴求型",
         hook="1行目に出演者名＋その人ならではの一言（役柄・雰囲気）", body_structure="出演者名+特徴 / 作品の見どころ1つ / 客観情報（配信日 or 価格）",
         cta_structure="リプ欄・詳細へ誘導する短い一言", media_type="image", ideal_length=80, ideal_hours=[21, 22, 23],
         target_genre="単体作品", target_actress_type="名前検索される人気・専属"),
    dict(pattern_id="P02_title", pattern_name="作品タイトル訴求型", category="作品タイトル訴求型",
         hook="タイトルの語感や設定を『どんな体験か』の一文に置き換える", body_structure="体験の一文 / ジャンル・尺 / 配信情報",
         cta_structure="サンプルへ誘導", media_type="image", ideal_length=70, ideal_hours=[12, 20, 22],
         target_genre="企画・ドラマ", target_actress_type="不問"),
    dict(pattern_id="P03_situation", pattern_name="シチュエーション訴求型", category="シチュエーション訴求型",
         hook="状況設定を情景描写で3行以内に", body_structure="情景 → 展開の示唆（結末は書かない） → 客観情報",
         cta_structure="『続きは』型", media_type="video", ideal_length=90, ideal_hours=[22, 23, 0],
         target_genre="シチュエーション系（人妻・OL・温泉 等）", target_actress_type="役柄が立つタイプ"),
    dict(pattern_id="P04_new", pattern_name="新作訴求型", category="新作訴求型",
         hook="『本日配信』『◯/◯配信開始』を先頭に", body_structure="日付 / 出演者・メーカー / 見どころ",
         cta_structure="配信ページへ", media_type="image", ideal_length=70, ideal_hours=[10, 12, 21],
         target_genre="新作全般", target_actress_type="新作を追われる人気女優"),
    dict(pattern_id="P05_discount", pattern_name="割引訴求型", category="割引訴求型",
         hook="割引率と期限を先頭に置く", body_structure="割引率・期限 / 対象作品の特徴 / 現在価格",
         cta_structure="期間内の確認を促す", media_type="image", ideal_length=70, ideal_hours=[7, 12, 21],
         target_genre="セール対象", target_actress_type="不問"),
    dict(pattern_id="P06_ranking", pattern_name="ランキング型", category="ランキング型",
         hook="『今週の◯◯ジャンル上位3本』などの枠組み提示", body_structure="枠組み / 3作品を1行ずつ（順位＋一言）",
         cta_structure="各作品の詳細へ", media_type="image", ideal_length=110, ideal_hours=[19, 20, 21],
         target_genre="ジャンル横断", target_actress_type="不問"),
    dict(pattern_id="P07_hidden", pattern_name="掘り出し物型", category="掘り出し物型",
         hook="『レビュー数は少ないが評価が高い』『埋もれている』という切り口", body_structure="発掘の理由（実データ） / 特徴",
         cta_structure="気になったら型", media_type="image", ideal_length=80, ideal_hours=[23, 0, 1],
         target_genre="レビュー少・評価高", target_actress_type="知名度は低いが評価が高い"),
    dict(pattern_id="P08_video", pattern_name="動画主導型", category="動画主導型",
         hook="文章は最小限。公式サンプル動画を主役に", body_structure="一文の説明 / PR",
         cta_structure="リプ欄・詳細", media_type="video", ideal_length=40, ideal_hours=[21, 22, 23, 0],
         target_genre="動画映えするジャンル", target_actress_type="不問"),
    dict(pattern_id="P09_image", pattern_name="画像主導型", category="画像主導型",
         hook="公式サンプル画像 2〜4 枚＋一言", body_structure="一言 / 客観情報",
         cta_structure="詳細へ", media_type="image", ideal_length=50, ideal_hours=[12, 18, 22],
         target_genre="ビジュアル重視", target_actress_type="不問"),
    dict(pattern_id="P10_short", pattern_name="短文型", category="短文型",
         hook="20〜40 字の一言", body_structure="一言のみ", cta_structure="なし or リプ欄",
         media_type="image", ideal_length=30, ideal_hours=[12, 18, 22], target_genre="不問", target_actress_type="不問"),
    dict(pattern_id="P11_review", pattern_name="長文レビュー型", category="長文レビュー型",
         hook="『レビュー平均◯.◯（△件）』の実データを先頭に", body_structure="実データ / 評価されているポイント（ジャンル・出演者から推定、捏造しない） / まとめ",
         cta_structure="レビュー全文へ", media_type="image", ideal_length=130, ideal_hours=[20, 21, 22],
         target_genre="レビュー多", target_actress_type="不問"),
    dict(pattern_id="P12_question", pattern_name="問いかけ型", category="問いかけ型",
         hook="1行目に読者への問い（『◯◯派？』『◯◯だと思ってた？』）", body_structure="問い / 答えの示唆 / 客観情報",
         cta_structure="答えは詳細で", media_type="image", ideal_length=70, ideal_hours=[21, 22],
         target_genre="不問", target_actress_type="不問"),
    dict(pattern_id="P13_surprise", pattern_name="意外性フック型", category="意外性フック型",
         hook="1行目に違和感・意外性（『これ本当に◯◯？』）、2行目に後半への期待", body_structure="違和感 / 期待 / CTA",
         cta_structure="矢印・『↓』型", media_type="video", ideal_length=60, ideal_hours=[22, 23],
         target_genre="展開のある作品", target_actress_type="不問"),
    dict(pattern_id="P14_number", pattern_name="数字型", category="数字型",
         hook="具体的な数字を先頭に（分数・本数・割引率・レビュー件数）", body_structure="数字 / その意味 / 客観情報",
         cta_structure="詳細へ", media_type="image", ideal_length=70, ideal_hours=[12, 20, 22],
         target_genre="総集編・ベスト・長尺", target_actress_type="不問"),
    dict(pattern_id="P15_series", pattern_name="シリーズ型", category="シリーズ型",
         hook="シリーズ名＋『第◯弾』『最新作』", body_structure="シリーズの位置づけ / 今作の違い / 客観情報",
         cta_structure="シリーズ一覧へ", media_type="image", ideal_length=80, ideal_hours=[20, 21, 22],
         target_genre="シリーズもの", target_actress_type="シリーズ常連"),
]

ANGLE_TO_PATTERN = {  # 5 案の訴求軸 → 既定パターン
    "A_short": "P10_short", "B_actress": "P01_actress", "C_situation": "P03_situation",
    "D_review": "P11_review", "E_price": "P05_discount",
}


def ensure_seed(db: Database) -> int:
    n = 0
    now = utcnow()
    for p in SEED_PATTERNS:
        if db.one("SELECT 1 FROM patterns WHERE pattern_id=?", (p["pattern_id"],)):
            continue
        db.exec(
            """INSERT INTO patterns(pattern_id,pattern_name,category,hook,body_structure,cta_structure,media_type,ideal_length,
               ideal_hours,target_genre,target_actress_type,confidence,status,source,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (p["pattern_id"], p["pattern_name"], p["category"], p["hook"], p["body_structure"], p["cta_structure"],
             p["media_type"], p["ideal_length"], dumps(p["ideal_hours"]), p["target_genre"], p["target_actress_type"],
             0.2, "active", "seed:public_web_research", now, now),
        )
        n += 1
    return n


def _row(r) -> dict:
    d = dict(r)
    d["ideal_hours"] = loads(d.get("ideal_hours"), [])
    return d


def active_patterns(db: Database) -> list[dict]:
    return [_row(r) for r in db.q("SELECT * FROM patterns WHERE status='active' ORDER BY pattern_id")]


def get_pattern(db: Database, pattern_id: str) -> dict | None:
    r = db.one("SELECT * FROM patterns WHERE pattern_id=?", (pattern_id,))
    return _row(r) if r else None


def mark_used(db: Database, pattern_id: str) -> None:
    db.exec("UPDATE patterns SET uses=uses+1, last_used_at=?, updated_at=? WHERE pattern_id=?", (utcnow(), utcnow(), pattern_id))


def add_pattern(db: Database, p: dict, source: str, confidence: float = 0.3) -> bool:
    now = utcnow()
    cur = db.exec(
        """INSERT OR IGNORE INTO patterns(pattern_id,pattern_name,category,hook,body_structure,cta_structure,media_type,ideal_length,
           ideal_hours,target_genre,target_actress_type,confidence,trend_score,last_seen,status,source,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (p["pattern_id"], p.get("pattern_name", p["pattern_id"]), p.get("category", "その他"), p.get("hook", ""),
         p.get("body_structure", ""), p.get("cta_structure", ""), p.get("media_type", "image"), int(p.get("ideal_length", 80)),
         dumps(p.get("ideal_hours", [21, 22])), p.get("target_genre", ""), p.get("target_actress_type", ""),
         confidence, float(p.get("trend_score", 0)), now, "active", source, now, now),
    )
    return cur.rowcount > 0


def update_trend(db: Database, category: str, trend_score: float, last_seen: str | None = None) -> None:
    """research の結果で同カテゴリのパターンの trend_score / last_seen を更新する。"""
    db.exec("UPDATE patterns SET trend_score=?, last_seen=?, updated_at=? WHERE category=?",
            (round(trend_score, 4), last_seen or utcnow(), utcnow(), category))


def update_from_results(db: Database) -> None:
    """自分の投稿実績からパターン統計を再計算する（決定論的）。"""
    now = datetime.now(timezone.utc)
    d30 = (now - timedelta(days=30)).isoformat(timespec="seconds")
    followers = int(db.one("SELECT COALESCE(MAX(followers),0) f FROM accounts")["f"] or 0)
    for r in db.q("SELECT pattern_id FROM patterns"):
        pid = r["pattern_id"]
        stats = db.q(
            """SELECT p.post_id, p.posted_at,
                 (SELECT views FROM post_metrics m WHERE m.post_id=p.post_id ORDER BY captured_at DESC LIMIT 1) views,
                 (SELECT likes+reposts+replies+bookmarks FROM post_metrics m WHERE m.post_id=p.post_id ORDER BY captured_at DESC LIMIT 1) eng,
                 (SELECT url_clicks FROM post_metrics m WHERE m.post_id=p.post_id ORDER BY captured_at DESC LIMIT 1) clicks,
                 (SELECT COALESCE(SUM(revenue_jpy*attribution_share),0) FROM conversions cv WHERE cv.post_id=p.post_id) revenue,
                 (SELECT COALESCE(SUM(attribution_share),0) FROM conversions cv WHERE cv.post_id=p.post_id) conv,
                 p.api_cost_jpy + p.ai_cost_jpy cost
               FROM posts p WHERE p.pattern_id=? AND p.status='posted'""", (pid,))
        if not stats:
            continue

        def agg(subset):
            n = len(subset)
            views = sum((s["views"] or 0) for s in subset)
            eng = sum((s["eng"] or 0) for s in subset)
            clicks = sum((s["clicks"] or 0) for s in subset)
            rev = sum(s["revenue"] or 0 for s in subset)
            conv = sum(s["conv"] or 0 for s in subset)
            cost = sum(s["cost"] or 0 for s in subset)
            return {"n": n, "avg_views": views / n if n else 0, "vpf": (views / n / followers) if (n and followers) else 0,
                    "eng": eng / views if views else 0, "ctr": clicks / views if views else 0,
                    "epc": rev / clicks if clicks else 0, "conv": conv, "profit": rev - cost}
        a, rec = agg(stats), agg([s for s in stats if (s["posted_at"] or "") >= d30])
        confidence = min(0.95, 0.2 + 0.75 * (1 - 1 / (1 + a["n"] / 15)))
        db.exec(
            """UPDATE patterns SET avg_views=?, views_per_follower=?, engagement_rate=?, ctr=?, epc=?, conversions=?, profit=?,
               recent30_views=?, recent30_ctr=?, recent30_epc=?, recent30_profit=?, confidence=?, updated_at=? WHERE pattern_id=?""",
            (a["avg_views"], a["vpf"], a["eng"], a["ctr"], a["epc"], int(round(a["conv"])), a["profit"],
             rec["avg_views"], rec["ctr"], rec["epc"], rec["profit"], confidence, utcnow(), pid),
        )


def decay_stale(db: Database, stale_days: int = 30) -> list[str]:
    now = datetime.now(timezone.utc)
    limit = (now - timedelta(days=stale_days)).isoformat(timespec="seconds")
    changed: list[str] = []
    for r in db.q("SELECT * FROM patterns WHERE status='active'"):
        pid = r["pattern_id"]
        last = r["last_used_at"] or r["last_seen"] or r["created_at"]
        if last < limit:
            db.exec("UPDATE patterns SET confidence=MAX(0.05, confidence*0.8), updated_at=? WHERE pattern_id=?", (utcnow(), pid))
            changed.append(pid)
        if (r["uses"] or 0) >= 20 and (r["recent30_profit"] or 0) < 0 and (r["confidence"] or 0) > 0.6:
            db.exec("UPDATE patterns SET status='demoted', updated_at=? WHERE pattern_id=?", (utcnow(), pid))
            changed.append(pid)
    return changed
