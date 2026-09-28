"""投稿パッケージの整形（テキスト / Markdown / HTML）とフォルダ出力。"""
from __future__ import annotations

import html
import json
from pathlib import Path

BAR = "━" * 16


def _price(p: dict) -> str:
    if not p.get("price"):
        return "-"
    s = f"{int(p['price']):,}円"
    if p.get("list_price") and p["list_price"] > p["price"]:
        s += f"（通常 {int(p['list_price']):,}円）"
    return s


def render_text(p: dict) -> str:
    pred = p.get("predicted") or {}
    lines = [BAR, f"POST {p['seq']}", BAR,
             f"推奨投稿時刻：{p['scheduled_local']}",
             f"優先度：{p.get('priority') or '-'}",
             f"商品名：{p['title']}",
             f"女優：{'・'.join(p.get('actresses') or []) or '-'}",
             f"ジャンル：{'・'.join((p.get('genres') or [])[:4]) or '-'}",
             f"価格：{_price(p)}",
             f"割引：{int(float(p.get('discount_rate') or 0) * 100)}%" if p.get("discount_rate") else "割引：なし",
             f"FANZA URL：{p.get('url') or '-'}",
             f"Affiliate URL：{p.get('affiliate_url') or '-'}",
             f"使用Pattern：{p.get('pattern_id')}（{p.get('pattern_name') or ''}）/ 訴求軸 {p.get('angle')}",
             f"この商品を選んだ理由：{p.get('reason') or '-'}",
             "投稿本文：", p["text"], "",
             "使用推奨素材：", f"画像/動画URL：{p.get('media_source') or '（公式素材なし）'}",
             f"素材タイプ：{'動画' if p.get('media_type') == 'video' else '画像' if p.get('media_type') == 'image' else 'なし'}",
             f"素材の権利状態：{'OK（DMM 公式素材）' if p.get('media_source') else '要確認'}",
             "期待値：",
             f"  Predicted Views {pred.get('views', '-')}", f"  Predicted CTR {pred.get('ctr', '-')}",
             f"  Predicted CVR {pred.get('cvr', '-')}", f"  Expected Revenue {pred.get('revenue', '-')} 円",
             "類似成功投稿：", f"  Post ID {p.get('similar_post_id') or '-'}", f"  {p.get('similar_reason') or '（調査データなし）'}",
             "投稿時の注意："]
    lines += [f"  {n}" for n in (p.get("notes") or [])]
    alts = p.get("alternatives") or []
    if alts:
        lines.append("代替案（必要な場合のみ）：")
        for a in alts:
            lines.append(f"  [{a.get('angle')}] {a.get('text')}")
    lines.append(BAR)
    return "\n".join(lines)


def render_schedule(packages: list[dict]) -> str:
    return "\n".join(f"{p['scheduled_local']} POST {p['seq']}" + ("  ✅投稿済" if p.get("status") == "posted" else "") for p in packages)


def render_day_text(packages: list[dict], adjustments: list[str] | None = None) -> str:
    out = [render_schedule(packages), ""]
    out += [render_text(p) for p in packages]
    if adjustments:
        out += ["", "本日の調整："] + [f"・{a}" for a in adjustments]
    return "\n".join(out)


