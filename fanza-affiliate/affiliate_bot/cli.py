"""CLI（Phase 3: FANZA 手動投稿アシスト）。X への投稿コマンドは存在しない。"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import attention, bandit, bootstrap, failsafe, launch, media, metrics, packages, patterns, planner, posted, products, reports, research, webui
from .config import Settings, load_settings
from .db import Database, loads
from .dmm_client import DMMClient, DMMError
from .llm import LLMRouter
from .x_client import DryRunXClient, XReadClient


def _x(settings: Settings, db: Database):
    from .pricing import x_pricing
    if not settings.x_read_available():
        return DryRunXClient(pricing=x_pricing(settings, db))
    return XReadClient(settings.x_bearer_token, pricing=x_pricing(settings, db))


def _llm(settings: Settings, db: Database) -> LLMRouter | None:
    r = LLMRouter(settings, db)
    return r if r.enabled else None


def _export_dir(settings: Settings) -> Path:
    return settings.data_dir.parent / "exports"


# ---------------------------------------------------------------- commands
def cmd_status(settings: Settings, db: Database, args) -> None:
    print("== FANZA 手動投稿アシスト ==")
    print(f"DMM 認証: {'あり' if settings.dmm_credentials_present() else 'なし'} (site={settings.dmm_site} floor={settings.dmm_floor}) / 媒体登録: {settings.dmm_media_registered}")
    print(f"X 読取: {'あり' if settings.x_read_available() else 'なし（指標は CSV/手入力）'} / @{settings.x_username or '-'}")
    print(f"Anthropic: {'あり' if settings.anthropic_api_key else 'なし（テンプレート生成）'} ({settings.model_sonnet} / {settings.model_opus} / {settings.model_fable})")
    print("X 自動投稿: 機能なし（成人向けは policy.py で HARD BLOCK。投稿は人間）")
    for t in ("products", "patterns", "candidates", "posts", "post_metrics", "conversions", "research_posts", "media_assets", "costs"):
        print(f"{t}: {db.one(f'SELECT COUNT(*) c FROM {t}')['c']}")
    tz = ZoneInfo(settings.timezone)
    today = datetime.now(tz).strftime("%Y-%m-%d")
    st = db.q("SELECT status, COUNT(*) c FROM posts WHERE day=? GROUP BY status", (today,))
    print(f"本日 {today}: " + (", ".join(f"{r['status']} {r['c']}" for r in st) or "パッケージなし（plan 未実行）"))
    for k in ("last_research_at", "last_conversions_ingest_at", "last_weekly_review_at", "conv_weight"):
        print(f"{k}: {db.get_setting(k) or '-'}")
    items = attention.open_items(db)
    print("要対応: " + (f"{len(items)} 件（attention で表示）" if items else "なし"))
    print_costs(settings, db)


def print_costs(settings: Settings, db: Database) -> None:
    """実使用量ベースのコスト（直近 24h と全期間の 1 日平均）と 30 日換算。README の推定ではなく costs 台帳から。"""
    now = datetime.now(timezone.utc)
    d1 = (now - timedelta(hours=24)).isoformat(timespec="seconds")
    first = db.one("SELECT MIN(ts) t FROM costs")
    days = 1.0
    if first and first["t"]:
        days = max(1.0, (now - datetime.fromisoformat(first["t"])).total_seconds() / 86400)
    print("== 実コスト（costs 台帳）==")
    for kind in ("ai", "x_api", "dmm_api"):
        last24 = db.cost_between(d1, now.isoformat(timespec="seconds"), kind)
        total = db.cost_between("0000", now.isoformat(timespec="seconds"), kind)
        per_day = total / days
        print(f"{kind:8s} 直近24h {last24:7.1f}円 / 1日平均 {per_day:7.1f}円 / 30日換算 {per_day * 30:8.0f}円")
    infra = settings.infra_cost_month_jpy + settings.other_cost_month_jpy
    print(f"infra    月額設定 {infra:.0f}円")
    for r in db.q("SELECT model, SUM(input_tokens) i, SUM(output_tokens) o, SUM(amount_jpy) jpy, COUNT(*) n FROM costs WHERE kind='ai' GROUP BY model"):
        print(f"  {r['model']}: {r['n']} 回, in {r['i']:,} / out {r['o']:,} tok, {r['jpy']:.1f}円")


def cmd_fetch_products(settings: Settings, db: Database, args) -> None:
    if not settings.dmm_credentials_present():
        if args.demo:
            from .demo_data import demo_products
            n = products.upsert_products(db, demo_products(settings.dmm_site), settings.dmm_payout_rate)
            print(f"demo products upserted: {n}")
        else:
            print("DMM_API_ID / DMM_AFFILIATE_ID が未設定です（bootstrap で設定、または --demo）", file=sys.stderr)
            sys.exit(2)
    else:
        c = DMMClient(settings.dmm_api_id, settings.dmm_affiliate_id)
        total = 0
        for sort in args.sorts.split(","):
            for page in range(args.pages):
                try:
                    items = c.item_list(site=settings.dmm_site, service=settings.dmm_service, floor=settings.dmm_floor, sort=sort, hits=args.hits, offset=1 + page * args.hits)
                except DMMError as e:
                    db.log_event("warn", "dmm_error", str(e))
                    if "401" in str(e) or "403" in str(e) or "api_id" in str(e).lower():
                        attention.raise_item(db, "fanza_auth", "FANZA API 認証エラー", detail=str(e)[:200], action="bootstrap で API ID を再設定")
                    print(f"DMM error: {e}", file=sys.stderr)
                    break
                total += products.upsert_products(db, items, settings.dmm_payout_rate, rank_offset=page * args.hits if sort == "rank" else 1000)
        print(f"products upserted: {total}")
    n = products.rescore_all(db)
    for r in db.q("SELECT content_id FROM products"):
        media.register_official_assets(db, dict(db.one("SELECT * FROM products WHERE content_id=?", (r["content_id"],))))
    print(f"rescored: {n}")
    for p in products.top_candidates(db, limit=8):
        c = p["eav_components"]
        print(f"  EAV {p['eav']:.4f}  {p['content_id']}  {p['title'][:36]}  views {c.get('p_views')} ctr {c.get('p_ctr')} cvr {c.get('p_cvr')} payout {c.get('payout_jpy')}")


def cmd_research(settings: Settings, db: Database, args) -> None:
    if args.import_csv:
        print(f"imported: {research.import_csv(db, Path(args.import_csv).read_text(encoding='utf-8-sig'))}")
    if args.demo:
        from .demo_data import DEMO_RESEARCH_CSV
        print(f"demo imported: {research.import_csv(db, DEMO_RESEARCH_CSV)}")
    if args.collect:
        x = _x(settings, db)
        if isinstance(x, DryRunXClient):
            print("X_BEARER_TOKEN がないため収集はスキップ（--import-csv で取込可）")
        else:
            print(f"collected: {research.collect(db, x, settings.usd_jpy, queries=args.query.split('|') if args.query else None, per_query=args.per_query)}")
    if args.analyze or not (args.import_csv or args.collect or args.demo):
        print(json.dumps(research.analyze(db, _llm(settings, db)), ensure_ascii=False, indent=1))
    for r in research.top_outliers(db, 5):
        print(f"  {r['x_post_id']} [{r['category']}] followers {r['author_followers']:,} views {r['views']:,} vpf {r['views_per_follower']:.1f} er {r['engagement_rate']:.3f}")


def cmd_plan(settings: Settings, db: Database, args) -> None:
    day = datetime.fromisoformat(args.date).replace(tzinfo=ZoneInfo(settings.timezone)) if args.date else None
    ids = planner.plan_day(db, settings, _llm(settings, db), day_jst=day, replace=not args.keep)
    print(f"packages: {len(ids)}")
    cmd_today(settings, db, argparse.Namespace(date=args.date, full=False))
    cmd_export(settings, db, argparse.Namespace(date=args.date, out=None))


def cmd_today(settings: Settings, db: Database, args) -> None:
    tz = ZoneInfo(settings.timezone)
    day = args.date or datetime.now(tz).strftime("%Y-%m-%d")
    pk = planner.today_packages(db, settings, day)
    if not pk:
        print(f"{day} の投稿セットはありません。`plan` を実行してください。")
        return
    adj = loads(db.get_setting("today_adjustments"), [])
    print(packages.render_day_text(pk, adj) if getattr(args, "full", True) else packages.render_schedule(pk) + "\n" + "\n".join(
        f"POST {p['seq']} [{p['angle']}] {p['title'][:30]}… / {p['media_type']}\n{p['text']}\n" for p in pk))


def cmd_export(settings: Settings, db: Database, args) -> None:
    tz = ZoneInfo(settings.timezone)
    day = args.date or datetime.now(tz).strftime("%Y-%m-%d")
    pk = planner.today_packages(db, settings, day)
    if not pk:
        print("投稿セットがありません")
        return
    out = Path(args.out) if args.out else _export_dir(settings)
    d = packages.export_day(pk, day, out, loads(db.get_setting("today_adjustments"), []))
    print(f"-> {d}/index.html, posts.txt, post*.txt")


def cmd_launch_posts(settings: Settings, db: Database, args) -> None:
    d = launch.export_launch(db, settings, Path(args.out) if args.out else _export_dir(settings))
    print((d / "launch.md").read_text(encoding="utf-8"))
    print(f"-> {d}")


def cmd_posted(settings: Settings, db: Database, args) -> None:
    if args.skip:
        posted.skip(db, args.date or datetime.now(ZoneInfo(settings.timezone)).strftime("%Y-%m-%d"), int(args.post), args.reason or "")
        print("skipped")
        return
    res = posted.register(db, settings, args.url, seq=int(args.post) if args.post else None, day=args.date, actual_text=args.text,
                          actual_time=args.time, actual_media=args.media, x=_x(settings, db))
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))


def cmd_metrics(settings: Settings, db: Database, args) -> None:
    if args.csv:
        print(f"csv rows: {metrics.ingest_metrics_csv(db, Path(args.csv).read_text(encoding='utf-8-sig'))}")
        return
    if args.manual:
        v = [int(x) for x in args.manual]
        metrics.ingest_manual_metrics(db, v[0], v[1], *(v[2:6] + [0] * (4 - len(v[2:6]))))
        print("manual metrics saved")
        return
    x = _x(settings, db)
    if isinstance(x, DryRunXClient):
        due = metrics.due_milestones(db, settings.metric_milestones_hours)
        print(f"X 読取なし。取得待ち {len(due)} 件 → `metrics --manual POST_ID views likes reposts replies bookmarks` または --csv")
        return
    try:
        print(f"metrics rows: {metrics.ingest_x_metrics(db, settings, x)}")
        attention.resolve_by_category(db, "x_read_auth")
    except Exception as e:  # noqa: BLE001
        from .x_client import XError
        if isinstance(e, XError) and e.is_auth:
            attention.raise_item(db, "x_read_auth", f"X READ API 認証失敗 {e.status}", detail=e.body[:200], action="Bearer Token を再生成し bootstrap")
        raise


def cmd_ingest_conversions(settings: Settings, db: Database, args) -> None:
    try:
        text = Path(args.csv).read_text(encoding="utf-8-sig")
        n = metrics.ingest_conversions_csv(db, settings, text)
        print(f"conversions: {n}")
        attention.resolve_by_category(db, "csv_ingest_failed")
        for r in db.q("SELECT attribution_confidence, COUNT(*) c FROM conversions GROUP BY attribution_confidence"):
            print(f"  confidence {r['attribution_confidence']}: {r['c']}")
    except Exception as e:  # noqa: BLE001
        attention.raise_item(db, "csv_ingest_failed", f"成果 CSV 取込失敗: {e.__class__.__name__}", detail=str(e)[:300],
                             action="CSV の列名（日時/商品ID/報酬/注文ID）を確認して再実行")
        raise


def cmd_learn(settings: Settings, db: Database, args) -> None:
    print(f"learned posts: {metrics.learn(db)}")
    for dim in ("hour_slot", "pattern", "genre", "media"):
        arms = bandit.get_arms(db, dim)
        if arms:
            print(f"  {dim}: " + ", ".join(f"{a}={v[0] / (v[0] + v[1]):.2f}(n={v[2]})" for a, v in sorted(arms.items())))


def cmd_report(settings: Settings, db: Database, args) -> None:
    md = reports.daily_report(db, settings, None if args.no_llm else _llm(settings, db),
                              datetime.fromisoformat(args.date).replace(tzinfo=ZoneInfo(settings.timezone)) if args.date else None)
    out = Path(args.out) if args.out else settings.data_dir.parent / "reports" / f"daily-{datetime.now(ZoneInfo(settings.timezone)).strftime('%Y-%m-%d')}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"-> {out}")


def cmd_weekly(settings: Settings, db: Database, args) -> None:
    md = reports.weekly_review(db, settings, None if args.no_llm else _llm(settings, db))
    out = settings.data_dir.parent / "reports" / f"weekly-{datetime.now().strftime('%Y-%m-%d')}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"-> {out}")


def cmd_checks(settings: Settings, db: Database, args) -> None:
    failsafe.run_checks(db, settings)
    print(f"attention open: {len(attention.open_items(db))}")


def cmd_attention(settings: Settings, db: Database, args) -> None:
    if args.resolve:
        attention.resolve(db, int(args.resolve))
    if args.notify:
        print(f"notified: {attention.notify_pending(db, settings)}")
    items = attention.open_items(db)
    if not items:
        print("要対応: なし（自律運用中）")
    for it in items:
        print(f"#{it['id']} {it['ts']} [{it['severity']}/{it['category']}] {it['title']}\n   → {it['action']}")


def cmd_bootstrap(settings: Settings, db: Database, args) -> None:
    bootstrap.run(settings, db, bootstrap.IO(interactive=not args.check), network=not args.no_network, only=args.only.split(",") if args.only else None)


def cmd_serve(settings: Settings, db: Database, args) -> None:
    if args.port:
        settings.web_port = int(args.port)
    webui.serve(settings, db)


def cmd_pricing(settings: Settings, db: Database, args) -> None:
    from .pricing import apply_candidate, verify_x_pricing, x_pricing
    if args.verify:
        print(verify_x_pricing(settings, db))
    if args.apply:
        p = apply_candidate(db)
        print("applied: " + str(p.as_dict()) if p else "候補はありません")
    print("current:", x_pricing(settings, db).as_dict())


def morning(settings: Settings, db: Database) -> None:
    """毎朝の自動処理: 商品更新 → 学習 → 検知 → レポート → 計画 → 出力 → 通知（要対応時のみ）。"""
    if settings.dmm_credentials_present():
        cmd_fetch_products(settings, db, argparse.Namespace(demo=False, sorts="rank,date", pages=1, hits=100))
    metrics.learn(db)
    failsafe.run_checks(db, settings)
    llm = _llm(settings, db)
    planner.plan_day(db, settings, llm)
    md = reports.daily_report(db, settings, llm)
    out = settings.data_dir.parent / "reports" / f"daily-{datetime.now(ZoneInfo(settings.timezone)).strftime('%Y-%m-%d')}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    cmd_export(settings, db, argparse.Namespace(date=None, out=None))
    attention.notify_pending(db, settings)


def cmd_morning(settings: Settings, db: Database, args) -> None:
    morning(settings, db)
    cmd_today(settings, db, argparse.Namespace(date=None, full=False))


def cmd_loop(settings: Settings, db: Database, args) -> None:
    """常駐: 毎時 metrics（X 読取があれば）+ 通知。06:00 JST に morning。月曜 07:00 に weekly + research。"""
    tz = ZoneInfo(settings.timezone)
    last_hourly = last_daily = last_weekly = None
    errors = 0
    while True:
        now = datetime.now(tz)
        try:
            if last_hourly is None or (now - last_hourly) >= timedelta(minutes=args.every):
                settings = load_settings()
                x = _x(settings, db)
                if not isinstance(x, DryRunXClient):
                    metrics.ingest_x_metrics(db, settings, x)
                attention.notify_pending(db, settings)
                last_hourly = now
            if now.hour == 6 and (last_daily is None or last_daily.date() != now.date()):
                morning(settings, db)
                last_daily = now
            if now.weekday() == 0 and now.hour == 7 and (last_weekly is None or (now - last_weekly) > timedelta(days=6)):
                x = _x(settings, db)
                if not isinstance(x, DryRunXClient):
                    research.collect(db, x, settings.usd_jpy)
                research.analyze(db, _llm(settings, db))
                from . import policy
                for k, v in policy.verify_policy(db).items():
                    if v["status"] in ("changed", "phrase_missing"):
                        attention.raise_item(db, "policy_change", f"規約ページの変更を検知: {k}", detail=str(v), action="一次情報を確認", severity="critical")
                reports.weekly_review(db, settings, _llm(settings, db))
                last_weekly = now
            errors = 0
        except Exception as e:  # noqa: BLE001
            errors += 1
            db.log_event("warn", "loop_error", f"{e.__class__.__name__}: {e}")
            if errors >= 3:
                attention.raise_item(db, "prod_outage", f"loop が連続 {errors} 回失敗: {e.__class__.__name__}", detail=str(e)[:500],
                                     action="events を確認して原因を解決", severity="critical", dedupe_key="loop_error_streak")
                attention.notify_pending(db, settings)
        time.sleep(60)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="affiliate-bot", description="FANZA アフィリエイト 手動投稿アシスト（AI 編集部・リサーチ部・分析部）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="全体ステータス").set_defaults(fn=cmd_status)
    p = sub.add_parser("bootstrap", help="対話型の初期設定"); p.add_argument("--check", action="store_true"); p.add_argument("--no-network", action="store_true"); p.add_argument("--only"); p.set_defaults(fn=cmd_bootstrap)
    p = sub.add_parser("research", help="公開投稿を調査し勝ちパターン更新"); p.add_argument("--collect", action="store_true"); p.add_argument("--analyze", action="store_true")
    p.add_argument("--import-csv"); p.add_argument("--demo", action="store_true"); p.add_argument("--query"); p.add_argument("--per-query", type=int, default=100); p.set_defaults(fn=cmd_research)
    p = sub.add_parser("fetch-products", help="FANZA 商品取得と EAV 推定"); p.add_argument("--sorts", default="rank,date"); p.add_argument("--pages", type=int, default=1)
    p.add_argument("--hits", type=int, default=100); p.add_argument("--demo", action="store_true"); p.set_defaults(fn=cmd_fetch_products)
    p = sub.add_parser("plan", help="本日の投稿パッケージ作成"); p.add_argument("--date"); p.add_argument("--keep", action="store_true", help="既存の planned を消さない"); p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("today", help="今日人間が投稿すべき内容を表示"); p.add_argument("--date"); p.add_argument("--full", action="store_true", default=True); p.set_defaults(fn=cmd_today)
    p = sub.add_parser("export", help="投稿素材と文章をフォルダ/HTML へ出力"); p.add_argument("--date"); p.add_argument("--out"); p.set_defaults(fn=cmd_export)
    p = sub.add_parser("launch-posts", help="新規アカウントの設計と初期 10 投稿を出力"); p.add_argument("--out"); p.set_defaults(fn=cmd_launch_posts)
    p = sub.add_parser("posted", help="実際に投稿した Post を登録"); p.add_argument("--url", help="X の投稿 URL または Post ID"); p.add_argument("--post", help="POST 番号（省略時は予定時刻が最も近い未登録）")
    p.add_argument("--date"); p.add_argument("--text", help="実際の本文（予定と違う場合）"); p.add_argument("--time", help="実際の投稿時刻"); p.add_argument("--media", help="実際の素材")
    p.add_argument("--skip", action="store_true", help="投稿しなかった POST を skipped にする"); p.add_argument("--reason"); p.set_defaults(fn=cmd_posted)
    p = sub.add_parser("metrics", help="投稿結果取得（X 読取 / CSV / 手入力）"); p.add_argument("--csv"); p.add_argument("--manual", nargs="+", metavar="N", help="POST_ID views likes reposts replies bookmarks"); p.set_defaults(fn=cmd_metrics)
    p = sub.add_parser("ingest-conversions", help="FANZA 成果 CSV 取込"); p.add_argument("--csv", required=True); p.set_defaults(fn=cmd_ingest_conversions)
    sub.add_parser("learn", help="学習").set_defaults(fn=cmd_learn)
    p = sub.add_parser("report", help="日次レポート"); p.add_argument("--date"); p.add_argument("--out"); p.add_argument("--no-llm", action="store_true"); p.set_defaults(fn=cmd_report)
    p = sub.add_parser("weekly", help="Fable による週次レビュー"); p.add_argument("--no-llm", action="store_true"); p.set_defaults(fn=cmd_weekly)
    sub.add_parser("checks", help="異常検知").set_defaults(fn=cmd_checks)
    p = sub.add_parser("attention", help="Human Attention Queue"); p.add_argument("--resolve"); p.add_argument("--notify", action="store_true"); p.set_defaults(fn=cmd_attention)
    p = sub.add_parser("serve", help="スマホ向け Web UI"); p.add_argument("--port"); p.set_defaults(fn=cmd_serve)
    p = sub.add_parser("pricing", help="X API 価格の確認/候補適用"); p.add_argument("--verify", action="store_true"); p.add_argument("--apply", action="store_true"); p.set_defaults(fn=cmd_pricing)
    sub.add_parser("morning", help="毎朝の一括処理（fetch → learn → report → plan → export）").set_defaults(fn=cmd_morning)
    p = sub.add_parser("loop", help="常駐"); p.add_argument("--every", type=int, default=60); p.set_defaults(fn=cmd_loop)
    args = ap.parse_args(argv)
    settings = load_settings()
    db = Database(settings.db_path)
    try:
        args.fn(settings, db, args)
    finally:
        db.close()


if __name__ == "__main__":
    main()
