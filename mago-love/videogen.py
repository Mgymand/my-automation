"""動画クリップの生成（Veo: 画像 → 数秒の動画）。

場面画像（キャラがホールにいる静止画）を最初のフレームとして、
  idle: その場で呼吸し、視線を動かし、ろうそくの光が揺れる「待機ループ」
  talk: カメラが寄り、キャラが正面を向いて話しかけてくる「会話クリップ」
を生成する。ギルドホールを本当に「生きている」場所にするための素材。

優先順位:
  1. Vertex AI（Cloud Run 上ではサービスアカウントで自動認証。aiplatform.googleapis.com 有効化 + roles/aiplatform.user）
  2. Gemini API キー（環境変数 GEMINI_API_KEY）
モデル: 環境変数 VIDEO_MODEL（既定 veo-3.0-fast-generate-001）。料金は1本（8秒）あたり百数十円〜数百円程度で、
プロジェクト側に課金される。生成には1〜3分かかるため、サーバー側でバックグラウンド実行し、進捗をポーリングする。
"""
from __future__ import annotations

import base64
import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.request

from imagegen import _mime, _project, _token

_CTX = ssl.create_default_context()
MODEL = os.environ.get("VIDEO_MODEL", "veo-3.0-fast-generate-001")
LOCATION = os.environ.get("VEO_LOCATION", "us-central1")
DURATION = int(os.environ.get("VIDEO_SECONDS", "8"))

IDLE_PROMPT = (
    "Cinematic idle loop of the same scene. The character stays in place and {place}, breathing softly, "
    "shifting weight slightly, blinking and glancing around the room naturally. Candle light flickers, dust motes drift in the sunbeams. "
    "The camera holds almost still with a very slow, subtle drift. No speech, no text, no captions, no new people. "
    "The final frame should closely match the first frame so the clip can loop seamlessly. Painterly anime style consistent with the image."
)
TALK_PROMPT = (
    "The camera slowly pushes in toward the character. The character notices the viewer, turns to face the camera, "
    "smiles warmly and starts talking with natural, lively gestures and clear mouth movement, like a friendly guild member greeting a visitor. "
    "Warm lighting, shallow depth of field on the background. No text, no captions, no new people. Painterly anime style consistent with the image."
)


def status() -> dict:
    proj = _project()
    tok = bool(_token()) if proj else False
    key = bool(os.environ.get("GEMINI_API_KEY"))
    return {"vertex": bool(proj and tok), "project": proj, "gemini_api_key": key, "model": MODEL,
            "seconds": DURATION, "available": bool((proj and tok) or key)}


def _http(url: str, body: dict | None, headers: dict, method: str = "POST") -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120, context=_CTX) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:400]
        if e.code == 403:
            raise RuntimeError("権限がありません。Vertex AI API の有効化と、実行サービスアカウントへの roles/aiplatform.user 付与が必要です（setup-cloudshell.sh を再実行）")
        if e.code == 404:
            raise RuntimeError(f"モデル {MODEL} が見つかりません（VIDEO_MODEL を確認）: {detail}")
        raise RuntimeError(f"HTTP {e.code}: {detail}")


def _endpoint() -> tuple[str, dict, str]:
    """(ベースURL, ヘッダ, 種別) を返す。"""
    proj = _project()
    tok = _token() if proj else None
    if proj and tok:
        base = (f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{proj}/locations/{LOCATION}"
                f"/publishers/google/models/{MODEL}")
        return base, {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}, "vertex"
    if os.environ.get("GEMINI_API_KEY"):
        base = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}"
        return base, {"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"]}, "gemini"
    raise RuntimeError("動画生成AIが利用できません（Vertex AI 未設定・GEMINI_API_KEY 未設定）")


def generate_clip(start_image: bytes, prompt: str, on_progress=None) -> bytes:
    """画像を最初のフレームにして動画を生成し、MP4 のバイト列を返す（完了まで最大 8 分待つ）。"""
    base, headers, kind = _endpoint()
    body = {
        "instances": [{"prompt": prompt, "image": {"bytesBase64Encoded": base64.b64encode(start_image).decode(), "mimeType": _mime(start_image)}}],
        "parameters": {"aspectRatio": "16:9", "durationSeconds": DURATION, "sampleCount": 1, "resolution": "720p",
                       "generateAudio": False, "personGeneration": "allow_adult"},
    }
    op = _http(f"{base}:predictLongRunning", body, headers)
    name = op.get("name")
    if not name:
        raise RuntimeError(f"生成を開始できませんでした: {json.dumps(op)[:300]}")
    deadline = time.time() + 8 * 60
    while time.time() < deadline:
        time.sleep(6)
        if kind == "vertex":
            res = _http(f"{base}:fetchPredictOperation", {"operationName": name}, headers)
        else:
            res = _http(f"https://generativelanguage.googleapis.com/v1beta/{name}", None, headers, method="GET")
        if on_progress:
            on_progress()
        if not res.get("done"):
            continue
        if res.get("error"):
            raise RuntimeError(f"生成エラー: {res['error'].get('message', res['error'])}")
        resp = res.get("response") or {}
        vids = resp.get("videos") or []
        if vids and vids[0].get("bytesBase64Encoded"):
            return base64.b64decode(vids[0]["bytesBase64Encoded"])
        # Gemini API 形式
        samples = ((resp.get("generateVideoResponse") or {}).get("generatedSamples")) or []
        if samples and (samples[0].get("video") or {}).get("uri"):
            uri = samples[0]["video"]["uri"]
            req = urllib.request.Request(uri, headers={"x-goog-api-key": os.environ.get("GEMINI_API_KEY", "")})
            with urllib.request.urlopen(req, timeout=120, context=_CTX) as r:
                return r.read()
        filtered = resp.get("raiMediaFilteredCount") or resp.get("raiMediaFilteredReasons")
        raise RuntimeError(f"動画が返されませんでした（安全フィルタ等: {filtered or '理由不明'}）")
    raise RuntimeError("生成がタイムアウトしました（8分）。時間をおいて再試行してください")


# ---- バックグラウンドジョブ（1つずつ順番に実行） -------------------------------
_jobs: dict[str, dict] = {}
_lock = threading.Lock()
_worker: threading.Thread | None = None


def _run_queue(fn_map):
    global _worker
    while True:
        with _lock:
            job = next((j for j in _jobs.values() if j["status"] == "queued"), None)
            if not job:
                _worker = None
                return
            job["status"] = "running"; job["started"] = time.time()
        try:
            fn_map(job)
            job["status"] = "done"
        except Exception as e:  # noqa: BLE001
            job["status"] = "error"; job["error"] = str(e)
            print(f"[videogen] {job['id']}: {e}")
        job["finished"] = time.time()


def enqueue(job_id: str, meta: dict, runner) -> dict:
    """同じ ID の実行中ジョブがあればそれを返す。runner(job) が本体。"""
    global _worker
    with _lock:
        cur = _jobs.get(job_id)
        if cur and cur["status"] in ("queued", "running"):
            return cur
        job = {"id": job_id, "status": "queued", "created": time.time(), **meta}
        _jobs[job_id] = job
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_run_queue, args=(runner,), daemon=True)
            _worker.start()
    return job


def jobs() -> list[dict]:
    with _lock:
        out = sorted(_jobs.values(), key=lambda j: j["created"], reverse=True)[:40]
        return [{k: v for k, v in j.items()} for j in out]
