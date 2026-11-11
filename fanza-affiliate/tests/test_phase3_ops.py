"""運用系: Attention Queue / bootstrap / Web UI / pricing / secrets。"""
import io
import json
import threading
from http.server import HTTPServer
from urllib.request import Request, urlopen
from datetime import datetime, timezone

from affiliate_bot import attention, bootstrap, failsafe, patterns, planner, products, webui
from affiliate_bot.bootstrap import ACTION, BLOCKED, READY, IO, StepResult
from affiliate_bot.demo_data import demo_products
from affiliate_bot.secrets_store import LocalEnvStore, mask


def _ctx(db, settings, tmp_path, answers=None, secrets=None, interactive=True):
    db.set_setting("env_platform", "local")
    out = io.StringIO()
    return bootstrap.Ctx(settings=settings, db=db, io=IO(interactive, answers, secrets, out), store=LocalEnvStore(tmp_path / ".env"),
                         repo_root=tmp_path, project_dir=tmp_path, network=False), out


def test_attention_categories_and_notify(db, settings, capsys):
    a = attention.raise_item(db, "fanza_auth", "FANZA API 401", action="再設定")
    assert attention.raise_item(db, "fanza_auth", "FANZA API 401") is None
    try:
        attention.raise_item(db, "auth_expired", "old category")
        assert False
    except AssertionError:
        pass
    settings.notify_console_delivery = False
    assert attention.notify_pending(db, settings) == 0 and "FANZA API 401" in capsys.readouterr().out
    settings.notify_console_delivery = True
    assert attention.notify_pending(db, settings) == 1
    attention.resolve(db, a)
    assert attention.open_items(db) == []


def test_failsafe_only_raises_attention(db, settings):
    patterns.ensure_seed(db)
    products.upsert_products(db, demo_products("FANZA"), 0.2)
    db.exec("UPDATE products SET price=9999, list_price=100 WHERE content_id='demo001'")
    now = datetime.now(timezone.utc).isoformat()
    db.exec("INSERT INTO posts(day,seq,account,product_id,pattern_id,text,scheduled_at,status,posted_at,x_post_id,created_at) VALUES('d',1,'m','demo001','P01','t',?,'posted',?,'x',?)", (now, now, now))
    failsafe.run_checks(db, settings)
    cats = {i["category"] for i in attention.open_items(db)}
    assert "product_inconsistency" in cats
    assert not hasattr(failsafe, "halt")    # 停止機構は存在しない（自動投稿がないため）


def test_bootstrap_check_mode_and_board(db, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "BASE_DIR", tmp_path)
    (tmp_path / "requirements.txt").write_text("requests\n")
    res = bootstrap.run(settings, db, IO(interactive=False, out=io.StringIO()), network=False)
    board = bootstrap.render_board(res, settings, db)
    assert "総合判定" in board and "X READ" in board and "FANZA API" in board
    assert "DRY_RUN" not in board and "Tracking" not in board and "本番運用開始" not in board
    assert not (tmp_path / ".env").exists()
    assert json.loads(db.get_setting("bootstrap_state"))["database"]["status"] == READY


def test_bootstrap_x_read_optional_and_dmm_media(db, settings, tmp_path):
    settings.x_bearer_token = ""
    ctx, out = _ctx(db, settings, tmp_path, answers=["y"], secrets=[""])
    r = bootstrap.step_x_read(ctx)
    assert r.status == READY and "読取なし" in r.summary
    settings.dmm_api_id, settings.dmm_affiliate_id, settings.dmm_media_registered = "APIID", "me-990", False
    ctx, out = _ctx(db, settings, tmp_path, answers=["myhandle", "新作紹介", ""])
    r = bootstrap.step_dmm(ctx)
    assert r.status == ACTION and (tmp_path / "dmm_media_application.md").exists() and "APIID" not in out.getvalue()
    settings.dmm_media_registered = False
    ctx, out = _ctx(db, settings, tmp_path, answers=["承認済み"])
    assert bootstrap.step_dmm(ctx).status == READY and ctx.store.get("DMM_MEDIA_REGISTERED") == "true"


