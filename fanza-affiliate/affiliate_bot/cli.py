"""CLI。すべてのジョブはここから deterministic に呼ばれる（cron / loop）。"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import attention, bandit, bootstrap, failsafe, metrics, patterns, products, reports, research, scheduler, tracking
from .config import Settings, load_settings
from .db import Database
from .dmm_client import DMMClient, DMMError
from .llm import LLMRouter
from .publisher import publish_due
from .x_client import DryRunXClient, XClient


def _x(settings: Settings, db: Database):
    from .pricing import x_pricing
    pr = x_pricing(settings, db)
    if settings.dry_run or not settings.x_credentials_present():
        return DryRunXClient(pricing=pr)
    return XClient(settings.x_consumer_key, settings.x_consumer_secret, settings.x_access_token,
                   settings.x_access_token_secret, pricing=pr)


def _llm(settings: Settings, db: Database) -> LLMRouter | None:
    r = LLMRouter(settings, db)
    return r if r.enabled else None


def cmd_init(settings: Settings, db: Database, args) -> None:
    n = patterns.ensure_seed(db)
    if not db.one("SELECT 1 FROM accounts WHERE name=?", (settings.x_account_name,)):
        db.exec("INSERT INTO accounts(name,theme,target_audience,content_strategy,created_at) VALUES(?,?,?,?,?)",
                (settings.x_account_name, "未設定（1アカウント1テーマ）", "未設定", "未設定", datetime.now(timezone.utc).isoformat()))
    print(f"DB: {settings.db_path}  seed patterns added: {n}")
    cmd_status(settings, db, args)


def cmd_status(settings: Settings, db: Database, args) -> None:
    paused, reason = failsafe.is_paused(db)
    print("== 状態 ==")
    print(f"DRY_RUN: {settings.dry_run} / 停止中: {paused} {reason}")
    print(f"DMM 認証: {'あり' if settings.dmm_credentials_present() else 'なし'} (site={settings.dmm_site} floor={settings.dmm_floor})")
    print(f"X 認証: {'あり' if settings.x_credentials_present() else 'なし'}")
    print(f"Anthropic: {'あり' if settings.anthropic_api_key else 'なし'} (sonnet={settings.model_sonnet}, opus={settings.model_opus}, fable={settings.model_fable})")
    print("== 人間確認ゲート ==")
    print(f"SENSITIVE_MEDIA_SETTING_CONFIRMED={settings.sensitive_media_setting_confirmed}  DMM_MEDIA_REGISTERED={settings.dmm_media_registered}")
    print("成人向け（FANZA）商品の X 投稿: HARD BLOCK（policy.py / X 有料パートナーシップ方針の禁止カテゴリ。設定で解除不可）")
    print("== 集計 ==")
    for t in ("products", "patterns", "candidates", "posts", "post_metrics", "clicks", "conversions", "costs", "events"):
        print(f"{t}: {db.one(f'SELECT COUNT(*) c FROM {t}')['c']}")
    ev = db.q("SELECT ts, level, code, message FROM events ORDER BY id DESC LIMIT 5")
    if ev:
        print("== 直近イベント ==")
        for e in ev:
            print(f"{e['ts']} [{e['level']}] {e['code']}: {e['message'][:80]}")


def cmd_fetch_products(settings: Settings, db: Database, args) -> None:
    if not settings.dmm_credentials_present():
        if args.demo:
            from .demo_data import demo_products
            n = products.upsert_products(db, demo_products(settings.dmm_site), settings.dmm_payout_rate)
            print(f"demo products upserted: {n}")
        else:
            print("DMM_API_ID / DMM_AFFILIATE_ID が未設定です（--demo で合成データ）", file=sys.stderr)
            sys.exit(2)
    else:
        c = DMMClient(settings.dmm_api_id, settings.dmm_affiliate_id)
        total = 0
        for sort in args.sorts.split(","):
            for page in range(args.pages):
                try:
                    items = c.item_list(site=settings.dmm_site, service=settings.dmm_service, floor=settings.dmm_floor,
                                        sort=sort, hits=args.hits, offset=1 + page * args.hits)
                except DMMError as e:
                    db.log_event("warn", "dmm_error", str(e))
                    print(f"DMM error: {e}", file=sys.stderr)
                    break
                total += products.upsert_products(db, items, settings.dmm_payout_rate, rank_offset=page * args.hits if sort == "rank" else 1000)
        print(f"products upserted: {total}")
    n = products.rescore_all(db)
    print(f"rescored: {n}")
    for p in products.top_candidates(db, limit=10)[:10]:
        print(f"  {p['erpi']:.4f}  {p['content_id']}  {p['title'][:40]}  {p['erpi_components']}")


def cmd_plan(settings: Settings, db: Database, args) -> None:
    llm = _llm(settings, db)
    day = None
    if args.date:
        day = datetime.fromisoformat(args.date).replace(tzinfo=ZoneInfo(settings.timezone))
    ids = scheduler.plan_day(db, settings, llm, day_jst=day)
    print(f"scheduled: {len(ids)}")
    tz = ZoneInfo(settings.timezone)
    for r in db.q("SELECT post_id, scheduled_at, pattern_id, angle, product_id, text FROM posts WHERE status='scheduled' ORDER BY scheduled_at"):
        t = datetime.fromisoformat(r["scheduled_at"]).astimezone(tz).strftime("%m-%d %H:%M")
        print(f"  #{r['post_id']} {t} [{r['pattern_id']}/{r['angle']}] {r['product_id']}: {r['text'][:50].replace(chr(10), ' ')}")
    hr = db.q("SELECT id, product_id, status, scores FROM candidates WHERE status='human_review' ORDER BY id DESC LIMIT 5")
    if hr:
        print("== 人間レビュー待ち（理由は scores.reasons）==")
        for c in hr:
            print(f"  cand#{c['id']} {c['product_id']}: {c['scores'][:160]}")


def cmd_publish(settings: Settings, db: Database, args) -> None:
    x = _x(settings, db)
    now = datetime.now(timezone.utc) + (timedelta(days=2) if args.force_now else timedelta())
    done = publish_due(db, settings, x, now=now)
    print(f"published: {done} (dry_run={settings.dry_run})")
    if isinstance(x, DryRunXClient):
        for c in x.calls:
            print("  DRY:", {k: (v[:60] + "…" if isinstance(v, str) and len(v) > 60 else v) for k, v in c.items()})


def cmd_ingest_metrics(settings: Settings, db: Database, args) -> None:
    x = _x(settings, db)
    print(f"metrics rows: {metrics.ingest_x_metrics(db, settings, x)}")


def cmd_ingest_conversions(settings: Settings, db: Database, args) -> None:
    text = Path(args.csv).read_text(encoding="utf-8-sig")
    print(f"conversions: {metrics.ingest_conversions_csv(db, settings, text)}")


def cmd_learn(settings: Settings, db: Database, args) -> None:
    print(f"learned posts: {metrics.learn(db)}")
    for dim in ("hour_slot", "pattern", "genre", "media"):
        arms = bandit.get_arms(db, dim)
        if arms:
            print(f"  {dim}: " + ", ".join(f"{a}={v[0] / (v[0] + v[1]):.2f}(n={v[2]})" for a, v in sorted(arms.items())))


def cmd_checks(settings: Settings, db: Database, args) -> None:
    reasons = failsafe.run_checks(db, settings, check_network=args.network)
    print("halted: " + "; ".join(reasons) if reasons else "ok")


def cmd_report(settings: Settings, db: Database, args) -> None:
    llm = _llm(settings, db) if not args.no_llm else None
    day = datetime.fromisoformat(args.date).replace(tzinfo=ZoneInfo(settings.timezone)) if args.date else None
    md = reports.daily_report(db, settings, llm, day)
    out = Path(args.out) if args.out else (settings.data_dir.parent / "reports" / f"daily-{md.splitlines()[0].split()[-1].split('（')[0]}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"-> {out}")


def cmd_weekly(settings: Settings, db: Database, args) -> None:
    llm = _llm(settings, db) if not args.no_llm else None
    md = reports.weekly_review(db, settings, llm)
    out = settings.data_dir.parent / "reports" / f"weekly-{datetime.now().strftime('%Y-%m-%d')}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"-> {out}")


def cmd_research(settings: Settings, db: Database, args) -> None:
    if args.import_csv:
        print(f"imported: {research.import_csv(db, Path(args.import_csv).read_text(encoding='utf-8-sig'))}")
    if args.collect:
        x = _x(settings, db)
        if isinstance(x, DryRunXClient):
            print("X 認証がない／DRY_RUN のため収集はスキップ")
        else:
            print(f"collected: {research.collect(db, x, settings.usd_jpy, per_query=args.per_query)}")
    if args.analyze:
        import json
        print(json.dumps(research.analyze(db, _llm(settings, db)), ensure_ascii=False, indent=1))


def cmd_serve_tracking(settings: Settings, db: Database, args) -> None:
    tracking.serve(settings, db)


def cmd_bootstrap(settings: Settings, db: Database, args) -> None:
    io = bootstrap.IO(interactive=not args.check)
    bootstrap.run(settings, db, io, network=not args.no_network, only=args.only.split(",") if args.only else None)


def cmd_attention(settings: Settings, db: Database, args) -> None:
    if args.resolve:
        attention.resolve(db, int(args.resolve))
        print(f"resolved #{args.resolve}")
    if args.notify:
        print(f"notified: {attention.notify_pending(db, settings)}")
    items = attention.open_items(db)
    if not items:
        print("要対応: なし（自律運用中）")
    for it in items:
        print(f"#{it['id']} {it['ts']} [{it['severity']}/{it['category']}] {it['title']}\n   → {it['action']}")


def cmd_pause(settings: Settings, db: Database, args) -> None:
    failsafe.halt(db, "manual", args.reason or "人間による停止")
    print("paused")


def cmd_resume(settings: Settings, db: Database, args) -> None:
    failsafe.resume(db)
    print("resumed")


def cmd_loop(settings: Settings, db: Database, args) -> None:
    """常駐スケジューラ（cron の代替）。毎時: publish/metrics/checks。06:00 JST: learn/report/plan。月曜 07:00: weekly。"""
    tz = ZoneInfo(settings.timezone)
    last_hourly = last_daily = last_weekly = None
    errors = 0
    while True:
        now = datetime.now(tz)
        try:
            if last_hourly is None or (now - last_hourly) >= timedelta(minutes=args.every):
                settings = load_settings()   # bootstrap/resume による .env 変更を拾う
                failsafe.run_checks(db, settings, check_network=(now.hour % 6 == 0))
                publish_due(db, settings, _x(settings, db))
                metrics.ingest_x_metrics(db, settings, _x(settings, db))
                attention.notify_pending(db, settings)   # 要対応があるときだけ人間へ
                last_hourly = now
            if now.hour == 6 and (last_daily is None or last_daily.date() != now.date()):
                metrics.learn(db)
                if settings.dmm_credentials_present():
                    cmd_fetch_products(settings, db, argparse.Namespace(demo=False, sorts="rank,date", pages=1, hits=100))
                md = reports.daily_report(db, settings, _llm(settings, db))
                out = settings.data_dir.parent / "reports" / f"daily-{now.strftime('%Y-%m-%d')}.md"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(md, encoding="utf-8")
                scheduler.plan_day(db, settings, _llm(settings, db))
                last_daily = now
            if now.weekday() == 0 and now.hour == 7 and (last_weekly is None or (now - last_weekly) > timedelta(days=6)):
                weekly_maintenance(db, settings)
                reports.weekly_review(db, settings, _llm(settings, db))
                last_weekly = now
            errors = 0
        except Exception as e:  # noqa: BLE001 - 常駐は落とさずログに残す
            errors += 1
            db.log_event("warn", "loop_error", f"{e.__class__.__name__}: {e}")
            if errors >= 3:
                attention.raise_item(db, "prod_outage", f"loop が連続 {errors} 回失敗: {e.__class__.__name__}",
                                     detail=str(e)[:500], action="ログ（events）を確認して原因を解決", severity="critical",
                                     dedupe_key="loop_error_streak")
                attention.notify_pending(db, settings)
        time.sleep(60)


def weekly_maintenance(db: Database, settings: Settings) -> None:
    """週次の規約・価格の再確認。変化があれば Attention Queue へ。"""
    from . import policy
    from .pricing import verify_x_pricing
    try:
        res = policy.verify_policy(db)
        for k, v in res.items():
            if v["status"] in ("changed", "phrase_missing"):
                attention.raise_item(db, "policy_change", f"規約ページの変更を検知: {k}", detail=str(v),
                                     action="一次情報を確認し policy.py / 運用を見直す", severity="critical")
        pv = verify_x_pricing(settings, db)
        if pv["status"] == "changed":
            attention.raise_item(db, "policy_change", "X API 価格の変更を検知", detail=str(pv["changed"]),
                                 action="コスト見積を確認（計算は新価格で継続）")
    except Exception as e:  # noqa: BLE001
        db.log_event("warn", "weekly_maintenance_error", str(e))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="affiliate-bot", description="DMM/FANZA アフィリエイト × X 自動運用")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    p = sub.add_parser("fetch-products"); p.add_argument("--sorts", default="rank,date"); p.add_argument("--pages", type=int, default=1)
    p.add_argument("--hits", type=int, default=100); p.add_argument("--demo", action="store_true"); p.set_defaults(fn=cmd_fetch_products)
    p = sub.add_parser("plan"); p.add_argument("--date"); p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("publish"); p.add_argument("--force-now", action="store_true", help="予定時刻を無視して今すぐ（検証用）"); p.set_defaults(fn=cmd_publish)
    sub.add_parser("ingest-metrics").set_defaults(fn=cmd_ingest_metrics)
    p = sub.add_parser("ingest-conversions"); p.add_argument("--csv", required=True); p.set_defaults(fn=cmd_ingest_conversions)
    sub.add_parser("learn").set_defaults(fn=cmd_learn)
    p = sub.add_parser("checks"); p.add_argument("--network", action="store_true"); p.set_defaults(fn=cmd_checks)
    p = sub.add_parser("report"); p.add_argument("--date"); p.add_argument("--out"); p.add_argument("--no-llm", action="store_true"); p.set_defaults(fn=cmd_report)
    p = sub.add_parser("weekly"); p.add_argument("--no-llm", action="store_true"); p.set_defaults(fn=cmd_weekly)
    p = sub.add_parser("research"); p.add_argument("--collect", action="store_true"); p.add_argument("--analyze", action="store_true")
    p.add_argument("--import-csv"); p.add_argument("--per-query", type=int, default=100); p.set_defaults(fn=cmd_research)
    sub.add_parser("serve-tracking").set_defaults(fn=cmd_serve_tracking)
    p = sub.add_parser("bootstrap", help="対話型の初期設定エージェント（再実行で続きから再開）")
    p.add_argument("--check", action="store_true", help="質問せずに現状判定だけ表示")
    p.add_argument("--no-network", action="store_true", help="疎通確認・デプロイを行わない")
    p.add_argument("--only", help="実行するステップをカンマ区切りで限定（例: x,tracking）")
    p.set_defaults(fn=cmd_bootstrap)
    p = sub.add_parser("attention", help="Human Attention Queue の表示/解決")
    p.add_argument("--resolve"); p.add_argument("--notify", action="store_true"); p.set_defaults(fn=cmd_attention)
    p = sub.add_parser("pause"); p.add_argument("--reason"); p.set_defaults(fn=cmd_pause)
    sub.add_parser("resume").set_defaults(fn=cmd_resume)
    p = sub.add_parser("loop"); p.add_argument("--every", type=int, default=60); p.set_defaults(fn=cmd_loop)
    args = ap.parse_args(argv)
    settings = load_settings()
    db = Database(settings.db_path)
    try:
        args.fn(settings, db, args)
    finally:
        db.close()


if __name__ == "__main__":
    main()
