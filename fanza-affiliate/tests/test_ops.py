"""運用自動化レイヤー（GitHub Issues / Actions / Discord）のテスト。GitHub は in-memory の偽物で置き換える。"""
import random
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from affiliate_bot import attention, notify, ops, patterns, planner, products, research
from affiliate_bot.demo_data import DEMO_RESEARCH_CSV, demo_products
from affiliate_bot.policy import HUMAN_POSTING_NOTICE

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "ops" / "template"


class FakeGitHub(ops.GitHub):
    def __init__(self):
        super().__init__("t", "me/fanza-ops")
        self.dry_run = False
        self.issues: dict[int, dict] = {}
        self.comments: dict[int, list[dict]] = {}
        self._n = 0
        self._cid = 0

    def add_human_comment(self, number, body, assoc="OWNER", typ="User"):
        self._cid += 1
        self.comments.setdefault(number, []).append({"id": self._cid, "body": body, "author_association": assoc, "user": {"type": typ}})

    def _req(self, method, path, payload=None, params=None):
        self.log.append((method, path, payload))
        if method == "POST" and path == "/issues":
            self._n += 1
            self.issues[self._n] = {**payload, "number": self._n, "state": "open"}
            return {"number": self._n, "html_url": self.issue_url(self._n)}
        m = re.match(r"/issues/(\d+)(/comments)?$", path)
        n = int(m.group(1))
        if m.group(2):
            if method == "GET":
                return self.comments.get(n, []) if (params or {}).get("page", 1) == 1 else []
            self._cid += 1
            self.comments.setdefault(n, []).append({"id": self._cid, "body": payload["body"], "author_association": "NONE", "user": {"type": "Bot"}})
            return {"id": self._cid}
        if method == "PATCH":
            self.issues[n].update(payload)
            return self.issues[n]
        return self.issues.get(n, {})


class FakeSession:
    def __init__(self, status=204):
        self.calls, self.status = [], status

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        return type("R", (), {"status_code": self.status})()


def _seed_day(db, settings, day="2030-01-01"):
    patterns.ensure_seed(db)
    products.upsert_products(db, demo_products("FANZA"), 0.2)
    products.rescore_all(db)
    research.import_csv(db, DEMO_RESEARCH_CSV)
    planner.plan_day(db, settings, None, day_jst=datetime.fromisoformat(day).replace(tzinfo=timezone.utc), rng=random.Random(3))
    return day


def test_daily_issue_body_and_lifecycle(db, settings):
    day = _seed_day(db, settings)
    gh = FakeGitHub()
    n = ops.publish_daily_issue(db, settings, gh, day, report_md="# 日次レポート")
    issue = gh.issues[n]
    body = issue["body"]
    assert issue["title"] == f"📅 {day} 投稿セット" and issue["labels"] == [ops.LABEL_DAILY]
    pk = planner.today_packages(db, settings, day)
    assert body.count("- [ ] ") == len(pk) == settings.posts_per_day
    for p in pk:
        assert f'<a id="post-{p["seq"]}"></a>' in body and p["text"] in body
        if p.get("affiliate_url"):
            assert p["affiliate_url"] in body
    assert HUMAN_POSTING_NOTICE in body and "昨日のレポート" in body
    # 同じ日に再実行しても新しい Issue は作らない
    assert ops.publish_daily_issue(db, settings, gh, day) == n and len(gh.issues) == 1
    # 翌日分を作ると前日の Issue は閉じる
    _seed_day(db, settings, "2030-01-02")
    n2 = ops.publish_daily_issue(db, settings, gh, "2030-01-02")
    assert n2 != n and gh.issues[n]["state"] == "closed" and "未登録" in gh.comments[n][-1]["body"]


