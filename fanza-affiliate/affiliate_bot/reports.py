"""日次レポートと週次レビュー（Phase 3）。

日次（毎朝）:
  最上部: 本日の投稿時刻表（11:30 POST 1 …）
  次に:   昨日の実績（売上 / 報酬 / Views / 平均 Views / 最良・最低投稿 / CTR 推定 / CV / EPC / 投稿あたり利益）
  次に:   AI の判断（昨日分かったこと / 今日増やす / 今日減らす / 新しく試す）— Opus 5.5。なければルールベース
  最後:   本日の調整（動画比率・ジャンル・Pattern 停止・時間帯強化）を 4 行程度
週次（7 日に 1 回のみ Fable 5.1）: 7 日 / 30 日 / 全期間を比較し、来週増やす・減らす・試す・削除/追加 Pattern を決定。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import bandit
from .config import Settings
from .db import Database, dumps, loads, utcnow
from .llm import LLMRouter, LLMUnavailable
from .metrics import post_profit_rows
from .packages import render_schedule, render_text
from .planner import today_packages


def _day_bounds(settings: Settings, day: datetime | None = None) -> tuple[str, str, str]:
    tz = ZoneInfo(settings.timezone)
    d = (day or (datetime.now(tz) - timedelta(days=1))).astimezone(tz)
    start = d.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.strftime("%Y-%m-%d"), start.astimezone(timezone.utc).isoformat(timespec="seconds"), end.astimezone(timezone.utc).isoformat(timespec="seconds")


def summarize_day(db: Database, settings: Settings, day: datetime | None = None) -> dict:
    label, a, b = _day_bounds(settings, day)
    rows = [r for r in post_profit_rows(db, days=40) if a <= (r["posted_at"] or "") < b]
    views = sum(r["views"] for r in rows)
    clicks = sum(r["clicks"] for r in rows)
    conv_row = db.one("SELECT COALESCE(SUM(attribution_share),0) c, COALESCE(SUM(revenue_jpy*attribution_share),0) r FROM conversions WHERE ts>=? AND ts<? AND post_id IS NOT NULL", (a, b))
    unattr = db.one("SELECT COALESCE(SUM(revenue_jpy),0) r FROM conversions WHERE ts>=? AND ts<? AND post_id IS NULL", (a, b))
    conv, revenue = float(conv_row["c"]), float(conv_row["r"])
    revenue_total = revenue + float(unattr["r"])
    ai_cost = db.cost_between(a, b, "ai")
    api_cost = db.cost_between(a, b, "x_api") + db.cost_between(a, b, "dmm_api")
    infra = (settings.infra_cost_month_jpy + settings.other_cost_month_jpy) / 30
    profit = revenue_total - ai_cost - api_cost - infra
    best = max(rows, key=lambda r: (r["revenue"], r["views"]), default=None)
    worst = min(rows, key=lambda r: (r["revenue"], r["views"]), default=None)
    by_pat: dict[str, dict] = {}
    for r in rows:
        d = by_pat.setdefault(r["pattern_id"], {"posts": 0, "views": 0, "revenue": 0.0, "eng": 0})
        d["posts"] += 1; d["views"] += r["views"]; d["revenue"] += r["revenue"] or 0; d["eng"] += r["eng"]
    return {"day": label, "posts": len(rows), "views": views, "avg_views": views / len(rows) if rows else 0, "clicks": clicks,
            "ctr_est": clicks / views if views else 0.0, "conversions": conv, "revenue_jpy": revenue_total, "attributed_revenue_jpy": revenue,
            "epc": revenue / clicks if clicks else 0.0, "ai_cost_jpy": ai_cost, "api_cost_jpy": api_cost, "infra_cost_jpy": infra,
            "profit_jpy": profit, "profit_per_post": profit / len(rows) if rows else 0.0,
            "best_post": {"post_id": best["post_id"], "seq": best["seq"], "views": best["views"], "revenue": best["revenue"], "pattern": best["pattern_id"]} if best else None,
            "worst_post": {"post_id": worst["post_id"], "seq": worst["seq"], "views": worst["views"], "revenue": worst["revenue"], "pattern": worst["pattern_id"]} if worst else None,
            "by_pattern": by_pat,
            "posts_detail": [{k: r[k] for k in ("post_id", "seq", "pattern_id", "product_id", "genre", "angle", "media_type", "slot_hour", "views", "eng", "clicks", "revenue", "profit")} for r in rows]}


def _rule_adjustments(s: dict, arms: dict) -> dict:
    learned, more, less, tests, adjust = [], [], [], [], []
    if s["posts"] == 0:
        learned.append("昨日は投稿登録がありません（posted --url で登録すると学習が進みます）")
    elif s["views"] < 3000:
        learned.append(f"表示 {s['views']:,} はサンプル不足。差は判断せず配分を維持")
    if s.get("best_post"):
        more.append(f"{s['best_post']['pattern']}（昨日の最良投稿 POST {s['best_post']['seq']}）")
    for pid, d in s.get("by_pattern", {}).items():
        if d["views"] >= 3000 and d["eng"] == 0:
            less.append(f"{pid}: 表示 {d['views']:,} で反応 0")
    hs = arms.get("hour_slot", {})
    untested = [a for a, v in hs.items() if v[2] == 0]
    if untested:
        tests.append(f"未検証の時間帯 {untested[:2]} を 1 枠")
    tests.append("同一商品で訴求軸（B_actress vs E_price）を別日に比較")
    media = arms.get("media", {})
    if media:
        best_media = max(media, key=lambda k: media[k][0] / (media[k][0] + media[k][1]))
        adjust.append(f"{'動画' if best_media == 'video' else '画像'}投稿の比率を維持・微増（バンディット推定で {best_media} が優位）")
    if hs:
        best_slot = max(hs, key=lambda k: hs[k][0] / (hs[k][0] + hs[k][1]))
        adjust.append(f"{best_slot} 時台の投稿を強化")
    adjust += [f"{x} を停止候補" for x in less[:1]]
    return {"learned": learned, "more": more or ["現行の商品選定・パターン配分"], "less": less or ["なし"], "tests": tests, "adjustments": adjust or ["現状維持"]}


def _fmt_post(p: dict | None) -> str:
    if not p:
        return "-"
    return f"POST {p['seq']}（{p['pattern']}, {p['views']:,} views, {p['revenue']:,.0f}円）"


def daily_report(db: Database, settings: Settings, llm: LLMRouter | None = None, day: datetime | None = None) -> str:
    s = summarize_day(db, settings, day)
    prev = summarize_day(db, settings, datetime.fromisoformat(s["day"]).replace(tzinfo=ZoneInfo(settings.timezone)) - timedelta(days=1))
    arms = {dim: {a: [round(v[0], 2), round(v[1], 2), v[2]] for a, v in bandit.get_arms(db, dim).items()} for dim in ("hour_slot", "pattern", "genre", "media")}
    today = today_packages(db, settings)
    insight = None
    if llm is not None and llm.enabled and s["posts"] > 0:
        try:
            res = llm.call("opus",
                           "あなたはアフィリエイト事業のグロースアナリストです。目的関数は Affiliate Profit。人間に分析を求めず、AI が判断して"
                           "『昨日分かったこと』『今日増やすもの』『今日減らすもの』『新しく試すもの』『本日の調整（動画比率・ジャンル・Pattern 停止・時間帯強化など 3〜5 行）』を"
                           "サンプルサイズを踏まえて慎重に出してください。1 日の結果だけで大きな変更はしない。出力は JSON。",
                           "## 昨日\n" + dumps({k: v for k, v in s.items() if k != "posts_detail"}) + "\n## 一昨日\n" +
                           dumps({k: v for k, v in prev.items() if k not in ("posts_detail", "by_pattern")}) + "\n## バンディット\n" + dumps(arms) +
                           "\n## 投稿明細\n" + dumps(s["posts_detail"]),
                           schema={"type": "object", "properties": {k: {"type": "array", "items": {"type": "string"}} for k in ("learned", "more", "less", "tests", "adjustments")},
                                   "required": ["learned", "more", "less", "tests", "adjustments"], "additionalProperties": False},
                           max_tokens=1500, ref="daily_report")
            insight = res.parsed
        except LLMUnavailable as e:
            db.log_event("warn", "daily_llm_skip", str(e))
    if insight is None:
        insight = _rule_adjustments(s, arms)
    sug = loads(db.get_setting("suggested_posts_per_day"), {})
    md = [f"# {datetime.now(ZoneInfo(settings.timezone)).strftime('%Y-%m-%d')} 今日の投稿", ""]
    md += [render_schedule(today) or "（plan 未実行）", ""]
    md += [f"## 昨日（{s['day']}）の実績",
           f"- 売上（成果）: {s['revenue_jpy']:,.0f}円（投稿帰属 {s['attributed_revenue_jpy']:,.0f}円）",
           f"- 報酬 − 費用 = 利益: {s['profit_jpy']:,.0f}円（AI {s['ai_cost_jpy']:,.0f} / API {s['api_cost_jpy']:,.0f}）",
           f"- Views 合計 {s['views']:,} / 平均 {s['avg_views']:,.0f}",
           f"- 最良投稿: {_fmt_post(s['best_post'])}",
           f"- 最低投稿: {_fmt_post(s['worst_post'])}",
           f"- CTR 推定: {s['ctr_est'] * 100:.2f}% / CV {s['conversions']:.1f} / EPC {s['epc']:,.0f}円 / 投稿あたり利益 {s['profit_per_post']:,.0f}円", ""]
    md += ["## 昨日分かったこと"] + [f"- {x}" for x in insight["learned"] or ["- （データ不足）"]] + [""]
    md += ["## 今日増やすもの"] + [f"- {x}" for x in insight["more"]] + [""]
    md += ["## 今日減らすもの"] + [f"- {x}" for x in insight["less"]] + [""]
    md += ["## 新しく試すもの"] + [f"- {x}" for x in insight["tests"]] + [""]
    if sug:
        md += [f"## 投稿数の提案", f"- {sug.get('n')} 件/日（{sug.get('why')}）", ""]
    md += ["## 投稿セット", ""] + [render_text(p) for p in today] + [""]
    md += ["## 本日の調整"] + [f"・{x}" for x in insight["adjustments"]]
    text = "\n".join(md) + "\n"
    db.exec("INSERT OR REPLACE INTO daily_summary(day,revenue_jpy,profit_jpy,views,conversions,ctr,epc,ai_cost_jpy,api_cost_jpy,best_post,worst_post,posts,report_md,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (s["day"], s["revenue_jpy"], s["profit_jpy"], s["views"], s["conversions"], s["ctr_est"], s["epc"], s["ai_cost_jpy"], s["api_cost_jpy"],
             s["best_post"]["post_id"] if s["best_post"] else None, s["worst_post"]["post_id"] if s["worst_post"] else None, s["posts"], text, utcnow()))
    db.set_setting("today_adjustments", dumps(insight["adjustments"]))
    return text


def weekly_review(db: Database, settings: Settings, llm: LLMRouter | None) -> str:
    last = db.get_setting("last_weekly_review_at")
    now = datetime.now(timezone.utc)
    if last and (now - datetime.fromisoformat(last)) < timedelta(days=7):
        return f"前回の週次レビューから 7 日未満（{last}）。Fable は呼び出しません。"

    def window(days: int | None):
        rows = post_profit_rows(db, days=days or 3650)
        views = sum(r["views"] for r in rows); rev = sum(r["revenue"] or 0 for r in rows); conv = sum(r["conv"] for r in rows)
        cost = sum((r["api_cost_jpy"] or 0) + (r["ai_cost_jpy"] or 0) for r in rows)
        def group(key):
            g: dict[str, dict] = {}
            for r in rows:
                k = str(r.get(key) or "-")
                d = g.setdefault(k, {"posts": 0, "views": 0, "revenue": 0.0})
                d["posts"] += 1; d["views"] += r["views"]; d["revenue"] += r["revenue"] or 0
            return g
        return {"posts": len(rows), "views": views, "revenue": rev, "conversions": conv, "cost": cost, "profit": rev - cost,
                "by_pattern": group("pattern_id"), "by_genre": group("genre"), "by_media": group("media_type"), "by_hour": group("slot_hour"),
                "by_angle": group("angle")}
    data = {"7d": window(7), "30d": window(30), "all": window(None)}
    prods = [dict(r) for r in db.q("""SELECT p.product_id, pr.title, pr.price, pr.discount_rate, pr.actresses, pr.genres, COUNT(*) posts,
                                          SUM((SELECT COALESCE(SUM(revenue_jpy*attribution_share),0) FROM conversions cv WHERE cv.post_id=p.post_id)) revenue
                                        FROM posts p JOIN products pr ON pr.content_id=p.product_id WHERE p.status='posted' AND p.posted_at>=?
                                        GROUP BY p.product_id ORDER BY revenue DESC LIMIT 30""", ((now - timedelta(days=30)).isoformat(),))]
    pats = [dict(r) for r in db.q("SELECT pattern_id,pattern_name,uses,avg_views,views_per_follower,engagement_rate,ctr,epc,conversions,profit,confidence,trend_score,status FROM patterns")]
    research = [dict(r) for r in db.q("SELECT category, COUNT(*) n, AVG(views_per_follower) vpf, AVG(engagement_rate) er FROM research_posts WHERE captured_at>=? GROUP BY category ORDER BY vpf DESC",
                                      ((now - timedelta(days=30)).isoformat(),))]
    costs = [dict(r) for r in db.q("SELECT model, SUM(input_tokens) i, SUM(output_tokens) o, SUM(amount_jpy) jpy, COUNT(*) n FROM costs WHERE kind='ai' AND ts>=? GROUP BY model", ((now - timedelta(days=7)).isoformat(),))]
    md = [f"# 週次レビュー {now.strftime('%Y-%m-%d')}", "", "## 期間比較", "```json", dumps(data), "```", "", "## 商品（30日）", "```json", dumps(prods), "```",
          "", "## パターン DB", "```json", dumps(pats), "```", "", "## 競合トレンド（30日）", "```json", dumps(research), "```", "", "## AI コスト（7日）", "```json", dumps(costs), "```", ""]
    if llm is not None and llm.enabled:
        try:
            res = llm.call("fable",
                           "あなたは FANZA アフィリエイト事業の事業責任者兼データアナリストです。目的関数は Affiliate Profit。7日/30日/全期間を比較し、"
                           "売れた商品・売れなかった商品・女優・ジャンル・価格帯・割引率・投稿時間・Pattern・文章量・動画/画像・CTA・競合トレンド・AI コストを見直し、"
                           "『来週増やすもの』『来週減らすもの』『来週試すもの』『削除する Pattern』『追加する Pattern（構造のみ）』を決定してください。"
                           "サンプルサイズの小さい差を過大評価しない。人間への確認事項は本当に必要なものだけ。出力は JSON。",
                           "\n".join(md),
                           schema={"type": "object", "properties": {
                               "summary": {"type": "string"},
                               "increase": {"type": "array", "items": {"type": "string"}}, "decrease": {"type": "array", "items": {"type": "string"}},
                               "try": {"type": "array", "items": {"type": "string"}},
                               "remove_patterns": {"type": "array", "items": {"type": "string"}},
                               "add_patterns": {"type": "array", "items": {"type": "object", "properties": {
                                   "pattern_id": {"type": "string"}, "pattern_name": {"type": "string"}, "category": {"type": "string"}, "hook": {"type": "string"},
                                   "body_structure": {"type": "string"}, "cta_structure": {"type": "string"}, "media_type": {"type": "string"},
                                   "ideal_length": {"type": "integer"}, "ideal_hours": {"type": "array", "items": {"type": "integer"}},
                                   "target_genre": {"type": "string"}, "target_actress_type": {"type": "string"}},
                                   "required": ["pattern_id", "pattern_name", "category", "hook", "body_structure", "cta_structure", "media_type", "ideal_length", "ideal_hours", "target_genre", "target_actress_type"],
                                   "additionalProperties": False}},
                               "posts_per_day": {"type": "integer"}, "needs_human": {"type": "array", "items": {"type": "string"}}},
                               "required": ["summary", "increase", "decrease", "try", "remove_patterns", "add_patterns", "posts_per_day", "needs_human"],
                               "additionalProperties": False},
                           max_tokens=6000, ref="weekly_review")
            r = res.parsed
            from .patterns import add_pattern
            for pid in r["remove_patterns"]:
                db.exec("UPDATE patterns SET status='demoted', updated_at=? WHERE pattern_id=?", (utcnow(), pid))
            added = sum(1 for p in r["add_patterns"] if add_pattern(db, p, source="weekly:fable", confidence=0.3))
            md += ["## Fable 5.1 レビュー", r["summary"], "", "### 来週増やすもの", *[f"- {x}" for x in r["increase"]], "",
                   "### 来週減らすもの", *[f"- {x}" for x in r["decrease"]], "", "### 来週試すもの", *[f"- {x}" for x in r["try"]], "",
                   f"### 削除した Pattern: {', '.join(r['remove_patterns']) or 'なし'} / 追加した Pattern: {added}",
                   f"### 提案投稿数: {r['posts_per_day']} 件/日", "", "### 人間の確認事項", *([f"- {x}" for x in r["needs_human"]] or ["- なし"]), "",
                   f"（コスト {res.cost_jpy:.1f}円 / in {res.input_tokens} / out {res.output_tokens}）"]
            db.set_setting("weekly_decisions", dumps(r))
        except LLMUnavailable as e:
            md += [f"（Fable レビューはスキップ: {e}）"]
    db.set_setting("last_weekly_review_at", now.isoformat(timespec="seconds"))
    return "\n".join(md) + "\n"
