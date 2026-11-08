"""運用自動化レイヤー（GitHub Actions + GitHub Issues + Discord/Slack。すべて無料枠で動く）。

private の「運用リポジトリ」で GitHub Actions から呼ばれる。人間の画面は GitHub Issues（GitHub Mobile で通知が届く）。

  毎朝  : `ops morning`  商品更新 → 学習 → 検知 → 計画 → レポート → 「📅 今日の投稿セット」Issue → 通知
  毎時  : `ops hourly`   指標取得（X READ）→ 投稿時刻リマインド → コメント取込（取りこぼし回収）→ 要対応 Issue 同期
  毎週  : `ops weekly`   公開投稿の調査 → 規約ページ確認 → 週次レビュー Issue
  随時  : `ops sync-comments --issue N`  人間が投稿 URL をコメント → `posted` 登録 → チェックリスト更新
          `ops issue-closed --issue N`   要対応 Issue を人間が閉じた → Attention Queue を解決
          `ops inbox --dir inbox`        アップロードされた成果 CSV / 指標 CSV を取込

X への投稿はここでも行わない（投稿権限を持つコードは存在しない）。人間の作業は「投稿 → URL をコメント」だけ。
GITHUB_TOKEN / GITHUB_REPOSITORY が無い環境では GitHub への書込を行わず内容を表示する（ローカル確認用）。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from . import attention, metrics, notify, posted
from .config import Settings
from .db import Database, utcnow
from .policy import HUMAN_POSTING_NOTICE

LABEL_DAILY = "daily-posts"
LABEL_ATTENTION = "attention"
LABEL_WEEKLY = "weekly-review"
TRUSTED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
X_URL_RE = re.compile(r"https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/[A-Za-z0-9_]+/status/\d+[^\s)>\]]*")
DAY_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


# ---------------------------------------------------------------- GitHub REST
class GitHub:
    """最小限の GitHub REST クライアント。token が無ければ dry-run（書込内容を表示し、仮の番号を返す）。"""

    def __init__(self, token: str, repo: str, api: str = "https://api.github.com", server: str = "https://github.com",
                 session: requests.Session | None = None):
        self.token, self.repo, self.api, self.server = token, repo, api.rstrip("/"), server.rstrip("/")
        self.s = session or requests.Session()
        self.dry_run = not (token and repo)
        self._fake = 1000
        self.log: list[tuple[str, str, dict | None]] = []

    @classmethod
    def from_settings(cls, settings: Settings, session: requests.Session | None = None) -> "GitHub":
        return cls(settings.github_token, settings.github_repository, settings.github_api_url, settings.github_server_url, session)

    def issue_url(self, number: int, anchor: str = "") -> str:
        repo = self.repo or "OWNER/REPO"
        return f"{self.server}/{repo}/issues/{number}" + (f"#{anchor}" if anchor else "")

    def _req(self, method: str, path: str, payload: dict | None = None, params: dict | None = None):
        self.log.append((method, path, payload))
        if self.dry_run:
            if method == "GET":
                return []
            self._fake += 1
            print(f"[dry-run] {method} {path}\n" + (json.dumps(payload, ensure_ascii=False)[:600] if payload else ""))
            return {"number": self._fake, "html_url": self.issue_url(self._fake), "id": self._fake}
        r = self.s.request(method, f"{self.api}/repos/{self.repo}{path}", json=payload, params=params, timeout=30,
                           headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                                    "X-GitHub-Api-Version": "2022-11-28"})
        if r.status_code >= 400:
            raise RuntimeError(f"GitHub {method} {path} → HTTP {r.status_code}: {r.text[:200]}")
        return r.json() if r.content else {}

    def create_issue(self, title: str, body: str, labels: list[str]) -> dict:
        return self._req("POST", "/issues", {"title": title, "body": body, "labels": labels})

    def update_issue(self, number: int, **fields) -> dict:
        return self._req("PATCH", f"/issues/{number}", fields)

    def comment(self, number: int, body: str) -> dict:
        return self._req("POST", f"/issues/{number}/comments", {"body": body})

    def get_issue(self, number: int) -> dict:
        r = self._req("GET", f"/issues/{number}")
        return r if isinstance(r, dict) else {}

    def list_comments(self, number: int) -> list[dict]:
        out, page = [], 1
        while True:
            r = self._req("GET", f"/issues/{number}/comments", params={"per_page": 100, "page": page})
            if not r:
                return out
            out += r
            if len(r) < 100:
                return out
            page += 1


# ---------------------------------------------------------------- 日次 Issue
def _fence(text: str) -> str:
    return "```text\n" + (text or "").replace("```", "ˋˋˋ") + "\n```"


def _price(p: dict) -> str:
    if not p.get("price"):
        return "-"
    s = f"{int(p['price']):,}円"
    if p.get("list_price") and p["list_price"] > p["price"]:
        s += f"（通常 {int(p['list_price']):,}円）"
    return s


def _check_line(p: dict) -> str:
    title = (p.get("title") or "")[:28]
    if p.get("status") == "posted":
        link = f" ✅ [投稿]({p['x_url']})" if p.get("x_url") else " ✅"
        return f"- [x] **{p['scheduled_local']} POST {p['seq']}** {title}{link}"
    if p.get("status") == "skipped":
        return f"- [x] ~~{p['scheduled_local']} POST {p['seq']} {title}~~ スキップ"
    return f"- [ ] **{p['scheduled_local']} POST {p['seq']}** {title} → [本文](#post-{p['seq']})"


def render_daily_issue(packages: list[dict], day: str, report_md: str = "", adjustments: list[str] | None = None) -> str:
    done = sum(1 for p in packages if p.get("status") in ("posted", "skipped"))
    out = [f"<!-- fanza-ops:daily:{day} -->",
           f"## 今日の時刻表（{done}/{len(packages)} 完了）",
           *[_check_line(p) for p in packages], "",
           "## 投稿したら、このIssueに投稿URLをコメントするだけ",
           "- `https://x.com/あなた/status/…` を貼る → POST 番号は予定時刻から自動判定し、チェックが付きます",
           "- 番号を指定: `/posted 2 https://x.com/…/status/…`　投稿しない: `/skip 2 理由`",
           "- X READ が無いときの指標入力: `/metrics 2 views likes reposts replies bookmarks`　使い方: `/help`", ""]
    if adjustments:
        out += ["## 本日の調整", *[f"- {a}" for a in adjustments], ""]
    for p in packages:
        pred = p.get("predicted") or {}
        out += ["---", f'<a id="post-{p["seq"]}"></a>',
                f"### POST {p['seq']} — {p['scheduled_local']}（優先度 {p.get('priority') or '-'}）" + ("　✅ 投稿済" if p.get("status") == "posted" else ""),
                "**本文（コピーして投稿）**", _fence(p["text"]),
                "**リプ欄に貼る Affiliate URL**", _fence(p.get("affiliate_url") or "-"),
                f"- 素材: {('[DMM 公式素材を開く](' + p['media_source'] + ')') if p.get('media_source') else '（公式素材なし）'}"
                f"（{'動画' if p.get('media_type') == 'video' else '画像' if p.get('media_type') == 'image' else 'なし'} / 権利: {'OK・DMM 公式' if p.get('media_source') else '要確認'}）",
                f"- 商品: {p.get('title')}｜{_price(p)}" + (f"｜{int(float(p['discount_rate']) * 100)}%OFF" if p.get("discount_rate") else ""),
                f"- 女優: {'・'.join(p.get('actresses') or []) or '-'}｜ジャンル: {'・'.join((p.get('genres') or [])[:4]) or '-'}",
                f"- Pattern: {p.get('pattern_id')}（{p.get('pattern_name') or ''}）/ 訴求軸 {p.get('angle')}",
                f"- 選んだ理由: {p.get('reason') or '-'}",
                f"- 期待値: Views {pred.get('views', '-')} / CTR {pred.get('ctr', '-')} / CVR {pred.get('cvr', '-')} / 収益 {pred.get('revenue', '-')} 円"]
        notes = [n for n in (p.get("notes") or []) if n != HUMAN_POSTING_NOTICE]
        if notes:
            out += ["- 投稿時の注意:", *[f"  - {n}" for n in notes]]
        alts = p.get("alternatives") or []
        if alts:
            out += ["<details><summary>代替案</summary>", "", *[f"**[{a.get('angle')}]**\n{_fence(a.get('text') or '')}" for a in alts], "</details>"]
        out.append("")
    out += ["---", f"> {HUMAN_POSTING_NOTICE}"]
    if report_md:
        out += ["", "<details><summary>昨日のレポート</summary>", "", report_md, "", "</details>"]
    return "\n".join(out)


def daily_title(day: str) -> str:
    return f"📅 {day} 投稿セット"


def _today(settings: Settings) -> str:
    return datetime.now(ZoneInfo(settings.timezone)).strftime("%Y-%m-%d")


def _issue_for_day(db: Database, day: str) -> int | None:
    v = db.get_setting(f"ops:daily_issue:{day}")
    return int(v) if v else None


def _day_for_issue(db: Database, number: int, title: str = "") -> str | None:
    v = db.get_setting(f"ops:daily_issue_day:{number}")
    if v:
        return v
    m = DAY_RE.search(title or "")
    return m.group(1) if m else None


def refresh_daily_issue(db: Database, settings: Settings, gh: GitHub, day: str) -> int | None:
    from .planner import today_packages
    number = _issue_for_day(db, day)
    if not number:
        return None
    pk = today_packages(db, settings, day)
    body = render_daily_issue(pk, day, db.get_setting(f"ops:daily_report:{day}") or "", json.loads(db.get_setting("today_adjustments") or "[]"))
    fields = {"body": body}
    if pk and all(p.get("status") in ("posted", "skipped") for p in pk):
        fields["state"] = "closed"
    gh.update_issue(number, **fields)
    return number


def publish_daily_issue(db: Database, settings: Settings, gh: GitHub, day: str | None = None, report_md: str = "") -> int | None:
    from .planner import today_packages
    day = day or _today(settings)
    pk = today_packages(db, settings, day)
    if not pk:
        return None
    if report_md:
        db.set_setting(f"ops:daily_report:{day}", report_md[:20000])
    number = _issue_for_day(db, day)
    if number:
        return refresh_daily_issue(db, settings, gh, day)
    # 前日までの開いたままの日次 Issue を閉じる（未登録分は後からコメントで登録できる）
    for key in [r["key"] for r in db.q("SELECT key FROM settings WHERE key LIKE 'ops:daily_issue:%'")]:
        old_day = key.rsplit(":", 1)[1]
        if old_day < day and not db.get_setting(f"ops:daily_closed:{old_day}"):
            n = int(db.get_setting(key))
            left = db.one("SELECT COUNT(*) c FROM posts WHERE day=? AND status='planned'", (old_day,))["c"]
            if left:
                gh.comment(n, f"日付が変わったため閉じます。未登録 {left} 件は、投稿済みならこのIssueに URL をコメントすれば後からでも登録されます。")
            gh.update_issue(n, state="closed")
            db.set_setting(f"ops:daily_closed:{old_day}", "1")
    body = render_daily_issue(pk, day, report_md, json.loads(db.get_setting("today_adjustments") or "[]"))
    res = gh.create_issue(daily_title(day), body, [LABEL_DAILY])
    number = int(res["number"])
    db.set_setting(f"ops:daily_issue:{day}", number)
    db.set_setting(f"ops:daily_issue_day:{number}", day)
    db.log_event("info", "ops_daily_issue", f"{day} の投稿セット Issue #{number}", {"posts": len(pk)})
    return number


# ---------------------------------------------------------------- コメント → 登録
HELP = """使い方（このIssueにコメント）:
- 投稿URLを貼るだけ → 予定時刻が一番近い未登録の POST に紐付け
- `/posted 2 https://x.com/…/status/…` → POST 2 に紐付け
- `/skip 2 理由` → POST 2 を投稿しない
- `/metrics 2 1200 8 1 0 2` → POST 2 の指標（views likes reposts replies bookmarks）を手入力
- `/help` → この説明"""


def _post_id_for(db: Database, day: str, seq: int) -> int | None:
    r = db.one("SELECT post_id FROM posts WHERE day=? AND seq=?", (day, seq))
    return r["post_id"] if r else None


def handle_comment(db: Database, settings: Settings, day: str, body: str, x=None) -> list[str]:
    """コメント本文を解釈して実行。返り値は結果行（返信に使う）。"""
    results: list[str] = []
    text = (body or "").strip()
    consumed: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^/posted\s+(\d+)\s+(\S+)", line)
        if m:
            seq, url = int(m.group(1)), m.group(2)
            consumed.add(url)
            results.append(_register(db, settings, day, url, seq, x))
            continue
        m = re.match(r"^/posted\s+(\S+)", line)
        if m:
            consumed.add(m.group(1))
            results.append(_register(db, settings, day, m.group(1), None, x))
            continue
        m = re.match(r"^/skip\s+(\d+)\s*(.*)$", line)
        if m:
            seq = int(m.group(1))
            row = db.one("SELECT status FROM posts WHERE day=? AND seq=?", (day, seq))
            if not row:
                results.append(f"⚠️ POST {seq} は {day} にありません")
            elif row["status"] != "planned":
                results.append(f"ℹ️ POST {seq} は既に {row['status']} です")
            else:
                posted.skip(db, day, seq, m.group(2).strip())
                results.append(f"⏭ POST {seq} をスキップにしました")
            continue
        m = re.match(r"^/metrics\s+(\d+)\s+([\d\s]+)$", line)
        if m:
            seq = int(m.group(1))
            vals = [int(v) for v in m.group(2).split()]
            pid = _post_id_for(db, day, seq)
            if not pid or not vals:
                results.append(f"⚠️ POST {seq} の指標を保存できません（{day} に無い / 値が無い）")
            else:
                vals = (vals + [0] * 5)[:5]
                metrics.ingest_manual_metrics(db, pid, *vals)
                results.append(f"📊 POST {seq}: views {vals[0]:,} / likes {vals[1]} / reposts {vals[2]} / replies {vals[3]} / bookmarks {vals[4]} を保存")
            continue
        if line.startswith("/help"):
            results.append(HELP)
    for url in X_URL_RE.findall(text):
        if url in consumed or any(url.startswith(c) or c.startswith(url) for c in consumed):
            continue
        results.append(_register(db, settings, day, url, None, x))
    return results


def _register(db: Database, settings: Settings, day: str, url: str, seq: int | None, x) -> str:
    if seq is not None:
        row = db.one("SELECT status FROM posts WHERE day=? AND seq=?", (day, seq))
        if not row:
            return f"⚠️ POST {seq} は {day} にありません"
        if row["status"] != "planned":
            return f"ℹ️ POST {seq} は既に {row['status']} です（別の POST なら番号を指定してください）"
    try:
        res = posted.register(db, settings, url, seq=seq, day=day, x=x)
        return f"✅ POST {res['seq']}（{res['day']}）を登録しました → 24h / 72h 後に指標を自動取得します"
    except ValueError as e:
        msg = str(e)
        if "登録済み" in msg:
            return f"ℹ️ {msg}"
        return f"⚠️ 登録できません: {msg}"


def sync_comments(db: Database, settings: Settings, gh: GitHub, issue: int | None = None, x=None) -> int:
    """日次 Issue の新しいコメントを取り込む（イベント駆動の取りこぼしは毎時の実行で回収）。"""
    numbers: list[int]
    if issue:
        numbers = [issue]
    else:
        days = sorted({r["key"].rsplit(":", 1)[1] for r in db.q("SELECT key FROM settings WHERE key LIKE 'ops:daily_issue:%'")})[-3:]
        numbers = [_issue_for_day(db, d) for d in days if _issue_for_day(db, d)]
    handled = 0
    for n in numbers:
        day = db.get_setting(f"ops:daily_issue_day:{n}") or _day_for_issue(db, n, (gh.get_issue(n) or {}).get("title", ""))
        if not day:
            continue
        changed = False
        for c in gh.list_comments(n):
            cid = str(c.get("id"))
            if db.get_setting(f"ops:comment_done:{cid}"):
                continue
            user = c.get("user") or {}
            db.set_setting(f"ops:comment_done:{cid}", "1")
            if user.get("type") == "Bot" or c.get("author_association") not in TRUSTED_ASSOCIATIONS:
                continue
            res = handle_comment(db, settings, day, c.get("body") or "", x)
            if res:
                gh.comment(n, "\n".join(res))
                handled += 1
                changed = True
        if changed:
            refresh_daily_issue(db, settings, gh, day)
    return handled


# ---------------------------------------------------------------- リマインド
def remind(db: Database, settings: Settings, gh: GitHub, now: datetime | None = None, session: requests.Session | None = None) -> int:
    """次の投稿予定をプッシュ通知（通知本文に商品名・本文は入れない）。"""
    now = now or datetime.now(timezone.utc)
    lo = (now - timedelta(minutes=15)).isoformat(timespec="seconds")
    hi = (now + timedelta(minutes=settings.ops_remind_lead_min)).isoformat(timespec="seconds")
    rows = db.q("SELECT post_id, day, seq, scheduled_at FROM posts WHERE status='planned' AND scheduled_at>=? AND scheduled_at<? ORDER BY scheduled_at", (lo, hi))
    tz = ZoneInfo(settings.timezone)
    sent = 0
    for r in rows:
        if db.get_setting(f"ops:reminded:{r['post_id']}"):
            continue
        n = _issue_for_day(db, r["day"])
        hhmm = datetime.fromisoformat(r["scheduled_at"]).astimezone(tz).strftime("%H:%M")
        link = gh.issue_url(n, f"post-{r['seq']}") if n else ""
        msg = f"⏰ まもなく POST {r['seq']}（{hhmm}）。投稿したら URL を Issue にコメント → {link}".strip()
        ok = False
        if notify.channels(settings):
            ok = notify.send(settings, msg, session=session, db=db)
        if not ok and n:
            mention = f"@{settings.ops_mention} " if settings.ops_mention else ""
            gh.comment(n, f"{mention}⏰ まもなく **POST {r['seq']}（{hhmm}）** → [本文](#post-{r['seq']})")
            ok = True
        if ok:
            db.set_setting(f"ops:reminded:{r['post_id']}", utcnow())
            sent += 1
    return sent


# ---------------------------------------------------------------- 要対応 Issue
def sync_attention(db: Database, settings: Settings, gh: GitHub, session: requests.Session | None = None) -> dict:
    attention.ensure_schema(db)
    opened = closed = 0
    for it in attention.open_items(db):
        key = f"ops:attention_issue:{it['id']}"
        if db.get_setting(key):
            continue
        body = "\n".join([f"**カテゴリ**: `{it['category']}`　**重要度**: {it['severity']}", "",
                          f"**やること**: {it['action'] or '-'}", "", "<details><summary>詳細</summary>", "", _fence(it.get("detail") or ""), "</details>", "",
                          "対応したらこの Issue を Close してください（Attention Queue も自動で解決になります）。"])
        res = gh.create_issue(f"⚠️ 要対応: {it['title']}"[:240], body, [LABEL_ATTENTION, f"attention:{it['category']}"])
        db.set_setting(key, res["number"])
        db.set_setting(f"ops:attention_item:{res['number']}", it["id"])
        db.exec("UPDATE attention_queue SET notified_at=? WHERE id=?", (utcnow(), it["id"]))
        opened += 1
        if it["severity"] == "critical" and notify.channels(settings):
            notify.send(settings, f"🚨 要対応（重大）: {it['category']} → {gh.issue_url(res['number'])}", session=session, db=db)
    for r in db.q("SELECT id FROM attention_queue WHERE status='resolved'"):
        key = f"ops:attention_issue:{r['id']}"
        n = db.get_setting(key)
        if n and not db.get_setting(f"ops:attention_closed:{r['id']}"):
            gh.update_issue(int(n), state="closed")
            db.set_setting(f"ops:attention_closed:{r['id']}", "1")
            closed += 1
    return {"opened": opened, "closed": closed}


def issue_closed(db: Database, number: int) -> bool:
    v = db.get_setting(f"ops:attention_item:{number}")
    if not v:
        return False
    attention.resolve(db, int(v))
    db.set_setting(f"ops:attention_closed:{v}", "1")
    return True


# ---------------------------------------------------------------- 受信箱（CSV アップロード）
def ingest_inbox(db: Database, settings: Settings, directory: Path) -> list[tuple[Path, str]]:
    """inbox/ に置かれた CSV を種類判定して取り込む。返り値: (ファイル, 結果)。取込済みファイルは呼び出し側で削除する。"""
    out = []
    for f in sorted(directory.glob("*.csv")):
        try:
            text = f.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            text = f.read_text(encoding="cp932")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        head = lines[0].lower() if lines else ""
        try:
            if "views" in head and ("x_post_id" in head or "post_id" in head or "tweet" in head):
                kind, n = "指標 CSV", metrics.ingest_metrics_csv(db, text)
            else:
                kind, n = "成果 CSV", metrics.ingest_conversions_csv(db, settings, text)
            if n == 0 and len(lines) > 1:
                raise ValueError(f"{kind}として読めた行が 0 件（列名が想定と違う可能性）: {lines[0][:120]}")
            out.append((f, f"{kind}: {n} 件"))
        except Exception as e:  # noqa: BLE001
            attention.raise_item(db, "csv_ingest_failed", f"CSV 取込失敗: {f.name}", detail=f"{e.__class__.__name__}: {str(e)[:300]}",
                                 action="CSV の列名（日時/商品ID/報酬/注文ID）を確認し、inbox/ に再アップロード")
            out.append((f, f"失敗: {e.__class__.__name__}"))
    if out and not any(r.startswith("失敗") for _, r in out):
        attention.resolve_by_category(db, "csv_ingest_failed")
    return out


# ---------------------------------------------------------------- ダイジェスト
def digest_text(db: Database, settings: Settings, gh: GitHub, day: str) -> str:
    from .planner import today_packages
    from .reports import summarize_day
    pk = today_packages(db, settings, day)
    y = summarize_day(db, settings)
    n = _issue_for_day(db, day)
    open_att = len(attention.open_items(db))
    times = " / ".join(p["scheduled_local"] for p in pk) or "なし"
    lines = [f"🗓 {day[5:].replace('-', '/')} 投稿セット {len(pk)} 件：{times}",
             f"昨日：投稿 {y['posts']} 件・Views {y['views']:,}・成果 ¥{y['revenue_jpy']:,.0f}・利益 ¥{y['profit_jpy']:,.0f}",
             f"要対応：{open_att} 件" + ("（Issue を確認）" if open_att else "（なし・自律運用中）")]
    if n:
        lines.append(f"→ {gh.issue_url(n)}")
    return "\n".join(lines)
