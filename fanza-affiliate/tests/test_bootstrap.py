"""bootstrap / attention / tracking(stateless) / pricing / secrets のテスト（ネットワークなし）。"""
import io
import json
from datetime import datetime, timezone

from affiliate_bot import attention, bootstrap, tracking
from affiliate_bot.bootstrap import ACTION, BLOCKED, READY, IO, StepResult
from affiliate_bot.pricing import XPricing, x_pricing
from affiliate_bot.secrets_store import LocalEnvStore, mask


def _ctx(db, settings, tmp_path, answers=None, secrets=None, interactive=True):
    store = LocalEnvStore(tmp_path / ".env")
    out = io.StringIO()
    return bootstrap.Ctx(settings=settings, db=db, io=IO(interactive, answers, secrets, out), store=store,
                         repo_root=tmp_path, project_dir=tmp_path, network=False), out


def test_local_env_store_masks_and_hardens(tmp_path):
    st = LocalEnvStore(tmp_path / ".env")
    st.set("X_CONSUMER_KEY", "abcdefghij")
    assert st.get("X_CONSUMER_KEY") == "abcdefghij"
    assert st.permissions_ok()
    assert "abcdefghij" not in mask("abcdefghij") and "ij" in mask("abcdefghij")
    st.set("X_CONSUMER_KEY", "zzz")
    assert (tmp_path / ".env").read_text().count("X_CONSUMER_KEY=") == 1


def test_compliance_step_blocks_fanza_and_offers_switch(db, settings, tmp_path):
    settings.dmm_site = "FANZA"
    ctx, out = _ctx(db, settings, tmp_path, answers=["n"])
    r = bootstrap.step_compliance(ctx)
    assert r.status == BLOCKED and "HARD BLOCK" in r.summary
    ctx, out = _ctx(db, settings, tmp_path, answers=["y", "digital", "videoa", "n"])
    r = bootstrap.step_compliance(ctx)
    assert r.status == READY and ctx.store.get("DMM_SITE") == "DMM.com"


def test_check_mode_never_prompts_and_reports_missing(db, settings, tmp_path):
    settings.anthropic_api_key = ""
    settings.dmm_api_id = settings.dmm_affiliate_id = ""
    settings.x_consumer_key = ""
    ctx, out = _ctx(db, settings, tmp_path, interactive=False)
    assert bootstrap.step_anthropic(ctx).status == ACTION
    assert bootstrap.step_dmm(ctx).status == ACTION
    assert bootstrap.step_x(ctx).status == ACTION
    r = bootstrap.step_go_live(ctx)
    assert r.status == ACTION and settings.dry_run


def test_dmm_step_validates_affiliate_id_and_media_registration(db, settings, tmp_path):
    settings.dmm_api_id = settings.dmm_affiliate_id = ""
    ctx, out = _ctx(db, settings, tmp_path, answers=["bad-id"], secrets=["APIID123"])
    assert bootstrap.step_dmm(ctx).status == ACTION
    ctx, out = _ctx(db, settings, tmp_path, answers=["good-990", "myhandle", "動画紹介", ""], secrets=["APIID123"])
    settings.dmm_media_registered = False
    r = bootstrap.step_dmm(ctx)
    assert r.status == ACTION and "媒体登録 未承認" in r.summary
    assert (settings.data_dir / "dmm_media_application.md").exists()
    assert "APIID123" not in out.getvalue()               # Secret は画面に出ない
    assert attention.open_items(db)[0]["category"] == "review_needed"
    settings.dmm_api_id, settings.dmm_affiliate_id, settings.dmm_media_registered = "APIID123", "good-990", False
    ctx, out = _ctx(db, settings, tmp_path, answers=["承認済み"])
    r = bootstrap.step_dmm(ctx)
    assert r.status == READY and ctx.store.get("DMM_MEDIA_REGISTERED") == "true"
    assert attention.open_items(db) == []


def test_go_live_requires_exact_phrase(db, settings, tmp_path):
    ctx, out = _ctx(db, settings, tmp_path, answers=["はい"])
    for k, _ in bootstrap.BOARD_KEYS:
        ctx.results[k] = StepResult(READY, "ok")
    assert bootstrap.step_go_live(ctx).status == ACTION
    assert db.get_setting("go_live_approved_at") is None
    ctx, out = _ctx(db, settings, tmp_path, answers=["本番運用開始"])
    for k, _ in bootstrap.BOARD_KEYS:
        ctx.results[k] = StepResult(READY, "ok")
    r = bootstrap.step_go_live(ctx)
    assert r.status == READY and db.get_setting("go_live_approved_at") and ctx.store.get("DRY_RUN") == "false"


