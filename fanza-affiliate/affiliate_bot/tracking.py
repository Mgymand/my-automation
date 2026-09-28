"""投稿単位のトラッキング。

2 つのモード:
- stateless（推奨・自動構築対象）: リンクに「トラッキングコード＋遷移先」を HMAC 署名付きで埋め込み、
  Vercel の関数や Cloud Run が DB なしでリダイレクトする。クリック時刻は X の url_link_clicks の差分から推定する
  （metrics.ingest_x_metrics）。X 上では URL 長に関係なく 23 文字扱い。
- db: 自前サーバーが SQLite を参照して /r/<code> をリダイレクトし、クリックを記録する（同一コンテナ運用向け）。
どちらも無ければアフィリエイト URL を直接貼る（X の投稿単位 url_link_clicks は取れる）。

DMM のアフィリエイト ID 末尾（-001〜-999）はアカウント単位のチャネル ID として併用できるが、投稿単位の粒度は無い。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from .config import Settings
from .db import Database, utcnow


def new_code() -> str:
    return secrets.token_urlsafe(6).replace("-", "a").replace("_", "b")[:8]


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def tracking_mode(settings: Settings) -> str:
    if settings.tracking_base_url and settings.tracking_secret:
        return "stateless"
    if settings.tracking_base_url:
        return "db"
    return "none"


# ---- 署名付きペイロード（stateless）----
def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign_payload(secret: str, code: str, url: str) -> str:
    payload = _b64e(json.dumps({"c": code, "u": url}, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{payload}.{sig}"


def verify_payload(secret: str, token: str) -> tuple[str, str] | None:
    """(code, url) を返す。署名不一致・不正なら None。"""
    if "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    expect = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        d = json.loads(_b64d(payload))
        url = str(d["u"])
        if not url.startswith("https://"):
            return None
        return str(d["c"]), url
    except (ValueError, KeyError, TypeError):
        return None


def build_link(settings: Settings, code: str, affiliate_url: str) -> str:
    mode = tracking_mode(settings)
    base = settings.tracking_base_url.rstrip("/")
    if mode == "stateless":
        return f"{base}/r/{sign_payload(settings.tracking_secret, code, affiliate_url)}"
    if mode == "db":
        return f"{base}/r/{code}"
    return affiliate_url


def tracking_url(settings: Settings, code: str) -> str:  # 後方互換
    return f"{settings.tracking_base_url.rstrip('/')}/r/{code}"


# ---- DB 参照（db モード）----
def resolve(db: Database, code: str) -> str | None:
    row = db.one(
        "SELECT pr.affiliate_url FROM posts p JOIN products pr ON pr.content_id=p.product_id WHERE p.tracking_code=?",
        (code,),
    )
    return row["affiliate_url"] if row else None


def record_click(db: Database, code: str, ua: str, referer: str) -> None:
    ua_hash = hashlib.sha256(ua.encode()).hexdigest()[:16] if ua else None
    db.exec("INSERT INTO clicks(tracking_code,ts,ua_hash,referer) VALUES(?,?,?,?)", (code, utcnow(), ua_hash, referer[:200]))


def attribute_conversion(db: Database, product_id: str | None, ts: datetime, window_hours: int) -> tuple[int | None, str]:
    """成果を投稿へ帰属。同一商品の直近クリックがあれば last_click、なければ unattributed。"""
    start = (ts - timedelta(hours=window_hours)).isoformat(timespec="seconds")
    end = ts.isoformat(timespec="seconds")
    if product_id:
        row = db.one(
            """SELECT p.post_id FROM clicks c JOIN posts p ON p.tracking_code=c.tracking_code
               WHERE p.product_id=? AND c.ts BETWEEN ? AND ? ORDER BY c.ts DESC LIMIT 1""",
            (product_id, start, end),
        )
        if row:
            return int(row["post_id"]), "last_click"
    row = db.one(
        """SELECT p.post_id FROM clicks c JOIN posts p ON p.tracking_code=c.tracking_code
           WHERE c.ts BETWEEN ? AND ? ORDER BY c.ts DESC LIMIT 1""",
        (start, end),
    )
    if row:
        return int(row["post_id"]), "last_click_any"
    return None, "unattributed"


# ---- HTTP サーバー（db / stateless の両方に対応）----
class _Handler(BaseHTTPRequestHandler):
    db: Database | None = None
    secret: str = ""

    def log_message(self, *a):  # 静かに
        pass

    def _redirect(self, url: str) -> None:
        self.send_response(302)
        self.send_header("Location", url)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        path = u.path
        if path == "/healthz":
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok"); return
        if path.startswith("/r/"):
            token = path[3:].split("/")[0]
            if self.secret and "." in token:
                v = verify_payload(self.secret, token)
                if not v:
                    self.send_response(404); self.end_headers(); return
                code, url = v
                if self.db is not None:
                    record_click(self.db, code, self.headers.get("User-Agent", ""), self.headers.get("Referer", ""))
                self._redirect(url)
                return
            if self.db is not None:
                url = resolve(self.db, token)
                if url:
                    record_click(self.db, token, self.headers.get("User-Agent", ""), self.headers.get("Referer", ""))
                    self._redirect(url)
                    return
        self.send_response(404); self.end_headers()


def serve(settings: Settings, db: Database | None) -> None:
    _Handler.db = db
    _Handler.secret = settings.tracking_secret
    port = int(os.environ.get("PORT", settings.tracking_port))
    srv = HTTPServer(("0.0.0.0", port), _Handler)
    print(f"tracking server on :{port} (mode={tracking_mode(settings)})")
    srv.serve_forever()