def test_compliance_step_mentions_readonly(db, settings, tmp_path):
    ctx, out = _ctx(db, settings, tmp_path)
    r = bootstrap.step_compliance(ctx)
    assert r.status == READY and any("READ ONLY" in d for d in r.details) and any("HARD BLOCK" in d for d in r.details)


def test_web_ui_today_and_posted(db, settings):
    patterns.ensure_seed(db)
    products.upsert_products(db, demo_products("FANZA"), 0.2)
    products.rescore_all(db)
    planner.plan_day(db, settings, None)
    settings.web_token = "tok"
    srv = HTTPServer(("127.0.0.1", 0), webui.make_handler(db, settings))
    port = srv.server_address[1]
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        body = urlopen(f"http://127.0.0.1:{port}/?t=tok").read().decode()
        assert "今日の投稿" in body and "POST 1" in body and "本文をコピー" in body and "投稿済み" in body and "Affiliate URL" in body
        assert urlopen(Request(f"http://127.0.0.1:{port}/analytics?t=tok")).read().decode().count("パターン") >= 1
        try:
            urlopen(f"http://127.0.0.1:{port}/")
            assert False
        except Exception as e:  # noqa: BLE001
            assert "403" in str(e)
        day = planner.today_packages(db, settings)[0]["day"]
        req = Request(f"http://127.0.0.1:{port}/api/posted?t=tok", data=json.dumps({"day": day, "seq": 1, "url": "https://x.com/me/status/1970000000000000009"}).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
        res = json.loads(urlopen(req).read())
        assert res["ok"] and res["post"]["x_post_id"] == "1970000000000000009"
        assert db.one("SELECT status FROM posts WHERE seq=1")["status"] == "posted"
        body = urlopen(f"http://127.0.0.1:{port}/?t=tok").read().decode()
        assert "✅" in body
    finally:
        srv.shutdown()


def test_pricing_read_only_and_staged(db, settings):
    from affiliate_bot.pricing import XPricing, evaluate_candidate, x_pricing
    cur = x_pricing(settings, db)
    assert cur.as_dict().keys() == {"read_post", "owned_read", "read_user", "source"}
    st, cand, ch = evaluate_candidate(cur, {"read_post": 0.02, "owned_read": 0.001, "read_user": 0.01})
    assert st == "staged" and x_pricing(settings, db).read_post == 0.005
    st, _, _ = evaluate_candidate(cur, {"read_post": 0.0052, "owned_read": 0.001, "read_user": 0.01})
    assert st == "applied"


def test_secret_store_masks(tmp_path):
    st = LocalEnvStore(tmp_path / ".env")
    st.set("X_BEARER_TOKEN", "AAAAbbbbcccc")
    assert st.get("X_BEARER_TOKEN") == "AAAAbbbbcccc" and st.permissions_ok() and "AAAAbbbb" not in mask("AAAAbbbbcccc")


def test_llm_router_roles_and_fallback(db, settings):
    from affiliate_bot.llm import FakeLLMClient, LLMRouter, LLMUnavailable
    fake = FakeLLMClient(['{"x":1}'])
    settings.anthropic_api_key = "k"
    r = LLMRouter(settings, db, client=fake)
    r.call("opus", "s", "u", schema={"type": "object"})
    assert fake.calls[0]["model"] == settings.model_opus and fake.calls[0]["output_config"]["effort"] == "medium"
    r.call("fable", "s", "u")
    assert fake.calls[1]["fallbacks"] == "default"
    db.set_setting("model_map", json.dumps({"fable": "claude-opus-5", "opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5"}))
    r.call("fable", "s", "u")
    assert fake.calls[2]["model"] == "claude-opus-5" and "fallbacks" not in fake.calls[2]
    settings.daily_ai_budget_jpy = 0.0001
    try:
        r.call("sonnet", "s", "u")
        assert False
    except LLMUnavailable:
        pass
