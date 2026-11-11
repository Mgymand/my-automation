"""スマホ向け簡易 Web UI（標準ライブラリのみ）。

トップ: 「今日の投稿」だけを大きく表示。各投稿に 投稿時刻 / 商品画像 / 商品名 / 本文 / 素材 / Affiliate URL / コピー / 投稿済み。
別タブ: 分析（昨日の実績・調整・Attention・パターン）。
投稿済みボタンは X の投稿 URL を受け取り posted.register を呼ぶ（X への投稿は人間がアプリで行う）。
"""
from __future__ import annotations

import html
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from . import attention, posted
from .config import Settings
from .db import Database, loads
from .planner import today_packages

CSS = """
body{font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans",sans-serif;margin:0;background:#f5f5f7;color:#111}
nav{display:flex;background:#111;color:#fff} nav a{flex:1;text-align:center;padding:14px;color:#fff;text-decoration:none;font-weight:600}
nav a.on{background:#1d4ed8} main{padding:12px;max-width:720px;margin:0 auto}
.card{background:#fff;border-radius:12px;padding:14px;margin:0 0 14px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.card.done{opacity:.55} .head{display:flex;gap:10px;align-items:baseline} .time{font-size:1.5em;font-weight:700} .seq{color:#666}
.prio{margin-left:auto;font-size:.9em;color:#a00} img,video{width:100%;border-radius:8px;margin:8px 0;max-height:360px;object-fit:cover}
h2{font-size:1.05em;margin:6px 0} .meta{color:#555;font-size:.9em}
pre.body{white-space:pre-wrap;background:#f0f0f4;padding:10px;border-radius:8px;font-family:inherit;font-size:1.05em}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px} button,.btn{flex:1;min-width:110px;text-align:center;padding:12px;border:0;border-radius:8px;background:#1d4ed8;color:#fff;font-size:1em;text-decoration:none}
.btn{background:#374151} .ok{background:#059669} input[type=text]{width:100%;padding:10px;border:1px solid #ccc;border-radius:8px;font-size:1em;box-sizing:border-box}
details{margin-top:8px;font-size:.92em} .schedule{font-size:1.15em;line-height:1.8} .warn{background:#fff7ed;border-left:4px solid #f59e0b;padding:8px;font-size:.9em}
table{width:100%;border-collapse:collapse;font-size:.9em} td,th{padding:6px;border-bottom:1px solid #eee;text-align:left}
"""

JS = """
function copyText(id){const t=document.getElementById(id).innerText;navigator.clipboard.writeText(t).then(()=>{const b=document.getElementById('c'+id);b.textContent='コピー済み';setTimeout(()=>b.textContent='本文をコピー',1500)})}
async function markPosted(day,seq){const url=document.getElementById('url'+seq).value.trim();if(!url){alert('X の投稿 URL を貼ってください');return}
 const r=await fetch('/api/posted',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({day,seq,url})});const j=await r.json();
 if(j.ok){location.reload()}else{alert(j.error)}}
"""


def _page(title: str, body: str, tab: str, token: str) -> str:
    q = f"?t={token}" if token else ""
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style></head><body>
<nav><a href="/{q}" class="{'on' if tab == 'today' else ''}">今日の投稿</a><a href="/analytics{q}" class="{'on' if tab == 'analytics' else ''}">分析</a></nav>
<main>{body}</main><script>{JS}</script></body></html>"""


def render_today(db: Database, settings: Settings, token: str) -> str:
    tz = ZoneInfo(settings.timezone)
    day = datetime.now(tz).strftime("%Y-%m-%d")
    pk = today_packages(db, settings, day)
    if not pk:
        return _page("今日の投稿", f"<div class='card'><h2>{day} の投稿セットはまだありません</h2><p><code>python -m affiliate_bot plan</code> を実行してください。</p></div>", "today", token)
    sched = "<br>".join(f"{p['scheduled_local']} POST {p['seq']}" + ("　✅" if p["status"] == "posted" else "") for p in pk)
    cards = [f"<div class='card schedule'><b>{day}</b><br>{sched}</div>"]
    for p in pk:
        pred = p.get("predicted") or {}
        media = ""
        if p.get("media_type") == "image" and p.get("media_source"):
            media = f'<img src="{html.escape(p["media_source"])}" alt="" loading="lazy">'
        elif p.get("media_type") == "video" and p.get("media_source"):
            media = f'<video src="{html.escape(p["media_source"])}" controls muted playsinline></video>'
        elif p.get("image_url"):
            media = f'<img src="{html.escape(p["image_url"])}" alt="" loading="lazy">'
        done = p["status"] == "posted"
        posted_row = "" if done else (f'<div class="row"><input type="text" id="url{p["seq"]}" placeholder="投稿した X の URL を貼る">'
                                      f'<button class="ok" onclick="markPosted(&quot;{day}&quot;,{p["seq"]})">投稿済み</button></div>')
        cards.append(f"""
