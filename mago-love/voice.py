"""キャラクターの声（Google Cloud Text-to-Speech）。

Cloud Run 上ではサービスアカウントで自動認証（texttospeech.googleapis.com の有効化が必要。setup-cloudshell.sh が有効化する）。
無料枠（月100万文字程度）内で十分収まる。利用できない場合はブラウザの読み上げ（speechSynthesis）にフォールバックする。
生成した音声は data/voice/ にキャッシュし、同じセリフは再生成しない。
"""
from __future__ import annotations

import hashlib
import json
import os
import ssl
import urllib.error
import urllib.request

from imagegen import _project, _token

_CTX = ssl.create_default_context()
DEFAULT_VOICE = {"name": "ja-JP-Neural2-B", "pitch": 0.0, "rate": 1.0}


def status() -> dict:
    proj = _project()
    ok = bool(proj and _token())
    return {"available": ok, "project": proj, "engine": "Google Cloud Text-to-Speech" if ok else "browser"}


def cache_key(text: str, voice: dict) -> str:
    return hashlib.sha1(json.dumps([text, voice], ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def synthesize(text: str, voice: dict | None = None) -> bytes:
    """テキストを MP3 に変換して返す。"""
    v = {**DEFAULT_VOICE, **(voice or {})}
    tok = _token()
    if not tok:
        raise RuntimeError("音声合成が利用できません（Cloud Run 以外の環境、または認証情報なし）")
    body = {
        "input": {"text": text[:400]},
        "voice": {"languageCode": "ja-JP", "name": v["name"]},
        "audioConfig": {"audioEncoding": "MP3", "pitch": v.get("pitch", 0.0), "speakingRate": v.get("rate", 1.0)},
    }
    req = urllib.request.Request("https://texttospeech.googleapis.com/v1/text:synthesize",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30, context=_CTX) as r:
            res = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        if e.code == 403:
            raise RuntimeError("Text-to-Speech API が有効化されていません（setup-cloudshell.sh を再実行）")
        raise RuntimeError(f"HTTP {e.code}: {detail}")
    import base64
    return base64.b64decode(res["audioContent"])
