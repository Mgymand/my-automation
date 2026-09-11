"""Slack通知（Incoming Webhook・無料）。

設定: settings.json の slack_webhook_url（画面から設定）または環境変数 SLACK_WEBHOOK_URL。
通知イベント: 物件登録 / ステータス変更 / 内見・現調報告 / 期限リマインド（日次ダイジェスト）。
"""
from __future__ import annotations

import json
import os
import ssl
import threading
import urllib.request

import store

_CTX = ssl.create_default_context()


def settings() -> dict:
    return store.load("settings", {})


def webhook_url() -> str:
    return (settings().get("slack_webhook_url") or os.environ.get("SLACK_WEBHOOK_URL") or "").strip()


def post(text: str, blocks: list | None = None, sync: bool = False) -> bool:
    """Slackへ投稿。Webhook未設定なら False（アプリの動作は止めない）。"""
    url = webhook_url()
    if not url:
        return False
    payload = {"text": text}
    if blocks:
        payload["blocks"] = blocks

    def _send():
        try:
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=10, context=_CTX) as r:
                return r.status == 200
        except Exception as e:  # noqa: BLE001
            print(f"[slack] failed: {e}")
            return False

    if sync:
        return _send()
    threading.Thread(target=_send, daemon=True).start()
    return True


def app_url() -> str:
    return (settings().get("app_url") or os.environ.get("APP_URL") or "").rstrip("/")


def prop_link(p: dict) -> str:
    base = app_url()
    name = p.get("name") or "(名称未設定)"
    return f"<{base}/#/property/{p['id']}|{name}>" if base else name


def notify_property_created(p: dict, by: str):
    if not settings().get("notify_on_create", True):
        return
    post(f":new: 物件登録: {prop_link(p)}（{p.get('pref','')}{p.get('city','')}） by {by}")


def notify_status_changed(p: dict, old: str, new: str, by: str, label: dict):
    if not settings().get("notify_on_status", True):
        return
    post(f":arrow_right: ステータス変更: {prop_link(p)}  {label.get(old, old)} → *{label.get(new, new)}*  by {by}")


def notify_report(p: dict, rep: dict, by: str):
    if not settings().get("notify_on_report", True):
        return
    kind = {"viewing": "内見報告", "survey": "現調報告"}.get(rep.get("type"), "報告")
    stars = "★" * int(rep.get("rating") or 0)
    text = (f":clipboard: {kind}: {prop_link(p)}  {stars}\n"
            f"> {rep.get('summary','')[:300]}")
    post(text)


def notify_schedule(p: dict, field_label: str, date: str, by: str):
    if not settings().get("notify_on_schedule", True):
        return
    post(f":calendar: 予定更新: {prop_link(p)}  {field_label}: *{date}*  by {by}")


def digest(lines_overdue: list[str], lines_soon: list[str], lines_events: list[str]) -> bool:
    if not (lines_overdue or lines_soon or lines_events):
        return False
    parts = [":sunrise: *孫LOVE 本日のリマインド*"]
    if lines_overdue:
        parts.append("*期限超過タスク*\n" + "\n".join(f"• {l}" for l in lines_overdue[:15]))
    if lines_soon:
        parts.append("*7日以内のタスク*\n" + "\n".join(f"• {l}" for l in lines_soon[:15]))
    if lines_events:
        parts.append("*今後14日の予定*\n" + "\n".join(f"• {l}" for l in lines_events[:15]))
    return post("\n\n".join(parts), sync=True)
