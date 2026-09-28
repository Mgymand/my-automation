"""index.html を Chromium でレンダリングし、PDF と各ページPNGを output/ に書き出す。

使い方:  python3 render.py            # PDF + PNG(2x)
         python3 render.py --check    # 収まりチェック結果も表示
Playwright と Chromium が必要（pip install playwright && playwright install chromium）。
"""
import glob, json, os, sys
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
os.makedirs(OUT, exist_ok=True)
exe = os.environ.get("CHROME_PATH")
if not exe:
    cands = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    exe = cands[-1] if cands else None

with sync_playwright() as p:
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    kw = {"proxy": {"server": proxy}} if proxy else {}
    if exe: kw["executable_path"] = exe
    browser = p.chromium.launch(**kw)
    ctx = browser.new_context(viewport={"width": 860, "height": 1200}, device_scale_factor=2, ignore_https_errors=True)
    page = ctx.new_page()
    page.on("requestfailed", lambda r: print("request failed:", r.url[:90], r.failure))
    page.goto("file://" + os.path.join(HERE, "index.html"), wait_until="networkidle")
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(1200)
    print("fonts loaded:", page.evaluate("[...document.fonts].filter(f=>f.status==='loaded').map(f=>f.family).filter((v,i,a)=>a.indexOf(v)===i)"))
    page.evaluate("window.__fit()")
    if "--check" in sys.argv:
        print(json.dumps(page.evaluate("window.__overflow()"), ensure_ascii=False, indent=1))
    pages = page.query_selector_all(".pg")
    for i, el in enumerate(pages, 1):
        el.screenshot(path=os.path.join(OUT, f"page-{i:02d}.png"))
    page.emulate_media(media="print")
    page.pdf(path=os.path.join(OUT, "negotiation-manga.pdf"), width="800px", height="1131px",
             print_background=True, prefer_css_page_size=True)
    browser.close()
print(f"rendered {len(pages)} pages -> {OUT}")