<section class="card {'done' if done else ''}" id="post{p['seq']}">
 <div class="head"><span class="time">{p['scheduled_local']}</span><span class="seq">POST {p['seq']}</span><span class="prio">{'投稿済み' if done else '優先度 ' + html.escape(str(p.get('priority') or ''))}</span></div>
 {media}
 <h2>{html.escape(p['title'])}</h2>
 <div class="meta">{html.escape('・'.join(p.get('actresses') or []) or '-')} / {html.escape('・'.join((p.get('genres') or [])[:3]))} / {int(p['price']):,}円{('（' + str(int(float(p['discount_rate']) * 100)) + '%OFF）') if p.get('discount_rate') else ''}</div>
 <pre class="body" id="t{p['seq']}">{html.escape(p['text'])}</pre>
 <div class="row"><button id="ct{p['seq']}" onclick="copyText('t{p['seq']}')">本文をコピー</button>
  {f'<a class="btn" href="{html.escape(p["media_source"])}" target="_blank" rel="noopener">素材（{"動画" if p["media_type"] == "video" else "画像"}）</a>' if p.get('media_source') else ''}
  <a class="btn" href="{html.escape(p.get('affiliate_url') or '#')}" target="_blank" rel="noopener">Affiliate URL</a></div>
 {posted_row}
 <details><summary>理由・期待値・注意・代替案</summary>
  <p><b>理由:</b> {html.escape(p.get('reason') or '')}</p>
  <p><b>期待値:</b> Views {pred.get('views','-')} / CTR {pred.get('ctr','-')} / CVR {pred.get('cvr','-')} / 売上 {pred.get('revenue','-')}円</p>
  <p><b>類似成功投稿:</b> {html.escape(str(p.get('similar_post_id') or '-'))} {html.escape(p.get('similar_reason') or '')}</p>
  <div class="warn">{'<br>'.join(html.escape(n) for n in (p.get('notes') or []))}</div>
  {''.join(f'<pre class="body">[{html.escape(a.get("angle",""))}] {html.escape(a.get("text",""))}</pre>' for a in (p.get('alternatives') or []))}
 </details>
</section>""")
    adj = loads(db.get_setting("today_adjustments"), [])
    if adj:
        cards.append("<div class='card'><b>本日の調整</b><ul>" + "".join(f"<li>{html.escape(a)}</li>" for a in adj) + "</ul></div>")
    return _page("今日の投稿", "".join(cards), "today", token)


def render_analytics(db: Database, settings: Settings, token: str) -> str:
    rows = db.q("SELECT day, revenue_jpy, profit_jpy, views, conversions, epc, posts FROM daily_summary ORDER BY day DESC LIMIT 14")
    tbl = "".join(f"<tr><td>{r['day']}</td><td>{r['posts']}</td><td>{r['views']:,}</td><td>{r['conversions']:.1f}</td><td>{r['revenue_jpy']:,.0f}</td><td>{r['profit_jpy']:,.0f}</td></tr>" for r in rows)
    pats = db.q("SELECT pattern_id,pattern_name,uses,avg_views,engagement_rate,epc,confidence,trend_score,status FROM patterns ORDER BY status, epc DESC, avg_views DESC")
    ptbl = "".join(f"<tr><td>{html.escape(p['pattern_id'])}</td><td>{html.escape(p['pattern_name'])}</td><td>{p['uses']}</td><td>{p['avg_views']:,.0f}</td><td>{p['engagement_rate']:.3f}</td><td>{p['epc']:,.0f}</td><td>{p['confidence']:.2f}</td><td>{p['trend_score']:.2f}</td><td>{p['status']}</td></tr>" for p in pats)
    items = attention.open_items(db)
    att = "".join(f"<li>[{html.escape(i['category'])}] {html.escape(i['title'])} → {html.escape(i['action'] or '')}</li>" for i in items) or "<li>なし（自律運用中）</li>"
    last = db.one("SELECT report_md FROM daily_summary ORDER BY day DESC LIMIT 1")
    rep = html.escape(last["report_md"]) if last else "（report 未実行）"
    body = f"""<div class="card"><h2>要対応</h2><ul>{att}</ul></div>
<div class="card"><h2>日次（直近 14 日）</h2><table><tr><th>日</th><th>投稿</th><th>Views</th><th>CV</th><th>売上</th><th>利益</th></tr>{tbl}</table></div>
<div class="card"><h2>パターン</h2><table><tr><th>ID</th><th>名前</th><th>使用</th><th>平均Views</th><th>Eng</th><th>EPC</th><th>信頼</th><th>Trend</th><th>状態</th></tr>{ptbl}</table></div>
<div class="card"><h2>最新レポート</h2><pre style="white-space:pre-wrap;font-size:.85em">{rep}</pre></div>"""
    return _page("分析", body, "analytics", token)


def make_handler(db: Database, settings: Settings):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _auth(self, u) -> bool:
            if not settings.web_token:
                return True
            return (parse_qs(u.query).get("t") or [""])[0] == settings.web_token or self.headers.get("X-Token") == settings.web_token

        def _send(self, code: int, body: str, ctype: str = "text/html; charset=utf-8"):
            b = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            u = urlparse(self.path)
            if not self._auth(u):
                return self._send(403, "forbidden", "text/plain")
            tok = settings.web_token
            if u.path == "/":
                return self._send(200, render_today(db, settings, tok))
            if u.path == "/analytics":
                return self._send(200, render_analytics(db, settings, tok))
            if u.path == "/healthz":
                return self._send(200, "ok", "text/plain")
            self._send(404, "not found", "text/plain")

        def do_POST(self):
            u = urlparse(self.path)
            if not self._auth(u):
                return self._send(403, json.dumps({"ok": False, "error": "forbidden"}), "application/json")
            n = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                data = {}
            if u.path == "/api/posted":
                try:
                    res = posted.register(db, settings, data.get("url", ""), seq=int(data["seq"]) if data.get("seq") else None, day=data.get("day"))
                    return self._send(200, json.dumps({"ok": True, "post": res}, default=str), "application/json")
                except (ValueError, KeyError) as e:
                    return self._send(400, json.dumps({"ok": False, "error": str(e)}), "application/json")
            self._send(404, json.dumps({"ok": False, "error": "not found"}), "application/json")
    return H


def serve(settings: Settings, db: Database) -> None:
    srv = HTTPServer(("0.0.0.0", settings.web_port), make_handler(db, settings))
    print(f"web ui on http://0.0.0.0:{settings.web_port}/" + (f"?t={settings.web_token}" if settings.web_token else ""))
    srv.serve_forever()
