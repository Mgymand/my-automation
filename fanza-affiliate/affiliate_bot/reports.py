"""日次レポートと週次レビュー。

日次: 決定論的な集計 + （任意）Opus 5.5 による「昨日わかったこと／継続／停止／新規テスト」の要約
週次: Fable 5.1 による 7 日 / 30 日 / 全期間の比較レビュー（7 日に 1 回だけ）
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import bandit
from .config import Settings
from .db import Database, dumps, loads, utcnow
from .llm import LLMRouter, LLMUnavailable
from .metrics import post_profit_rows


def _jst_day_bounds(settings: Settings, day: datetime | None = None) -> tuple[str, str, str]:
    tz = ZoneInfo(settings.timezone)
    d = (day or (datetime.now(tz) - timedelta(days=1))).astimezone(tz)
    start = d.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.strftime("%Y-%m-%d"), start.astimezone(timezone.utc).isoformat(timespec="seconds"), end.astimezone(timezone.utc).isoformat(timespec="seconds")


def summarize_day(db: Database, settings: Settings, day: datetime | None = None) -> dict:
    label, a, b = _jst_day_bounds(settings, day)
    rows = [r for r in post_profit_rows(db, days=40) if a <= (r["posted_at"] or "") < b]
    views = sum(r["views"] for r in rows)
    clicks = sum(r["clicks"] for r in rows)
    conv_row = db.one("SELECT COUNT(*) c, COALESCE(SUM(revenue_jpy),0) r FROM conversions WHERE ts>=? AND ts<?", (a, b))
    conv, revenue = int(conv_row["c"]), float(conv_row["r"])
    ai_cost = db.cost_between(a, b, "ai")
    api_cost = db.cost_between(a, b, "x_api") + db.cost_between(a, b, "dmm_api")
    infra = (settings.infra_cost_month_jpy + settings.other_cost_month_jpy) / 30
    profit = revenue - ai_cost - api_cost - infra
    best_pat = max(rows, key=lambda r: r["profit"], default=None)
    best_prod = max(rows, key=lambda r: r["revenue"], default=None)
    # パターン別・時間帯別の集計
    by_pat: dict[str, dict] = {}
    for r in rows:
        d = by_pat.setdefault(r["pattern_id"], {"posts": 0, "views": 0, "clicks": 0, "revenue": 0.0, "profit": 0.0})
        d["posts"] += 1; d["views"] += r["views"]; d["clicks"] += r["clicks"]; d["revenue"] += r["revenue"] or 0; d["profit"] += r["profit"]
    return {
        "day": label, "posts": len(rows), "views": views, "clicks": clicks, "conversions": conv,
        "ctr": clicks / views if views else 0.0, "cvr": conv / clicks if clicks else 0.0,
        "revenue_jpy": revenue, "ai_cost_jpy": ai_cost, "api_cost_jpy": api_cost, "infra_cost_jpy": infra,
        "profit_jpy": profit,
        "best_pattern": best_pat["pattern_id"] if best_pat else None,
        "best_product": best_prod["product_id"] if best_prod else None,
        "by_pattern": by_pat,
        "posts_detail": [{k: r[k] for k in ("post_id", "pattern_id", "product_id", "genre", "slot_hour", "views", "clicks", "revenue", "profit")} for r in rows],
    }


def _compare(today: dict, yesterday: dict) -> list[str]:
    lines = []
    for k, label in (("views", "表示"), ("clicks", "クリック"), ("conversions", "CV"), ("revenue_jpy", "売上"), ("profit_jpy", "利益")):
        t, y = today.get(k, 0), yesterday.get(k, 0)
        if y:
            lines.append(f"- {label}: {t:,.0f}（前日 {y:,.0f}, {((t - y) / y * 100):+.0f}%）")
        else:
            lines.append(f"- {label}: {t:,.0f}（前日 {y:,.0f}）")
    return lines


def daily_report(db: Database, settings: Settings, llm: LLMRouter | None = None, day: datetime | None = None) -> str:
    s = summarize_day(db, settings, day)
    prev = summarize_day(db, settings, datetime.fromisoformat(s["day"]).replace(tzinfo=ZoneInfo(settings.timezone)) - timedelta(days=1))
    arms = {dim: {a: round(v[0] / (v[0] + v[1]), 3) for a, v in bandit.get_arms(db, dim).items()} for dim in ("hour_slot", "pattern")}
    paused = db.get_setting("paused", "0") == "1"
    header = [
        f"# 日次レポート {s['day']}（JST）",
        "",
        f"- 昨日売上: {s['revenue_jpy']:,.0f}円",
        f"- 昨日利益: {s['profit_jpy']:,.0f}円（AI {s['ai_cost_jpy']:,.0f} / API {s['api_cost_jpy']:,.0f} / インフラ日割 {s['infra_cost_jpy']:,.0f}）",
        f"- クリック数: {s['clicks']:,}",
        f"- CV数: {s['conversions']:,}",
        f"- CTR: {s['ctr'] * 100:.2f}%",
        f"- CVR: {s['cvr'] * 100:.2f}%",
        f"- 最優秀Pattern: {s['best_pattern'] or '-'}",
        f"- 最優秀商品: {s['best_product'] or '-'}",
        f"- AI/APIコスト: {s['ai_cost_jpy'] + s['api_cost_jpy']:,.0f}円",
        f"- 投稿数: {s['posts']}",
        f"- 自動投稿: {'停止中（人間レビュー待ち）' if paused else '継続'}",
        "",
        "## 前日比",
        *_compare(s, prev),
        "",
    ]
    insight = None
    if llm is not None and llm.enabled and s["posts"] > 0:
        try:
            res = llm.call(
                "opus",
                "あなたはアフィリエイト事業のグロースアナリストです。与えられた集計から、サンプルサイズを踏まえて"
                "慎重に示唆を出してください。1日の結果だけで大きな戦略変更を提案しないこと。出力は JSON。",
                "## 昨日\n" + dumps({k: v for k, v in s.items() if k != "posts_detail"}) +
                "\n## 一昨日\n" + dumps({k: v for k, v in prev.items() if k not in ("posts_detail", "by_pattern")}) +
                "\n## バンディット（アーム別の推定成功率）\n" + dumps(arms) +
                "\n## 投稿明細\n" + dumps(s["posts_detail"]),
                schema={
                    "type": "object",
                    "properties": {
                        "learned": {"type": "array", "items": {"type": "string"}},
                        "continue": {"type": "array", "items": {"type": "string"}},
                        "stop": {"type": "array", "items": {"type": "string"}},
                        "new_tests": {"type": "array", "items": {"type": "string"}},
                        "needs_human": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["learned", "continue", "stop", "new_tests", "needs_human"],
                    "additionalProperties": False,
                },
                max_tokens=1500, ref="daily_report",
            )
            insight = res.parsed
        except LLMUnavailable as e:
            db.log_event("warn", "daily_llm_skip", str(e))
    if insight is None:
        insight = _rule_based_insight(s, prev, arms)
    body = [
        "## 昨日わかったこと", *([f"- {x}" for x in insight["learned"]] or ["- （データ不足）"]), "",
        "## 本日継続する施策", *([f"- {x}" for x in insight["continue"]] or ["- 現行方針を継続"]), "",
        "## 本日停止する施策", *([f"- {x}" for x in insight["stop"]] or ["- なし"]), "",
        "## 本日の新規テスト", *([f"- {x}" for x in insight["new_tests"]] or ["- なし"]), "",
    ]
    if insight.get("needs_human"):
        body += ["## 人間の確認が必要な事項", *[f"- {x}" for x in insight["needs_human"]], ""]
    else:
        body += ["## 人間の確認が必要な事項", "- なし（自動運用を継続）", ""]
    # 本日の投稿予定
    tz = ZoneInfo(settings.timezone)
    plan = db.q("SELECT post_id, scheduled_at, pattern_id, product_id, angle, text FROM posts WHERE status='scheduled' ORDER BY scheduled_at")
    body += ["## 本日の投稿予定"]
    if plan:
        for p in plan:
            t = datetime.fromisoformat(p["scheduled_at"]).astimezone(tz).strftime("%H:%M")
            body.append(f"- {t} [{p['pattern_id']}/{p['angle']}] {p['product_id']}: {p['text'][:40].replace(chr(10), ' ')}…")
    else:
        body.append("- なし（plan を実行してください）")
    md = "\n".join(header + body) + "\n"
    db.exec(
        "INSERT OR REPLACE INTO daily_summary(day,revenue_jpy,profit_jpy,clicks,conversions,views,ctr,cvr,ai_cost_jpy,api_cost_jpy,"
        "best_pattern,best_product,posts,report_md,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (s["day"], s["revenue_jpy"], s["profit_jpy"], s["clicks"], s["conversions"], s["views"], s["ctr"], s["cvr"],
         s["ai_cost_jpy"], s["api_cost_jpy"], s["best_pattern"], s["best_product"], s["posts"], md, utcnow()),
    )
    return md


def _rule_based_insight(s: dict, prev: dict, arms: dict) -> dict:
    learned, cont, stop, tests = [], [], [], []
    if s["posts"] == 0:
        learned.append("昨日は投稿がありませんでした")
    if s["views"] < 5000:
        learned.append(f"表示 {s['views']:,} はサンプル不足。CTR/CVR の差は判断しない")
    if s["best_pattern"]:
        cont.append(f"{s['best_pattern']} を継続（昨日の最高利益）")
    for pid, d in s.get("by_pattern", {}).items():
        if d["views"] >= 3000 and d["clicks"] == 0:
            stop.append(f"{pid}: 表示 {d['views']:,} でクリック 0（本日は割当を下げる）")
    hs = arms.get("hour_slot", {})
    if hs:
        untested = [a for a, v in hs.items() if v == 0.5]
        if untested:
            tests.append(f"未検証の時間帯 {untested[:2]} を 1 枠ずつ試す")
    tests.append("同一商品で訴求軸（price vs review）の 2 候補を別日に比較")
    return {"learned": learned, "continue": cont or ["現行の商品選定・パターン配分を継続"], "stop": stop, "new_tests": tests, "needs_human": []}


def weekly_review(db: Database, settings: Settings, llm: LLMRouter | None) -> str:
    """Fable 5.1 を 7 日に 1 回だけ呼ぶ。前回から 7 日未満なら決定論的サマリのみ返す。"""
    last = db.get_setting("last_weekly_review_at")
    now = datetime.now(timezone.utc)
    if last and (now - datetime.fromisoformat(last)) < timedelta(days=7):
        return f"前回の週次レビューから 7 日未満（{last}）。Fable は呼び出しません。"
    def window(days: int | None):
        rows = post_profit_rows(db, days=days or 3650)
        views = sum(r["views"] for r in rows); clicks = sum(r["clicks"] for r in rows)
        rev = sum(r["revenue"] or 0 for r in rows); cost = sum((r["api_cost_jpy"] or 0) + (r["ai_cost_jpy"] or 0) for r in rows)
        return {"posts": len(rows), "views": views, "clicks": clicks, "ctr": clicks / views if views else 0,
                "revenue": rev, "cost": cost, "profit": rev - cost}
    data = {"7d": window(7), "30d": window(30), "all": window(None)}
    pats = [dict(r) for r in db.q("SELECT pattern_id,category,uses,avg_views,avg_ctr,avg_cvr,avg_epc,recent30_profit,confidence,status FROM patterns")]
    arms = {dim: {a: [round(v[0], 1), round(v[1], 1), v[2]] for a, v in bandit.get_arms(db, dim).items()} for dim in ("hour_slot", "pattern", "genre", "media")}
    costs = [dict(r) for r in db.q("SELECT model, SUM(input_tokens) i, SUM(output_tokens) o, SUM(amount_jpy) jpy, COUNT(*) n FROM costs WHERE kind='ai' AND ts>=? GROUP BY model", ((now - timedelta(days=7)).isoformat(),))]
    md = [f"# 週次レビュー {now.strftime('%Y-%m-%d')}", "", "## 期間比較", "```json", dumps(data), "```", "",
          "## パターン DB", "```json", dumps(pats), "```", "", "## バンディット", "```json", dumps(arms), "```", "",
          "## AI コスト（7日）", "```json", dumps(costs), "```", ""]
    if llm is not None and llm.enabled:
        try:
            res = llm.call(
                "fable",
                "あなたはアフィリエイト事業の事業責任者兼データアナリストです。目的関数は営業利益（売上 − AI費 − API費 − インフラ費）。"
                "7日/30日/全期間を比較し、商品選定アルゴリズム・投稿生成・Pattern DB・投稿時間・モデル選択・トークン使用量・API費用を再評価し、"
                "具体的で検証可能な変更案を出してください。サンプルサイズの小さい差を過大評価しないこと。"
                "パラメータ変更案は param_changes に key/value で出す（対象: posts_per_day, daily_ai_budget_jpy, pattern_demote, pattern_promote）。出力は JSON。",
                "## 期間比較\n" + dumps(data) + "\n## パターン\n" + dumps(pats) + "\n## バンディット\n" + dumps(arms) + "\n## AIコスト\n" + dumps(costs),
                schema={
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "findings": {"type": "array", "items": {"type": "string"}},
                        "changes": {"type": "array", "items": {"type": "string"}},
                        "param_changes": {"type": "array", "items": {"type": "object", "properties": {"key": {"type": "string"}, "value": {"type": "string"}, "reason": {"type": "string"}}, "required": ["key", "value", "reason"], "additionalProperties": False}},
                        "new_pattern_hypotheses": {"type": "array", "items": {"type": "string"}},
                        "needs_human": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["summary", "findings", "changes", "param_changes", "new_pattern_hypotheses", "needs_human"],
                    "additionalProperties": False,
                },
                max_tokens=6000, ref="weekly_review",
            )
            r = res.parsed
            md += ["## Fable 5.1 レビュー", r["summary"], "", "### 発見", *[f"- {x}" for x in r["findings"]], "",
                   "### 変更", *[f"- {x}" for x in r["changes"]], "", "### パラメータ変更案（人間承認後に適用）",
                   *[f"- {p['key']} = {p['value']}（{p['reason']}）" for p in r["param_changes"]], "",
                   "### 新パターン仮説", *[f"- {x}" for x in r["new_pattern_hypotheses"]], "",
                   "### 人間の確認事項", *([f"- {x}" for x in r["needs_human"]] or ["- なし"]), "",
                   f"（コスト {res.cost_jpy:.1f}円 / in {res.input_tokens} / out {res.output_tokens}）"]
            db.set_setting("weekly_param_changes", dumps(r["param_changes"]))
        except LLMUnavailable as e:
            md += [f"（Fable レビューはスキップ: {e}）"]
    db.set_setting("last_weekly_review_at", now.isoformat(timespec="seconds"))
    return "\n".join(md) + "\n"
