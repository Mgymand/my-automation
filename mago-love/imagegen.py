"""キャラクター表情画像の生成（画像生成AI）。

優先順位:
  1. Vertex AI（Cloud Run 上ではサービスアカウントの認証情報を自動利用。追加ライブラリ不要）
     必要: aiplatform.googleapis.com の有効化 + 実行SAに roles/aiplatform.user
  2. Gemini API キー（環境変数 GEMINI_API_KEY。ローカル開発や Vertex を使わない場合）
モデル: 環境変数 IMAGE_MODEL（既定 gemini-2.5-flash-image）。元画像＋指示から同一キャラの別表情を生成する。
料金はプロジェクト側で発生（1枚あたり数円程度）。
"""
from __future__ import annotations

import base64
import json
import os
import ssl
import urllib.error
import urllib.request

_CTX = ssl.create_default_context()
MODEL = os.environ.get("IMAGE_MODEL", "gemini-2.5-flash-image")
LOCATION = os.environ.get("VERTEX_LOCATION", "global")


def _metadata(path: str) -> str | None:
    try:
        req = urllib.request.Request("http://metadata.google.internal/computeMetadata/v1/" + path,
                                     headers={"Metadata-Flavor": "Google"})
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.read().decode()
    except Exception:  # noqa: BLE001
        return None


def _project() -> str | None:
    return os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT") or _metadata("project/project-id")


def _token() -> str | None:
    raw = _metadata("instance/service-accounts/default/token")
    if not raw:
        return None
    try:
        return json.loads(raw).get("access_token")
    except ValueError:
        return None


def status() -> dict:
    proj = _project()
    tok = bool(_token()) if proj else False
    key = bool(os.environ.get("GEMINI_API_KEY"))
    return {"vertex": bool(proj and tok), "project": proj, "gemini_api_key": key, "model": MODEL,
            "available": bool((proj and tok) or key)}


def _mime(raw: bytes) -> str:
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _call(body: dict) -> dict:
    proj = _project()
    tok = _token() if proj else None
    if proj and tok:
        url = (f"https://aiplatform.googleapis.com/v1/projects/{proj}/locations/{LOCATION}"
               f"/publishers/google/models/{MODEL}:generateContent")
        headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    elif os.environ.get("GEMINI_API_KEY"):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={os.environ['GEMINI_API_KEY']}"
        headers = {"Content-Type": "application/json"}
    else:
        raise RuntimeError("画像生成AIが利用できません（Vertex AI 未設定・GEMINI_API_KEY 未設定）")
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120, context=_CTX) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:400]
        if e.code == 403:
            raise RuntimeError("権限がありません。Vertex AI API の有効化と、実行サービスアカウントへの roles/aiplatform.user 付与が必要です（setup-cloudshell.sh を再実行）")
        if e.code == 404:
            raise RuntimeError(f"モデル {MODEL} が見つかりません（IMAGE_MODEL を確認）: {detail}")
        raise RuntimeError(f"HTTP {e.code}: {detail}")


def generate_expression(base_image: bytes, character: dict, expression_prompt: str) -> bytes:
    """元画像と同一キャラの別表情を生成して PNG/JPEG バイト列を返す。"""
    prompt = (
        "This is a character illustration for a Japanese business app. Generate the SAME character: "
        "identical face, hairstyle, animal ears, tail, outfit, accessories, name tag, art style, proportions and colors. "
        "Keep the full-body framing, standing pose, and plain pure-white background. "
        f"Change only the expression and gesture to: {expression_prompt}. "
        f"The character is {character.get('name', '')}, a {character.get('species', '')}-eared {character.get('role', '')}. "
        "No text, no watermark, no speech bubbles, single character, centered, high quality anime illustration."
    )
    body = {
        "contents": [{"role": "user", "parts": [
            {"inlineData": {"mimeType": _mime(base_image), "data": base64.b64encode(base_image).decode()}},
            {"text": prompt},
        ]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"], "temperature": 0.6},
    }
    res = _call(body)
    for cand in res.get("candidates", []):
        for part in (cand.get("content") or {}).get("parts", []):
            data = (part.get("inlineData") or part.get("inline_data") or {})
            if data.get("data") and str(data.get("mimeType", data.get("mime_type", ""))).startswith("image/"):
                return base64.b64decode(data["data"])
    reason = (res.get("candidates") or [{}])[0].get("finishReason") or res.get("promptFeedback", {}).get("blockReason")
    raise RuntimeError(f"画像が返されませんでした（{reason or '理由不明'}）")


def _first_image(res: dict) -> bytes:
    for cand in res.get("candidates", []):
        for part in (cand.get("content") or {}).get("parts", []):
            data = (part.get("inlineData") or part.get("inline_data") or {})
            if data.get("data") and str(data.get("mimeType", data.get("mime_type", ""))).startswith("image/"):
                return base64.b64decode(data["data"])
    reason = (res.get("candidates") or [{}])[0].get("finishReason") or res.get("promptFeedback", {}).get("blockReason")
    raise RuntimeError(f"画像が返されませんでした（{reason or '理由不明'}）")


def still_prompt(character: dict, place: str) -> str:
    """ホール背景にキャラを合成する指示文（アプリ内生成と ChatGPT 用コピーの両方で使う）。"""
    return (
        "Image 1 is a background painting of a fantasy guild hall. Image 2 is a character illustration on a white background. "
        "Create ONE new image: the exact same guild hall from image 1 (same composition, camera angle, furniture, lighting and colors, nothing added or removed), "
        f"with the character from image 2 placed naturally inside it, {place}. "
        "Keep the character's identity exactly: same face, hairstyle, animal ears, outfit and colors. "
        "Match the character's scale to the perspective of the room, match the warm lighting and cast a soft shadow on the floor so the character looks like they belong there. "
        f"The character is {character.get('name', '')}, a {character.get('species', '')}-eared {character.get('role', '')}. "
        "Single character only, no other people, no text, no speech bubbles, no watermark. Painterly anime style consistent with the background. Aspect ratio 16:9."
    )


def generate_still(background: bytes, character_image: bytes, character: dict, place: str) -> bytes:
    """背景画像（ホール）に、キャラクターを指定の場所へ違和感なく合成した 16:9 の場面画像を生成する。"""
    body = {
        "contents": [{"role": "user", "parts": [
            {"inlineData": {"mimeType": _mime(background), "data": base64.b64encode(background).decode()}},
            {"inlineData": {"mimeType": _mime(character_image), "data": base64.b64encode(character_image).decode()}},
            {"text": still_prompt(character, place)},
        ]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"], "temperature": 0.5},
    }
    return _first_image(_call(body))


def generate_image(prompt: str, aspect: str = "16:9") -> bytes:
    """テキスト指示だけから画像を生成（背景・UI素材用）。"""
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt + f" Aspect ratio {aspect}."}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"], "temperature": 0.8},
    }
    res = _call(body)
    for cand in res.get("candidates", []):
        for part in (cand.get("content") or {}).get("parts", []):
            data = (part.get("inlineData") or part.get("inline_data") or {})
            if data.get("data") and str(data.get("mimeType", data.get("mime_type", ""))).startswith("image/"):
                return base64.b64decode(data["data"])
    reason = (res.get("candidates") or [{}])[0].get("finishReason") or res.get("promptFeedback", {}).get("blockReason")
    raise RuntimeError(f"画像が返されませんでした（{reason or '理由不明'}）")
