"""認証・権限レイヤ (Phase1.5)

役割階層（上位は下位の権限を全て含む）:
  ogn   : オーガナイズ画面（最上位）。ユーザー・加盟店の管理、全データ閲覧。
  admin : 管理画面。マネージャーダッシュボードで全店舗を横断閲覧。
  store : 加盟店画面。自店(store_id)のデータのみ操作・編集可能。

ログイン方式:
  1. Googleログイン: .env に GOOGLE_CLIENT_ID がある場合、Google Identity Services の
     IDトークンを受け取り、tokeninfo エンドポイントで検証（aud一致・期限内）。
     users.json に登録済みのメールのみログイン可（招待制）。
  2. 開発用ログイン: GOOGLE_CLIENT_ID 未設定時のみ、users.json のユーザーを
     選択してログインできる（本番では必ず無効化される）。
"""
from __future__ import annotations

import json
import os
import ssl
import time
import urllib.parse
import urllib.request
from functools import wraps

from flask import jsonify, redirect, request, session

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 本番では永続ディスクを PROPERTY_DATA_DIR で指定（app.py と同一規約）
DATA_DIR = os.environ.get("PROPERTY_DATA_DIR") or os.path.join(BASE_DIR, "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
STORES_FILE = os.path.join(DATA_DIR, "stores.json")

ROLE_LEVEL = {"store": 1, "admin": 2, "ogn": 3}
ROLE_LABEL = {"store": "加盟店", "admin": "管理", "ogn": "オーガナイズ"}
ROLE_HOME = {"store": "/portal", "admin": "/admin", "ogn": "/ogn"}

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


# ---------------------------------------------------------------------------
# ユーザー・店舗ストア
# ---------------------------------------------------------------------------

def _load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(path, items):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def load_users() -> list[dict]:
    return _load(USERS_FILE, [])


def save_users(users: list[dict]):
    _save(USERS_FILE, users)


def load_stores() -> list[dict]:
    return _load(STORES_FILE, [])


def save_stores(stores: list[dict]):
    _save(STORES_FILE, stores)


def find_user(email: str) -> dict | None:
    email = (email or "").strip().lower()
    for u in load_users():
        if u.get("email", "").lower() == email and u.get("active", True):
            return u
    return None


# ---------------------------------------------------------------------------
# セッション
# ---------------------------------------------------------------------------

def login_user(user: dict):
    session["user"] = {
        "email": user["email"],
        "name": user.get("name", user["email"]),
        "role": user.get("role", "store"),
        "store_id": user.get("store_id"),
    }


def logout_user():
    session.pop("user", None)


def current_user() -> dict | None:
    return session.get("user")


def user_level(user: dict | None) -> int:
    return ROLE_LEVEL.get((user or {}).get("role", ""), 0)


def google_enabled() -> bool:
    return bool(os.environ.get("GOOGLE_CLIENT_ID"))


# ---------------------------------------------------------------------------
# Google IDトークン検証
# ---------------------------------------------------------------------------

def verify_google_token(credential: str) -> dict:
    """Google Identity Services のIDトークンを検証し、{email, name} を返す。

    署名検証はGoogleの tokeninfo エンドポイントに委譲（依存パッケージ不要）。
    失敗時は ValueError。
    """
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    if not client_id:
        raise ValueError("GOOGLE_CLIENT_ID is not configured")
    q = urllib.parse.urlencode({"id_token": credential})
    url = f"https://oauth2.googleapis.com/tokeninfo?{q}"
    try:
        with urllib.request.urlopen(url, timeout=10, context=_SSL_CTX) as resp:
            info = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise ValueError(f"token verification failed: {e}")
    if info.get("aud") != client_id:
        raise ValueError("token audience mismatch")
    if int(info.get("exp", 0)) < time.time():
        raise ValueError("token expired")
    if info.get("email_verified") not in ("true", True):
        raise ValueError("email not verified")
    return {"email": info["email"], "name": info.get("name", info["email"])}


# ---------------------------------------------------------------------------
# ルートガード
# ---------------------------------------------------------------------------

def require_role(min_role: str):
    """ページ/API共用のロールガード。

    未ログイン: ページ→/loginへリダイレクト、API→401 JSON。
    権限不足:   403。
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            is_api = request.path.startswith("/api/")
            if not user:
                if is_api:
                    return jsonify({"error": "login required"}), 401
                return redirect(f"/login?next={urllib.parse.quote(request.path)}")
            if user_level(user) < ROLE_LEVEL[min_role]:
                if is_api:
                    return jsonify({"error": "permission denied"}), 403
                return redirect(ROLE_HOME.get(user["role"], "/login"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def scope_store_id(requested: str | None = None) -> str | None:
    """データ絞り込みに使う店舗ID。

    加盟店(store)ロール: 常に自店IDを強制（リクエスト値は無視＝改ざん防止）。
    admin/ogn: requested があればその店舗、なければ None（=全店舗）。
    """
    user = current_user() or {}
    if user.get("role") == "store":
        return user.get("store_id")
    return requested or None