def render_day_html(packages: list[dict], day: str, adjustments: list[str] | None = None) -> str:
    cards = []
    for p in packages:
        pred = p.get("predicted") or {}
        media_html = ""
        if p.get("media_type") == "image" and p.get("media_source"):
            media_html = f'<img src="{html.escape(p["media_source"])}" alt="" loading="lazy">'
        elif p.get("media_type") == "video" and p.get("media_source"):
            media_html = f'<video src="{html.escape(p["media_source"])}" controls muted playsinline></video>'
        cards.append(f"""
<section class="card" id="post{p['seq']}">
  <div class="head"><span class="time">{p['scheduled_local']}</span> <span class="seq">POST {p['seq']}</span>
    <span class="prio">優先度 {html.escape(str(p.get('priority') or '-'))}</span></div>
  {media_html}
  <h2>{html.escape(p['title'])}</h2>
  <div class="meta">{html.escape('・'.join(p.get('actresses') or []) or '-')} / {html.escape('・'.join((p.get('genres') or [])[:3]))} / {html.escape(_price(p))}</div>
  <pre class="body" id="text{p['seq']}">{html.escape(p['text'])}</pre>
  <div class="row"><button onclick="copyText('text{p['seq']}')">本文をコピー</button>
    <a class="btn" href="{html.escape(p.get('affiliate_url') or '#')}" target="_blank" rel="noopener">Affiliate URL</a>
    {f'<a class="btn" href="{html.escape(p["media_source"])}" target="_blank" rel="noopener">素材を開く</a>' if p.get('media_source') else ''}</div>
  <details><summary>詳細（理由・期待値・注意・代替案）</summary>
    <p><b>理由:</b> {html.escape(p.get('reason') or '')}</p>
    <p><b>期待値:</b> Views {pred.get('views','-')} / CTR {pred.get('ctr','-')} / CVR {pred.get('cvr','-')} / 売上 {pred.get('revenue','-')} 円</p>
    <p><b>類似成功投稿:</b> {html.escape(str(p.get('similar_post_id') or '-'))} {html.escape(p.get('similar_reason') or '')}</p>
    <ul>{''.join(f'<li>{html.escape(n)}</li>' for n in (p.get('notes') or []))}</ul>
    {''.join(f'<pre class="alt">[{html.escape(a.get("angle",""))}] {html.escape(a.get("text",""))}</pre>' for a in (p.get('alternatives') or []))}
  </details>
</section>""")
    adj = "".join(f"<li>{html.escape(a)}</li>" for a in (adjustments or []))
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>投稿セット {html.escape(day)}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans",sans-serif;margin:0;padding:12px;background:#f5f5f7;color:#111}}
.card{{background:#fff;border-radius:12px;padding:14px;margin:0 0 14px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.head{{display:flex;gap:10px;align-items:baseline}} .time{{font-size:1.4em;font-weight:700}} .seq{{color:#666}} .prio{{margin-left:auto;font-size:.9em;color:#a00}}
img,video{{width:100%;border-radius:8px;margin:8px 0}} h2{{font-size:1.05em;margin:6px 0}} .meta{{color:#555;font-size:.9em}}
pre.body{{white-space:pre-wrap;background:#f0f0f4;padding:10px;border-radius:8px;font-family:inherit;font-size:1.05em}}
pre.alt{{white-space:pre-wrap;background:#fafafa;border-left:3px solid #ccc;padding:6px;font-family:inherit;font-size:.9em}}
.row{{display:flex;gap:8px;flex-wrap:wrap}} button,.btn{{flex:1;min-width:120px;text-align:center;padding:12px;border:0;border-radius:8px;background:#1d4ed8;color:#fff;font-size:1em;text-decoration:none}}
.btn{{background:#374151}} details{{margin-top:8px;font-size:.92em}} .schedule{{font-size:1.1em;line-height:1.7}}
</style></head><body>
<h1 style="font-size:1.2em">今日の投稿 {html.escape(day)}</h1>
<div class="card schedule">{"<br>".join(html.escape(l) for l in render_schedule(packages).splitlines())}</div>
{''.join(cards)}
{f'<div class="card"><b>本日の調整</b><ul>{adj}</ul></div>' if adj else ''}
<script>function copyText(id){{const t=document.getElementById(id).innerText;navigator.clipboard.writeText(t).then(()=>alert('コピーしました'))}}</script>
</body></html>"""


def export_day(packages: list[dict], day: str, out_dir: Path, adjustments: list[str] | None = None) -> Path:
    d = out_dir / day
    d.mkdir(parents=True, exist_ok=True)
    (d / "posts.txt").write_text(render_day_text(packages, adjustments), encoding="utf-8")
    (d / "index.html").write_text(render_day_html(packages, day, adjustments), encoding="utf-8")
    (d / "packages.json").write_text(json.dumps(packages, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    for p in packages:
        (d / f"post{p['seq']}.txt").write_text(p["text"] + "\n", encoding="utf-8")
        if p.get("media_source"):
            (d / f"post{p['seq']}_media.txt").write_text(p["media_source"] + "\n", encoding="utf-8")
    return d