def test_comment_commands_register_skip_metrics_and_close(db, settings):
    day = _seed_day(db, settings)
    gh = FakeGitHub()
    n = ops.publish_daily_issue(db, settings, gh, day)
    gh.add_human_comment(n, "投稿しました https://x.com/me/status/1900000000000000001")
    gh.add_human_comment(n, "/posted 3 https://twitter.com/me/status/1900000000000000003?s=20")
    gh.add_human_comment(n, "https://x.com/evil/status/1900000000000000009", assoc="NONE")        # 第三者は無視
    gh.add_human_comment(n, "https://x.com/bot/status/1900000000000000008", assoc="OWNER", typ="Bot")
    assert ops.sync_comments(db, settings, gh, issue=n) == 2
    rows = {r["seq"]: dict(r) for r in db.q("SELECT seq, status, x_post_id FROM posts WHERE day=?", (day,))}
    assert rows[3]["status"] == "posted" and rows[3]["x_post_id"] == "1900000000000000003"
    assert sum(1 for r in rows.values() if r["status"] == "posted") == 2
    assert not db.one("SELECT 1 FROM posts WHERE x_post_id IN ('1900000000000000009','1900000000000000008')")
    assert gh.issues[n]["body"].count("- [x] ") == 2
    # 同じコメントは二度処理しない / 登録済み POST への再指定は拒否
    assert ops.sync_comments(db, settings, gh, issue=n) == 0
    gh.add_human_comment(n, "/posted 3 https://x.com/me/status/1900000000000000033")
    ops.sync_comments(db, settings, gh, issue=n)
    assert "既に posted" in gh.comments[n][-1]["body"]
    # 指標の手入力
    posted_seq = next(s for s, r in rows.items() if r["status"] == "posted")
    gh.add_human_comment(n, f"/metrics {posted_seq} 1200 8 1 0 2")
    ops.sync_comments(db, settings, gh, issue=n)
    pid = db.one("SELECT post_id FROM posts WHERE day=? AND seq=?", (day, posted_seq))["post_id"]
    assert db.one("SELECT views FROM post_metrics WHERE post_id=? AND source='manual'", (pid,))["views"] == 1200
    # 残りをスキップすると Issue が閉じる
    left = [s for s, r in rows.items() if r["status"] == "planned"]
    gh.add_human_comment(n, "\n".join(f"/skip {s} 在庫切れ" for s in left))
    ops.sync_comments(db, settings, gh, issue=n)
    assert gh.issues[n]["state"] == "closed"
    gh.add_human_comment(n, "/help")
    ops.sync_comments(db, settings, gh, issue=n)
    assert "/skip 2 理由" in gh.comments[n][-1]["body"]


def test_reminders_carry_no_adult_text(db, settings):
    day = _seed_day(db, settings)
    gh = FakeGitHub()
    n = ops.publish_daily_issue(db, settings, gh, day)
    first = db.one("SELECT post_id, seq, scheduled_at FROM posts WHERE day=? ORDER BY scheduled_at LIMIT 1", (day,))
    now = datetime.fromisoformat(first["scheduled_at"]) - timedelta(minutes=30)
    titles = [r["title"] for r in db.q("SELECT title FROM products")]
    settings.discord_webhook_url = "https://discord.example/webhook"
    s = FakeSession()
    assert ops.remind(db, settings, gh, now=now, session=s) >= 1
    url, payload = s.calls[0]
    assert payload["flags"] == 4 and payload["allowed_mentions"] == {"parse": []}
    assert f"POST {first['seq']}" in payload["content"] and gh.issue_url(n, f"post-{first['seq']}") in payload["content"]
    assert not any(t in payload["content"] for t in titles)
    assert ops.remind(db, settings, gh, now=now, session=s) == 0          # 二重送信しない
    # Webhook が無ければ日次 Issue へのメンションコメント（GitHub Mobile に通知）
    settings.discord_webhook_url = ""
    settings.ops_mention = "owner"
    db.exec("DELETE FROM settings WHERE key LIKE 'ops:reminded:%'")
    ops.remind(db, settings, gh, now=now)
    assert gh.comments[n][-1]["body"].startswith("@owner ⏰")


def test_attention_issue_sync_and_close(db, settings):
    gh = FakeGitHub()
    iid = attention.raise_item(db, "fanza_auth", "FANZA API 401", detail="bad", action="API ID を再発行", severity="critical")
    settings.discord_webhook_url = "https://discord.example/webhook"
    s = FakeSession()
    assert ops.sync_attention(db, settings, gh, session=s) == {"opened": 1, "closed": 0}
    n = max(gh.issues)
    assert "attention:fanza_auth" in gh.issues[n]["labels"] and "API ID を再発行" in gh.issues[n]["body"]
    assert s.calls and "🚨" in s.calls[0][1]["content"]
    assert db.one("SELECT notified_at FROM attention_queue WHERE id=?", (iid,))["notified_at"]
    assert ops.sync_attention(db, settings, gh, session=s)["opened"] == 0
    assert ops.issue_closed(db, n) and not attention.open_items(db)
    assert not ops.issue_closed(db, 9999)
    # コード側で解決した場合は Issue を閉じる
    iid2 = attention.raise_item(db, "data_stale", "7 日間データなし")
    ops.sync_attention(db, settings, gh)
    n2 = max(gh.issues)
    attention.resolve(db, iid2)
    assert ops.sync_attention(db, settings, gh)["closed"] == 1 and gh.issues[n2]["state"] == "closed"


