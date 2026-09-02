# -*- coding: utf-8 -*-
import base64, html, os
from model import *

def img64(path):
    ext = os.path.splitext(path)[1].lstrip('.').replace('jpg','jpeg')
    with open(path,'rb') as f: return f"data:image/{ext};base64," + base64.b64encode(f.read()).decode()

def esc(s): return html.escape(str(s), quote=False)

CSS = r"""
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Serif+JP:wght@400;500;600;700&family=Noto+Sans+JP:wght@400;500;700&display=swap">
<style>
:root{
  --paper:#fcfcfa; --ink:#1b1b1f; --ink-2:#4a4d57; --ink-3:#7a7e8a;
  --ai:#1f2d4d;      /* 藍: 見出し帯 */
  --ai-2:#3a4a70;
  --shu:#a63a2e;     /* 朱: 判定・決裁 */
  --kin:#9c8146;     /* 金: 表紙罫 */
  --line:#c9ccd4; --line-2:#e3e5ea; --wash:#f3f4f6; --wash-ai:#eef1f7; --wash-shu:#f8efed;
}
*{box-sizing:border-box}
html{background:#d9dbe0}
body{margin:0;background:#d9dbe0;color:var(--ink);font-family:'Noto Serif JP','Hiragino Mincho ProN','Yu Mincho',serif;font-size:10.5pt;line-height:1.72;font-feature-settings:"palt" 0;}
.sheet{background:var(--paper);width:210mm;margin:12mm auto;padding:18mm 17mm 20mm 17mm;box-shadow:0 2px 18px rgba(20,30,60,.18);position:relative}
@page{size:A4;margin:17mm 16mm 19mm 16mm;
  @top-left{content:"稟議書（不動産取得・事業計画）　整理番号 2　春日部市東中野 1523-13";font-family:'Noto Serif JP',serif;font-size:7.5pt;color:#7a7e8a}
  @top-right{content:"社外秘 / CONFIDENTIAL";font-family:'Noto Sans JP',sans-serif;font-size:7.5pt;letter-spacing:.08em;color:#a63a2e}
  @bottom-center{content:"— " counter(page) " / " counter(pages) " —";font-family:'Noto Serif JP',serif;font-size:8.5pt;color:#4a4d57}
}
@media print{
  html,body{background:#fff}
  .sheet{width:auto;margin:0;padding:0;box-shadow:none}
  .pb{page-break-before:always}
  .avoid{page-break-inside:avoid}
  h2{page-break-after:avoid} h3{page-break-after:avoid}
  tr{page-break-inside:avoid}
  a{color:inherit;text-decoration:none}
}
@media screen{ .pb{margin-top:18mm;border-top:1px dashed var(--line);padding-top:10mm} }
h1,h2,h3,h4{font-weight:600;text-wrap:balance;margin:0}
h2{font-size:15.5pt;color:var(--paper);background:var(--ai);padding:5px 12px;margin:18px 0 10px;letter-spacing:.04em;display:flex;align-items:baseline;gap:12px}
h2 .n{font-family:'Noto Sans JP',sans-serif;font-weight:500;font-size:10pt;opacity:.85;letter-spacing:.12em}
h3{font-size:12.5pt;color:var(--ai);border-left:4px solid var(--ai);padding-left:9px;margin:16px 0 7px}
h4{font-size:11pt;margin:10px 0 4px;color:var(--ink)}
p{margin:4px 0 8px;max-width:100%}
.lead{font-size:11pt}
small,.small{font-size:8.5pt;color:var(--ink-2)}
.muted{color:var(--ink-3)}
.sans{font-family:'Noto Sans JP',sans-serif}
.num,.tbl td.num,.tbl th.num{font-family:'Noto Sans JP',sans-serif;font-variant-numeric:tabular-nums;text-align:right}
.tbl{width:100%;border-collapse:collapse;font-family:'Noto Sans JP',sans-serif;font-size:8.6pt;line-height:1.45;margin:4px 0 8px}
.tbl th,.tbl td{border:1px solid var(--line);padding:4px 6px;vertical-align:top}
.tbl th{background:var(--ai);color:#fff;font-weight:500;text-align:left;letter-spacing:.03em}
.tbl th.sub{background:var(--wash-ai);color:var(--ai);font-weight:600}
.tbl td.lab{background:var(--wash);width:24%;font-weight:500}
.tbl td.k{background:var(--wash-ai);font-weight:500}
.tbl tr.total td{background:var(--wash);font-weight:600}
.tbl tr.hl td{background:#fbf6ea}
.tbl .c{text-align:center}
.tbl caption{caption-side:top;text-align:left;font-family:'Noto Serif JP',serif;font-size:9.5pt;font-weight:600;color:var(--ai);padding:2px 0 4px}
.wide{overflow-x:auto}
.intent{border-left:3px solid var(--shu);background:var(--wash-shu);padding:6px 10px 6px 12px;margin:6px 0 12px;font-size:9pt;line-height:1.6;color:var(--ink-2)}
.intent b{color:var(--shu);font-weight:600;margin-right:6px;letter-spacing:.06em}
.note{border:1px solid var(--line);background:var(--wash);padding:6px 10px;margin:6px 0 10px;font-size:9pt;line-height:1.6}
.note b.t{color:var(--ai)}
.warn{border:1px solid #d9b8b3;background:#fbf3f1;padding:7px 11px;margin:6px 0 10px;font-size:9.2pt;line-height:1.6}
.warn b.t{color:var(--shu)}
.badge{display:inline-block;font-family:'Noto Sans JP',sans-serif;font-weight:700;border:1.5px solid currentColor;border-radius:50%;width:19px;height:19px;line-height:16px;text-align:center;font-size:10pt}
.ok{color:#1f6f3f}.ng{color:var(--shu)}.md{color:#8a6d1a}
.stamp{display:inline-block;border:2px solid var(--shu);color:var(--shu);border-radius:3px;padding:1px 8px;font-weight:600;letter-spacing:.15em;font-size:10pt}
.cover{padding-top:6mm}
.cover .kanri{display:flex;justify-content:space-between;font-family:'Noto Sans JP',sans-serif;font-size:8.5pt;color:var(--ink-2);letter-spacing:.08em}
.cover .rule{border:0;border-top:2px solid var(--kin);margin:6mm 0 4mm;position:relative}
.cover .rule:after{content:"";display:block;border-top:1px solid var(--kin);margin-top:2px}
.cover h1{font-size:27pt;letter-spacing:.22em;text-align:center;margin:8mm 0 2mm;font-weight:600}
.cover .sub{text-align:center;font-size:12pt;letter-spacing:.1em;color:var(--ink-2)}
.cover .obj{text-align:center;margin:8mm 0 4mm;font-size:13pt;letter-spacing:.06em}
.approve{width:100%;border-collapse:collapse;font-family:'Noto Sans JP',sans-serif;font-size:8.5pt;margin-top:6mm}
.approve th{border:1px solid var(--ink);background:var(--wash-ai);font-weight:500;padding:3px;color:var(--ai)}
.approve td{border:1px solid var(--ink);height:22mm;text-align:center;vertical-align:bottom;padding:3px;color:var(--ink-3)}
.kv{width:100%;border-collapse:collapse;font-size:9.4pt;margin:4px 0 8px}
.kv th{width:22%;text-align:left;background:var(--wash-ai);color:var(--ai);border:1px solid var(--line);padding:4px 7px;font-weight:600;font-family:'Noto Sans JP',sans-serif;font-size:8.8pt}
.kv td{border:1px solid var(--line);padding:4px 7px;font-family:'Noto Sans JP',sans-serif;font-size:9pt}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}
.tile{border:1px solid var(--line);padding:7px 10px;background:#fff}
.tile .l{font-family:'Noto Sans JP',sans-serif;font-size:8pt;color:var(--ink-3);letter-spacing:.1em}
.tile .v{font-family:'Noto Sans JP',sans-serif;font-size:14.5pt;font-weight:700;color:var(--ai);font-variant-numeric:tabular-nums;line-height:1.25}
.tile .v.shu{color:var(--shu)}
.tile .s{font-size:8.3pt;color:var(--ink-2)}
figure{margin:8px 0 10px;text-align:center}
figure img{max-width:100%;border:1px solid var(--line-2)}
figcaption{font-size:8.5pt;color:var(--ink-2);margin-top:3px;font-family:'Noto Sans JP',sans-serif}
ol,ul{margin:4px 0 8px;padding-left:1.6em} li{margin:2px 0}
.toc{columns:2;column-gap:24px;font-size:9.4pt;font-family:'Noto Sans JP',sans-serif} .toc div{padding:1px 0;border-bottom:1px dotted var(--line-2)}
.src{font-size:8pt;color:var(--ink-3);font-family:'Noto Sans JP',sans-serif;word-break:break-all}
.chart{width:100%;height:auto;font-family:'Noto Sans JP',sans-serif}
.legend{font-size:8.5pt;font-family:'Noto Sans JP',sans-serif;color:var(--ink-2)}
.flow{display:flex;gap:6px;align-items:stretch;font-family:'Noto Sans JP',sans-serif;font-size:8.6pt;margin:6px 0 10px}
.flow .st{flex:1;border:1px solid var(--ai);padding:6px 7px;background:#fff;position:relative}
.flow .st b{display:block;color:var(--ai);font-size:9.2pt}
.flow .st:after{content:"▶";position:absolute;right:-9px;top:40%;color:var(--ai);font-size:8pt}
.flow .st:last-child:after{content:""}
.part{margin:4mm 0 6mm;border-top:2px solid var(--kin);border-bottom:1px solid var(--kin);padding:8px 4px}
.part .pn{font-family:'Noto Sans JP',sans-serif;font-size:9pt;letter-spacing:.2em;color:var(--kin)}
.part .pt{font-size:19pt;font-weight:600;letter-spacing:.06em;color:var(--ai)}
.chk{list-style:none;padding-left:0} .chk li{padding-left:1.6em;position:relative} .chk li:before{content:"□";position:absolute;left:0;color:var(--ai)}
.sig{font-size:8.5pt;color:var(--ink-3);text-align:right;margin-top:4px}
.dl{display:grid;grid-template-columns:auto 1fr;gap:2px 12px;font-size:9.2pt}
.dl dt{font-weight:600;color:var(--ai);font-family:'Noto Sans JP',sans-serif}
.dl dd{margin:0}
</style>
"""