def test_go_live_blocked_when_not_all_ready(db, settings, tmp_path):
    ctx, out = _ctx(db, settings, tmp_path, answers=["本番運用開始"])
    for k, _ in bootstrap.BOARD_KEYS:
        ctx.results[k] = StepResult(READY, "ok")
    ctx.results["tracking"] = StepResult(ACTION, "未構築")
    assert bootstrap.step_go_live(ctx).status == ACTION
    assert db.get_setting("go_live_approved_at") is None


def test_board_render_and_run_check(db, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "BASE_DIR", tmp_path)
    (tmp_path / "requirements.txt").write_text("requests\n")
    settings.anthropic_api_key = ""
    res = bootstrap.run(settings, db, IO(interactive=False, out=io.StringIO()), network=False)
    board = bootstrap.render_board(res, settings, db)
    assert "総合判定" in board and "ACTION REQUIRED" in board
    assert json.loads(db.get_setting("bootstrap_state"))["database"]["status"] == READY


def test_stateless_tracking_roundtrip(settings):
    settings.tracking_base_url = "https://t.example.com"
    settings.tracking_secret = "s3cret"
    link = tracking.build_link(settings, "abc12345", "https://al.dmm.com/?lurl=x&af_id=y-990")
    assert link.startswith("https://t.example.com/r/")
    token = link.split("/r/")[1]
    assert tracking.verify_payload("s3cret", token) == ("abc12345", "https://al.dmm.com/?lurl=x&af_id=y-990")
    assert tracking.verify_payload("wrong", token) is None
    assert tracking.verify_payload("s3cret", token[:-1] + "0") is None
    settings.tracking_secret = ""
    assert tracking.build_link(settings, "abc", "https://x") == "https://t.example.com/r/abc"
    settings.tracking_base_url = ""
    assert tracking.build_link(settings, "abc", "https://x") == "https://x"


def test_vercel_function_verifies_same_signature(settings):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("vr", Path(__file__).resolve().parent.parent / "deploy" / "vercel-tracking" / "api" / "r.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    token = tracking.sign_payload("k", "c1", "https://www.dmm.com/x")
    assert mod.verify("k", token) == "https://www.dmm.com/x"
    assert mod.verify("k2", token) is None


def test_attention_queue_dedupe_and_notify(db, settings, capsys):
    a = attention.raise_item(db, "auth_expired", "X 401", action="再発行")
    b = attention.raise_item(db, "auth_expired", "X 401", action="再発行")
    assert a and b is None
    assert attention.notify_pending(db, settings) == 1
    assert "X 401" in capsys.readouterr().out
    assert attention.notify_pending(db, settings) == 0
    attention.resolve(db, a)
    assert attention.open_items(db) == []


def test_metrics_delta_derives_clicks(db, settings):
    from affiliate_bot import metrics
    settings.tracking_base_url = "https://t.example.com"; settings.tracking_secret = "k"
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    db.exec("INSERT INTO posts(post_id,account,product_id,pattern_id,text,scheduled_at,status,posted_at,x_post_id,tracking_code,created_at) "
            "VALUES(1,'m','p','P01','t',?,'posted',?,'111','code1',?)", (now, now, now))

    class FakeX:
        def __init__(self, clicks): self.clicks = clicks
        def post_metrics(self, ids):
            return {"111": {"views": 100, "likes": 0, "reposts": 0, "replies": 0, "quotes": 0, "bookmarks": 0,
                            "profile_visits": 0, "url_clicks": self.clicks}}, 0.001
    metrics.ingest_x_metrics(db, settings, FakeX(3))
    metrics.ingest_x_metrics(db, settings, FakeX(5))
    assert db.one("SELECT COUNT(*) c FROM clicks WHERE tracking_code='code1'")["c"] == 5


def test_pricing_env_then_db(db, settings):
    settings.x_price_post_url_usd = 0.30
    assert x_pricing(settings, db).post_url == 0.30
    db.set_setting("x_pricing", json.dumps(XPricing(0.02, 0.25, 0.005, 0.001, 0.01, "official_page").as_dict()))
    p = x_pricing(settings, db)
    assert p.post == 0.02 and p.post_url == 0.25 and p.source == "official_page"


def test_profit_negative_raises_attention(db, settings):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for i in range(25):
        db.exec("INSERT INTO posts(account,product_id,pattern_id,text,scheduled_at,status,posted_at,api_cost_jpy,created_at) "
                "VALUES('m','p','P01','t',?,'posted',?,32,?)", (now, now, now))
    attention.check_profit_negative(db)
    items = attention.open_items(db)
    assert items and items[0]["category"] == "profit_negative"
