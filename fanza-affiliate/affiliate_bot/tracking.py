"""投稿単位のトラッキング。

X → 自前リダイレクト（/r/<code>）→ DMM アフィリエイト URL。
クリックは clicks テーブルに記録し、DMM の成果 CSV を取り込んだ際に
「同一商品への直近クリック（Attribution window 内）」でポスト単位に帰属させる。
DMM のアフィリエイト ID 末尾（-001〜-999）はチャネル ID として併用できるが、
投稿単位の粒度は自前リダイレクトでしか得られない。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from .config import Settings
from .db import Database, utcnow


def new_code() -> str:
    return secrets.token_urlsafe(6).replace("-", "a").replace("_", "b")[:8]


def tracking_url(settings: Settings, code: str) -> str:
    base = settings.tracking_base_url.rstrip("/")
    return f"{base}/r/{code}"


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


class _Handler(BaseHTTPRequestHandler):
    db: Database = None  # type: ignore
    secret: str = ""

    def log_message(self, *a):  # 静かに
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/healthz":
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok"); return
        if path.startswith("/r/"):
            code = path[3:].split("/")[0]
            url = resolve(self.db, code)
            if not url:
                self.send_response(404); self.end_headers(); return
            record_click(self.db, code, self.headers.get("User-Agent", ""), self.headers.get("Referer", ""))
            self.send_response(302)
            self.send_header("Location", url)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.send_response(404); self.end_headers()


def serve(settings: Settings, db: Database) -> None:
    _Handler.db = db
    srv = HTTPServer(("0.0.0.0", settings.tracking_port), _Handler)
    print(f"tracking server on :{settings.tracking_port}")
    srv.serve_forever()