def sec(num, title):
    return f'<h2><span class="n">{esc(num)}</span>{esc(title)}</h2>\n'

def intent(text):
    return f'<div class="intent"><b>記載意図</b>{text}</div>\n'

def note(title, text, warn=False):
    return f'<div class="{"warn" if warn else "note"}"><b class="t">{esc(title)}</b>　{text}</div>\n'

def badge(kind):
    m = {'ok':('○','ok'),'ng':('×','ng'),'md':('△','md')}[kind]
    return f'<span class="badge {m[1]}">{m[0]}</span>'

def table(headers, rows, caption=None, cls='tbl', widths=None, num_cols=()):
    h = f'<div class="wide"><table class="{cls}">'
    if caption: h += f'<caption>{caption}</caption>'
    if widths: h += '<colgroup>' + ''.join(f'<col style="width:{w}">' for w in widths) + '</colgroup>'
    if headers:
        h += '<thead><tr>' + ''.join(f'<th{" class=num" if i in num_cols else ""}>{x}</th>' for i,x in enumerate(headers)) + '</tr></thead>'
    h += '<tbody>'
    for r in rows:
        cls_r = ''
        if isinstance(r, dict):
            cls_r = f' class="{r.get("cls","")}"'; r = r['cells']
        h += f'<tr{cls_r}>' + ''.join(f'<td{" class=num" if i in num_cols else ""}>{x}</td>' for i,x in enumerate(r)) + '</tr>'
    return h + '</tbody></table></div>\n'