def test_inbox_detects_csv_types(db, settings, tmp_path):
    day = _seed_day(db, settings)
    pid = db.one("SELECT post_id, product_id FROM posts WHERE day=? ORDER BY seq LIMIT 1", (day,))
    db.exec("UPDATE posts SET status='posted', x_post_id='1900000000000000001', posted_at='2030-01-01T03:00:00+00:00' WHERE post_id=?", (pid["post_id"],))
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "conv.csv").write_text(f"日時,商品ID,報酬,注文ID\n2030-01-01 13:00:00,{pid['product_id']},196,o-1\n", encoding="cp932")
    (inbox / "metrics.csv").write_text("x_post_id,views,likes,reposts,replies,bookmarks\n1900000000000000001,900,5,1,0,1\n", encoding="utf-8")
    (inbox / "bad.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (inbox / "research.csv").write_text('x_post_id,followers,text,media_type,created_at,views,likes,reposts,replies,bookmarks\n'
                                        '9001,700,"50%OFF｜1,980円\\n「作品の名前です」\\n詳細はリプ欄",photo,2026-11-01T13:00:00+00:00,30000,300,40,3,90\n',
                                        encoding="utf-8")
    res = {f.name: r for f, r in ops.ingest_inbox(db, settings, inbox)}
    assert res["conv.csv"].startswith("成果 CSV: 1") and res["metrics.csv"].startswith("指標 CSV: 1")
    assert res["research.csv"].startswith("調査 CSV") and db.one("SELECT 1 FROM skeletons WHERE source='research'")
    assert res["bad.csv"].startswith("失敗") and any(i["category"] == "csv_ingest_failed" for i in attention.open_items(db))


def test_notify_chunks_and_suppresses_unfurl(settings):
    settings.discord_webhook_url = "https://discord.example/w"
    settings.slack_webhook_url = "https://hooks.slack.example/x"
    s = FakeSession()
    assert notify.send(settings, "\n".join(f"line {i} " + "x" * 80 for i in range(60)), session=s)
    discord = [p for u, p in s.calls if "discord" in u]
    slack = [p for u, p in s.calls if "slack" in u]
    assert len(discord) >= 2 and all(len(p["content"]) <= notify.DISCORD_LIMIT for p in discord)
    assert slack[0]["unfurl_links"] is False and slack[0]["unfurl_media"] is False
    assert not notify.send(settings, "x", session=FakeSession(status=500))


def test_dry_run_without_token_never_calls_github(settings):
    gh = ops.GitHub.from_settings(settings)
    assert gh.dry_run
    assert gh.create_issue("t", "b", [])["number"] > 0 and gh.list_comments(1) == []
    # CI（公開リポジトリ）では GITHUB_REPOSITORY だけが自動設定される → トークンが無いので書き込まない
    settings.github_repository = "Mgymand/my-automation"
    assert ops.GitHub.from_settings(settings).dry_run


def test_workflow_templates_are_safe_and_valid():
    cli_src = (ROOT / "affiliate_bot" / "cli.py").read_text(encoding="utf-8")
    ops_actions = set(re.search(r'add_argument\("action", choices=\[([^\]]+)\]', cli_src).group(1).replace('"', "").replace(" ", "").split(","))
    wfs = sorted((TEMPLATE / ".github" / "workflows").glob("*.yml"))
    assert len(wfs) == 6
    action = yaml.safe_load((TEMPLATE / ".github" / "actions" / "fanza-run" / "action.yml").read_text(encoding="utf-8"))
    run_steps = " ".join(s.get("run", "") for s in action["runs"]["steps"])
    assert "ops_state.sh pull" in run_steps and "ops_state.sh push" in run_steps
    assert "${{ inputs.command }}" not in run_steps                     # 入力値を run に直接埋め込まない
    for wf in wfs:
        text = wf.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        job = data["jobs"]["run"]
        assert "github.event.repository.private == true" in job["if"]    # 公開リポジトリでは動かない
        assert data["concurrency"]["group"] == "fanza-ops-state" and data["concurrency"]["cancel-in-progress"] is False
        assert "comment.body" not in text and "issue.title" not in text   # 外部入力を式に展開しない
        cmd = job["steps"][1]["with"]["command"].split()
        assert (cmd[0] == "ops" and cmd[1] in ops_actions) or cmd == ["status"]
    comment_if = yaml.safe_load((TEMPLATE / ".github" / "workflows" / "fanza-ops-comment.yml").read_text(encoding="utf-8"))["jobs"]["run"]["if"]
    assert "author_association" in comment_if and "Bot" in comment_if


def test_ops_layer_has_no_x_write_path():
    src = (ROOT / "affiliate_bot" / "ops.py").read_text(encoding="utf-8") + (ROOT / "affiliate_bot" / "notify.py").read_text(encoding="utf-8")
    assert "api.x.com" not in src and "api.twitter.com" not in src and "/2/tweets" not in src
