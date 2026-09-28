"""Vercel Python Function: 署名付きトラッキングリンクのステートレス・リダイレクト。

GET /r/<payload>.<sig>  → 署名検証 → 302 → DMM アフィリエイト URL
GET /healthz            → 200 ok
環境変数: TRACKING_SECRET（affiliate_bot と同じ値）。DB 不要。クリック数は X の url_link_clicks から推定する。
"""
import base64
import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def verify(secret: str, token: str):
    if "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    expect = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        d = json.loads(_b64d(payload))
        url = str(d["u"])
        return url if url.startswith("https://") else None
    except (ValueError, KeyError, TypeError):
        return None


class handler(BaseHTTPRequestHandler):  # noqa: N801 - Vercel の規約
    def do_GET(self):
        u = urlparse(self.path)
        if u.path.endswith("/healthz"):
            self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers(); self.wfile.write(b"ok"); return
        qs = parse_qs(u.query)
        token = (qs.get("p") or [""])[0] or u.path.split("/r/")[-1]
        secret = os.environ.get("TRACKING_SECRET", "")
        url = verify(secret, token) if secret else None
        if not url:
            self.send_response(404); self.end_headers(); return
        self.send_response(302)
        self.send_header("Location", url)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
