"""認証・権限（孫LOVE）

役割:
  admin  : 全設定・ユーザー管理・全データ編集
  member : 物件・タスク・報告の閲覧と編集
  viewer : 閲覧のみ

ログイン方式:
  1. Googleログイン: GOOGLE_CLIENT_ID がある場合、Google Identity Services の
     IDトークンを tokeninfo で検証。users.json に登録済みメールのみ（招待制）。
  2. 開発用ログイン: GOOGLE_CLIENT_ID 未設定時のみ、登録ユーザーを選択してログイン。
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

import store

ROLE_LEVEL = {"viewer": 1, "member": 2, "admin": 3}
ROLE_LABEL = {"viewer": "閲覧", "member": "メンバー", "admin": "管理者"}
_SSL_CTX = ssl.create_default_context()


def load_users() -> list[dict]:
    return store.load("users", [])


def save_users(users: list[dict]):
    store.save("users", users)


def find_user(email: str) -> dict | None:
    email = (email or "").strip().lower()
    for u in load_users():
        if u.get("email", "").lower() == email and u.get("active", True):
            return u
    return None


def bootstrap_admin():
    """初回起動時に ADMIN_EMAIL を管理者として登録（既にユーザーがいれば何もしない）。"""
    admin = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    if not admin or load_users():
        return
    save_users([{"email": admin, "name": "管理者", "role": "admin",
                 "active": True, "created_at": store.now_iso()}])
    print(f"[bootstrap] 初期管理者を作成しました: {admin}")


def login_user(user: dict):
    session.permanent = True
    session["user"] = {
        "email": user["email"],
        "name": user.get("name", user["email"]),
        "role": user.get("role", "member"),
    }


def logout_user():
    session.pop("user", None)


def current_user() -> dict | None:
    return session.get("user")


def user_level(user: dict | None) -> int:
    return ROLE_LEVEL.get((user or {}).get("role", ""), 0)


def google_enabled() -> bool:
    return bool(os.environ.get("GOOGLE_CLIENT_ID"))


def verify_google_token(credential: str) -> dict:
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    if not client_id:
        raise ValueError("GOOGLE_CLIENT_ID is not configured")
    q = urllib.parse.urlencode({"id_token": credential})
    url = f"https://oauth2.googleapis.com/tokeninfo?{q}"
    try:
        with urllib.request.urlopen(url, timeout=10, context=_SSL_CTX) as resp:
            info = json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"token verification failed: {e}")
    if info.get("aud") != client_id:
        raise ValueError("token audience mismatch")
    if int(info.get("exp", 0)) < time.time():
        raise ValueError("token expired")
    if info.get("email_verified") not in ("true", True):
        raise ValueError("email not verified")
    return {"email": info["email"], "name": info.get("name", info["email"])}


def require_role(min_role: str):
    """ページ/API共用のロールガード。未ログイン: ページ→/login、API→401。権限不足→403。"""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            is_api = request.path.startswith("/api/")
            if not user:
                if is_api:
                    return jsonify({"error": "login required"}), 401
                return redirect(f"/login?next={urllib.parse.quote(request.full_path.rstrip('?'))}")
            if user_level(user) < ROLE_LEVEL[min_role]:
                if is_api:
                    return jsonify({"error": "permission denied"}), 403
                return redirect("/")
            return fn(*args, **kwargs)
        return wrapper
    return decorator