def kv(pairs):
    h = '<table class="kv">'
    for k, v in pairs: h += f'<tr><th>{k}</th><td>{v}</td></tr>'
    return h + '</table>\n'

def tiles(items, cols=3):
    h = f'<div class="grid{cols}">'
    for l, v, s, shu in items:
        h += f'<div class="tile"><div class="l">{l}</div><div class="v{" shu" if shu else ""}">{v}</div><div class="s">{s}</div></div>'
    return h + '</div>\n'

def fig(path, caption, width='100%'):
    return f'<figure class="avoid"><img src="{img64(path)}" style="width:{width}" alt="{esc(caption)}"><figcaption>{caption}</figcaption></figure>\n'

def man(x):  # 万円表記
    return f"{x/10_000:,.0f}万円" if abs(x) >= 10_000 else f"{int(x):,}円"
def man1(x): return f"{x/10_000:,.1f}万円"
def pct(x, d=1): return f"{x*100:.{d}f}%"

# ---------------------------------------------------------------- SVG charts
def svg_bars(labels, values, title, unit='万円', w=640, h=230, fmt=lambda v: f"{v/10000:,.0f}"):
    """単一系列の縦棒（負値は朱）。1スケール・軸ラベルは到達値のみ。"""
    n = len(values); vmax = max(max(values), 0); vmin = min(min(values), 0)
    pad_l, pad_r, pad_t, pad_b = 54, 16, 30, 34
    pw, ph = w-pad_l-pad_r, h-pad_t-pad_b
    span = (vmax - vmin) or 1
    def y(v): return pad_t + (vmax - v)/span*ph
    bw = pw/n*0.58
    s = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">']
    s.append(f'<text x="{pad_l}" y="16" font-size="11" font-weight="600" fill="#1f2d4d">{esc(title)}</text>')
    # gridlines at 0, max, min
    for gv in sorted(set([0, vmax, vmin])):
        yy = y(gv)
        s.append(f'<line x1="{pad_l}" x2="{w-pad_r}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#d6d9e0" stroke-width="{1.2 if gv==0 else 0.8}" fill="none"/>')
        s.append(f'<text x="{pad_l-6}" y="{yy+4:.1f}" font-size="9" text-anchor="end" fill="#7a7e8a">{fmt(gv)}</text>')
    for i,(lab,v) in enumerate(zip(labels, values)):
        cx = pad_l + pw*(i+0.5)/n
        top, bot = y(max(v,0)), y(min(v,0))
        col = '#1f2d4d' if v >= 0 else '#a63a2e'
        s.append(f'<rect x="{cx-bw/2:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{max(bot-top,0.5):.1f}" fill="{col}" rx="2"><title>{esc(lab)}: {fmt(v)}{unit}</title></rect>')
        ty = top-5 if v>=0 else bot+11
        s.append(f'<text x="{cx:.1f}" y="{ty:.1f}" font-size="9.5" text-anchor="middle" fill="#1b1b1f" font-weight="600">{fmt(v)}</text>')
        s.append(f'<text x="{cx:.1f}" y="{h-12}" font-size="10" text-anchor="middle" fill="#4a4d57">{esc(lab)}</text>')
    s.append(f'<text x="{pad_l}" y="{h-1}" font-size="8.5" fill="#7a7e8a">単位: {unit}</text>')
    s.append('</svg>')
    return ''.join(s)

