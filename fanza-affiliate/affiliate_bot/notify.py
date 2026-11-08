"""プッシュ通知（Discord / Slack の Incoming Webhook。どちらも無料）。

- 通知には成人向けの本文・画像を載せない（時刻・件数・KPI・運用 Issue へのリンクだけ）。
  商品名や素材は private の運用リポジトリの Issue に置き、通知はそこへ誘導する
- Discord はリンクの埋め込み展開を止める（flags=4 SUPPRESS_EMBEDS）、@everyone 等のメンションは無効化
- Slack はリンク / メディアの展開を止める
- どれか 1 つでも配送できたら True
"""
from __future__ import annotations

import requests

from .config import Settings

DISCORD_LIMIT = 1900


def channels(settings: Settings) -> list[str]:
    return [n for n, url in (("discord", settings.discord_webhook_url), ("slack", settings.slack_webhook_url)) if url]


def _chunks(text: str, limit: int) -> list[str]:
    out, cur = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            out.append(line[:limit]); line = line[limit:]
        if len(cur) + len(line) > limit:
            out.append(cur); cur = ""
        cur += line
    if cur:
        out.append(cur)
    return out or [""]


def send(settings: Settings, text: str, session: requests.Session | None = None, db=None) -> bool:
    s = session or requests.Session()
    delivered = False
    if settings.discord_webhook_url:
        ok = True
        for part in _chunks(text, DISCORD_LIMIT):
            try:
                r = s.post(settings.discord_webhook_url, json={"content": part, "flags": 4, "allowed_mentions": {"parse": []}}, timeout=15)
                ok = ok and r.status_code < 300
            except requests.RequestException:
                ok = False
        if not ok and db is not None:
            db.log_event("warn", "notify_failed", "Discord への送信に失敗（次回再送）")
        delivered = delivered or ok
    if settings.slack_webhook_url:
        try:
            r = s.post(settings.slack_webhook_url, json={"text": text, "unfurl_links": False, "unfurl_media": False}, timeout=15)
            ok = r.status_code < 300
            if not ok and db is not None:
                db.log_event("warn", "notify_failed", f"Slack HTTP {r.status_code}（次回再送）")
        except requests.RequestException as e:
            ok = False
            if db is not None:
                db.log_event("warn", "notify_failed", f"Slack {e.__class__.__name__}（次回再送）")
        delivered = delivered or ok
    return delivered
