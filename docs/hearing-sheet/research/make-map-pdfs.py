#!/usr/bin/env python3
"""地理院タイル・ハザードマップタイルから物件周辺の地図PDFを作る。

使い方: python3 make-map-pdfs.py <lat> <lon> "<物件名>" <出力ディレクトリ>
タイルは3×3枚（768×768px）を合成し、中心に物件マーカーを打つ。
ハザード系はレイヤを淡色地図に重ねる。タイルが存在しない＝該当なし。
"""
import io, math, sys, urllib.request, concurrent.futures as cf
from PIL import Image, ImageDraw, ImageFont

UA = {"User-Agent": "Mozilla/5.0 (property-research)"}
FONT = "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf"

def latlon_to_tile(lat, lon, z):
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    la = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(la)) / math.pi) / 2.0 * n
    return x, y

def fetch(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
            return Image.open(io.BytesIO(r.read())).convert("RGBA")
    except Exception:
        return None

def mosaic(tmpl, lat, lon, z, n=3):
    """中心タイルの周囲 n×n を貼り合わせ、中心画素の座標も返す"""
    fx, fy = latlon_to_tile(lat, lon, z)
    cx, cy = int(fx), int(fy)
    half = n // 2
    canvas = Image.new("RGBA", (256 * n, 256 * n), (0, 0, 0, 0))
    jobs = {}
    with cf.ThreadPoolExecutor(9) as ex:
        for dy in range(-half, half + 1):
            for dx in range(-half, half + 1):
                url = tmpl.format(z=z, x=cx + dx, y=cy + dy)
                jobs[ex.submit(fetch, url)] = (dx, dy)
        for fut, (dx, dy) in jobs.items():
            im = fut.result()
            if im is not None:
                canvas.paste(im, ((dx + half) * 256, (dy + half) * 256))
    px = int((fx - cx + half) * 256)
    py = int((fy - cy + half) * 256)
    return canvas, (px, py)

def marker(im, xy, label="物件"):
    d = ImageDraw.Draw(im)
    x, y = xy
    r = 9
    d.ellipse([x - r - 3, y - r - 3, x + r + 3, y + r + 3], fill=(255, 255, 255, 230))
    d.ellipse([x - r, y - r, x + r, y + r], fill=(200, 30, 30, 255), outline=(255, 255, 255, 255), width=3)
    d.line([x, y + r, x, y + r + 14], fill=(200, 30, 30, 255), width=4)
    try:
        f = ImageFont.truetype(FONT, 22)
    except Exception:
        f = ImageFont.load_default()
    tw = d.textlength(label, font=f)
    d.rectangle([x - tw/2 - 6, y + r + 16, x + tw/2 + 6, y + r + 46], fill=(255,255,255,235))
    d.text((x - tw/2, y + r + 19), label, fill=(180, 20, 20), font=f)
    return im

STD   = "https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png"
PALE  = "https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png"
PHOTO = "https://cyberjapandata.gsi.go.jp/xyz/seamlessphoto/{z}/{x}/{y}.jpg"

LAYERS = [
    ("01-位置図（地理院標準地図）",        STD,   16, None),
    ("02-位置図（航空写真）",              PHOTO, 17, None),
    ("03-洪水浸水想定区域（想定最大規模）", PALE,  16, "https://disaportaldata.gsi.go.jp/raster/01_flood_l2_shinsuishin_data/{z}/{x}/{y}.png"),
    ("04-洪水浸水想定区域（計画規模）",     PALE,  16, "https://disaportaldata.gsi.go.jp/raster/01_flood_l1_shinsuishin_newlegend_data/{z}/{x}/{y}.png"),
    ("05-浸水継続時間（想定最大規模）",     PALE,  16, "https://disaportaldata.gsi.go.jp/raster/01_flood_l2_keizoku_data/{z}/{x}/{y}.png"),
    ("06-家屋倒壊等氾濫想定区域（氾濫流）", PALE,  16, "https://disaportaldata.gsi.go.jp/raster/01_flood_l2_kaokutokai_hanran_data/{z}/{x}/{y}.png"),
    ("07-土砂災害警戒区域",                PALE,  16, "https://disaportaldata.gsi.go.jp/raster/05_dosekiryukeikaikuiki/{z}/{x}/{y}.png"),
    ("08-津波浸水想定",                    PALE,  16, "https://disaportaldata.gsi.go.jp/raster/04_tsunami_newlegend_data/{z}/{x}/{y}.png"),
]

def main():
    lat, lon, name, outdir = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3], sys.argv[4]
    for title, base, z, over in LAYERS:
        im, xy = mosaic(base, lat, lon, z)
        hit = "―"
        if over:
            ov, _ = mosaic(over, lat, lon, z)
            hit = "該当あり" if ov.getchannel("A").getextrema()[1] > 0 else "該当なし（タイルなし）"
            im = Image.alpha_composite(im, ov)
        im = marker(im, xy, "物件")
        d = ImageDraw.Draw(im)
        try:
            f  = ImageFont.truetype(FONT, 24)
            fs = ImageFont.truetype(FONT, 17)
        except Exception:
            f = fs = ImageFont.load_default()
        cap = title.split("-", 1)[1]
        d.rectangle([0, 0, 768, 62], fill=(255, 255, 255, 235))
        d.text((12, 8),  f"{cap}", fill=(15, 47, 92), font=f)
        d.text((12, 38), f"{name}　北緯{lat} 東経{lon}　z={z}"
                         + (f"　判定：{hit}" if over else ""), fill=(60, 70, 80), font=fs)
        d.rectangle([0, 0, 767, 767], outline=(120, 130, 140, 255), width=2)
        path = f"{outdir}/{title}.pdf"
        im.convert("RGB").save(path, "PDF", resolution=150)
        print(f"{title}: {hit}")

if __name__ == "__main__":
    main()