def svg_ladder(points, title, lo, hi, w=680, h=235):
    """価格の位置関係（1軸）。points: [(label, value, kind)] kind in ('ref','offer','limit','ask')"""
    pad_l, pad_r = 30, 30; y_axis = 128
    def x(v): return pad_l + (v-lo)/(hi-lo)*(w-pad_l-pad_r)
    s = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">']
    s.append(f'<text x="{pad_l}" y="16" font-size="11" font-weight="600" fill="#1f2d4d">{esc(title)}</text>')
    s.append(f'<line x1="{pad_l}" x2="{w-pad_r}" y1="{y_axis}" y2="{y_axis}" stroke="#4a4d57" stroke-width="1.2" fill="none"/>')
    for t in range(int(lo/1_000_000), int(hi/1_000_000)+1):
        v = t*1_000_000
        if lo <= v <= hi:
            s.append(f'<line x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{y_axis-4}" y2="{y_axis+4}" stroke="#4a4d57" stroke-width="1" fill="none"/>')
            s.append(f'<text x="{x(v):.1f}" y="{y_axis+18}" font-size="9" text-anchor="middle" fill="#7a7e8a">{t*100:,}万</text>')
    cols = {'ref':'#7a7e8a','offer':'#a63a2e','limit':'#a63a2e','ask':'#1f2d4d','cap':'#9c8146'}
    # alternate label heights to avoid collisions
    above = sorted([p for p in points], key=lambda p: p[1])
    placed = []  # (x, up, lvl)
    for i,(lab,v,kind) in enumerate(above):
        xx = x(v); col = cols[kind]
        up = (i % 2 == 0)
        # 近接する既配置ラベル（同じ側・水平距離110px以内）の数だけ段を上げる
        lvl = sum(1 for (px,pu,pl) in placed if pu == up and abs(px-xx) < 110)
        placed.append((xx, up, lvl))
        ly = y_axis-30-lvl*15 if up else y_axis+36+lvl*15
        s.append(f'<circle cx="{xx:.1f}" cy="{y_axis}" r="{5 if kind in ("offer","limit","ask") else 3.5}" fill="{col}" stroke="#fcfcfa" stroke-width="1.5"><title>{esc(lab)}: {v/10000:,.0f}万円</title></circle>')
        s.append(f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="{y_axis-6 if up else y_axis+6}" y2="{ly+3 if up else ly-9}" stroke="{col}" stroke-width="0.8" stroke-dasharray="2 2" fill="none"/>')
        anchor = 'middle'
        s.append(f'<text x="{xx:.1f}" y="{ly:.1f}" font-size="8.5" text-anchor="{anchor}" fill="{col}" font-weight="{600 if kind!="ref" else 400}">{esc(lab)} {v/10000:,.0f}万</text>')
    s.append('</svg>')
    return ''.join(s)
