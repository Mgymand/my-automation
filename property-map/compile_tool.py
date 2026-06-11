"""
マイソク PDF 結合ツール

機能:
1. 複数の物件マイソク PDF を読み込み、指定矩形を白塗り（管理会社情報のカット）
2. 比較表ページを生成 (物件名・住所・賃料・面積・築年月・最寄駅徒歩分)
3. 物件位置の地図ページを生成 (国土地理院タイル合成 + ラベル付きピン)
4. 1つの PDF にまとめて出力
"""
from __future__ import annotations

import io
import json
import math
import os
import re
import ssl
import urllib.parse
import urllib.request
from typing import Iterable

import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont

# ---- Fonts ----

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]


def _find_jp_font() -> str:
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    raise RuntimeError("Japanese font not found on system")


JP_FONT_PATH = _find_jp_font()

# PyMuPDF can also use the system font path for CJK text drawing
# We'll insert a fontfile when writing text in PDF pages.


# ---- SSL for tile fetching ----
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


# =============================================================
# 1. PDF preview rendering
# =============================================================

def render_page_png(pdf_path: str, page_num: int = 0, dpi: int = 110) -> tuple[bytes, float, float, int]:
    """Render a single PDF page to PNG bytes.

    Returns (png_bytes, page_width_pt, page_height_pt, total_pages).
    DPI 110 gives reasonable preview clarity without huge bytes.
    """
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    png = pix.tobytes("png")
    w_pt, h_pt = page.rect.width, page.rect.height
    total = len(doc)
    doc.close()
    return png, w_pt, h_pt, total


# =============================================================
# 2. Mask (white-out) rectangles on a PDF
# =============================================================

def mask_pdf(pdf_path: str, rects_per_page: dict[int, list[tuple[float, float, float, float]]]) -> bytes:
    """Apply white-fill rectangles to specified pages.

    rects_per_page: {page_index: [(x, y, w, h), ...]} in PDF points (origin top-left).
    Returns masked PDF as bytes.
    """
    doc = fitz.open(pdf_path)
    for page_idx, rects in rects_per_page.items():
        if page_idx >= len(doc):
            continue
        page = doc[page_idx]
        for (x, y, w, h) in rects:
            rect = fitz.Rect(x, y, x + w, y + h)
            # Use redaction to truly remove underlying text/images, fill white
            page.add_redact_annot(rect, fill=(1, 1, 1))
        page.apply_redactions()
    out = doc.tobytes()
    doc.close()
    return out


# =============================================================
# 3. Property info extraction (for comparison table)
# =============================================================

def extract_for_table(pdf_path: str) -> dict:
    """Extract fields needed for the comparison table.

    Returns dict with keys:
      name, address, rent, area, year, station,
      deposit, keymoney, facilities, interior, available
    """
    import unicodedata
    doc = fitz.open(pdf_path)
    raw = doc[0].get_text()
    doc.close()
    # PDF text often contains Kangxi radical chars (⽉⽊⼩ etc.); NFKC maps these
    # to standard CJK ideographs so our regexes match consistently.
    text = unicodedata.normalize("NFKC", raw)
    # Replace special dashes that fonts may not have glyphs for
    text = text.replace("−", "-").replace("‐", "-").replace("–", "-").replace("—", "-")

    info = {
        "name": "", "address": "", "rent": "", "area": "", "year": "", "station": "",
        "deposit": "", "keymoney": "", "facilities": "", "interior": "", "available": "",
    }

    # 建物名（"建物名" の次に来る非空行）
    m = re.search(r"建\s*物\s*名\s*([^\n]+)", text)
    if m:
        info["name"] = _normalize_space(m.group(1))
    else:
        # fallback: first nonempty line
        for line in text.split("\n"):
            line = line.strip()
            if line:
                info["name"] = line
                break

    # 所在地
    m = re.search(r"所\s*在\s*地[^\n]*\n([^\n]+)", text)
    if m:
        info["address"] = _normalize_space(m.group(1))
    else:
        m = re.search(r"((?:東京都|神奈川県|埼玉県|千葉県|大阪府|京都府|北海道|[^\s]{2,3}県)[^\n]+)", text)
        if m:
            info["address"] = _normalize_space(m.group(1))

    # 賃料
    m = re.search(r"賃\s*料\s*([0-9０-９,，\.]+\s*(?:万円|円))", text)
    if m:
        info["rent"] = _normalize_space(m.group(1))

    # 面積
    m = re.search(r"([\d０-９][\d０-９\.\,]*)\s*(㎡|m2|m²|平米)", text)
    if m:
        info["area"] = f"{_normalize_space(m.group(1))} ㎡"

    # 築年月
    m = re.search(r"(\d{4}\s*年\s*\d{1,2}\s*月)", text)
    if m:
        info["year"] = _normalize_space(m.group(1))

    # 最寄駅・徒歩
    m = re.search(r"((?:JR|東京メトロ|東急|京王|小田急|京急|京成|西武|東武|相鉄|つくば|都営)[^\n]*徒歩\s*\d+\s*分)", text)
    if m:
        info["station"] = _normalize_space(m.group(1))
    else:
        m = re.search(r"([^\n]+徒歩\s*\d+\s*分)", text)
        if m:
            info["station"] = _normalize_space(m.group(1))

    # 敷金 + 保証金 (combined, always show both if present)
    deposit_parts = []
    m = re.search(r"敷\s*金\s+([^\s礼保]+(?:\s*ヶ月)?(?:\s*[\d,]+\s*円)?)", text)
    if m:
        deposit_parts.append(f"敷金 {m.group(1).strip()}")
    m = re.search(r"保\s*証\s*金\s+([^\s礼敷取]+(?:\s*ヶ月)?(?:\s*[\d,]+\s*円)?)", text)
    if m:
        deposit_parts.append(f"保証金 {m.group(1).strip()}")
    info["deposit"] = " / ".join(deposit_parts)

    # 礼金
    m = re.search(r"礼\s*金\s+([^\s敷保]+(?:\s*ヶ月)?(?:\s*[\d,]+\s*円)?)", text)
    if m:
        info["keymoney"] = m.group(1).strip()

    # 設備 → トイレ・水回り・EV 関連を抽出
    # 「設 備」行の直後にデバイス一覧があるパターンが多い
    m = re.search(r"設\s*備\s*\n([^\n]+(?:\n[^\n備保現]+)*)", text)
    if m:
        full_facilities = _normalize_space(m.group(1))
        # フィルタ: トイレ・水回り・EV関連キーワードを含む項目だけ拾う
        keywords = ["トイレ", "B・T", "BT", "バストイレ", "シャワー", "洗面",
                    "給湯", "エレベーター", "EV", "Ｂ・Ｔ", "湯沸", "キッチン", "ガス"]
        items = re.split(r"[,，、]", full_facilities)
        # Collapse internal whitespace inside each item (PDF can split "2基以上" -> "2基以 上")
        def _clean(s: str) -> str:
            return re.sub(r"\s+", "", s.strip())
        matched = [_clean(it) for it in items
                   if any(k in it for k in keywords) and it.strip()]
        if matched:
            info["facilities"] = ", ".join(matched)
        else:
            # fallback: keep raw 設備 text (also cleaned)
            info["facilities"] = ", ".join(_clean(it) for it in items if it.strip())

    # 内装状況 (居抜き・スケルトン・事務所使用可 など)
    interior_keywords = ["居抜き", "居抜", "スケルトン", "事務所使用可",
                         "事務所利用可", "事務所可", "現状渡し", "原状回復済"]
    found = [k for k in interior_keywords if k in text]
    if found:
        info["interior"] = ", ".join(found)

    # 入居可能日 / 引渡可能時期
    m = re.search(r"(?:入居|引渡)\s*可\s*能\s*\n?\s*時\s*期\s*([即時相談近\d\.年月日要応上]+)", text)
    if m:
        info["available"] = m.group(1).strip()
    else:
        # Fallback: standalone 即時 near 引渡/入居 area
        m = re.search(r"(?:入居|引渡)[^\n]{0,30}(即時|相談|応相談|\d{4}年\d+月)", text)
        if m:
            info["available"] = m.group(1).strip()

    return info


def _normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


# =============================================================
# 4. Comparison table page
# =============================================================

# Comparison table: rows are property attributes, columns are properties.
# "name" is rendered as the column header for each property, so it is NOT
# included in the body rows.
TABLE_ROWS = [
    ("address", "住所"),
    ("rent", "賃料"),
    ("area", "面積"),
    ("year", "築年月"),
    ("station", "最寄駅・徒歩"),
    ("deposit", "敷金（保証金）"),
    ("keymoney", "礼金"),
    ("facilities", "トイレ・水回り・EV"),
    ("interior", "内装状況"),
    ("available", "入居可能日"),
]


def make_table_pdf(properties: list[dict]) -> bytes:
    """Create a comparison table PDF (transposed layout).

    Each property is a column; each attribute is a row.
    Returns A4-landscape PDF as bytes. Spans multiple pages when the property
    count exceeds the per-page limit.
    """
    page_w, page_h = 842.0, 595.0  # A4 landscape
    margin_left = 30
    margin_right = 30
    margin_top = 40
    margin_bottom = 30
    title_font_size = 18
    header_font_size = 10
    label_font_size = 10
    cell_font_size = 10

    label_col_w = 110.0       # left column with attribute labels
    min_prop_col_w = 110.0    # minimum width per property column

    avail_w = page_w - margin_left - margin_right - label_col_w
    props_per_page = max(1, int(avail_w // min_prop_col_w))

    doc = fitz.open()

    if not properties:
        page = doc.new_page(width=page_w, height=page_h)
        page.insert_font(fontname="HirJP", fontfile=JP_FONT_PATH)
        page.insert_text((margin_left, margin_top), "物件比較表",
                         fontsize=title_font_size, fontname="HirJP",
                         color=(0.12, 0.16, 0.23))
        page.insert_text((margin_left, margin_top + 40), "物件がありません",
                         fontsize=12, fontname="HirJP",
                         color=(0.4, 0.45, 0.55))
        try: doc.subset_fonts()
        except Exception: pass
        out = doc.tobytes(garbage=4, deflate=True)
        doc.close()
        return out

    for chunk_idx in range(0, len(properties), props_per_page):
        chunk = properties[chunk_idx:chunk_idx + props_per_page]
        page = doc.new_page(width=page_w, height=page_h)
        page.insert_font(fontname="HirJP", fontfile=JP_FONT_PATH)

        # Title
        title = "物件比較表"
        if len(properties) > props_per_page:
            title += f" ({chunk_idx + 1}-{chunk_idx + len(chunk)} / {len(properties)})"
        page.insert_text((margin_left, margin_top), title,
                         fontsize=title_font_size, fontname="HirJP",
                         color=(0.12, 0.16, 0.23))

        table_top = margin_top + 25
        n = len(chunk)
        prop_col_w = avail_w / n

        # Compute row heights dynamically
        header_h = _estimate_text_height(
            [p.get("name", "") or "—" for p in chunk],
            prop_col_w, header_font_size, min_lines=2,
        )

        row_heights = []
        for key, label in TABLE_ROWS:
            cell_vals = [p.get(key, "") or "—" for p in chunk]
            cell_vals.append(label)
            rh = _estimate_text_height(cell_vals, prop_col_w, cell_font_size, min_lines=1)
            row_heights.append(max(24.0, rh))

        # Scale rows if total exceeds page
        total_h = header_h + sum(row_heights)
        max_h = page_h - table_top - margin_bottom
        if total_h > max_h:
            scale = max_h / total_h
            header_h *= scale
            row_heights = [h * scale for h in row_heights]

        # --- Header row (property names) ---
        x = margin_left
        y = table_top
        page.draw_rect(fitz.Rect(x, y, x + label_col_w, y + header_h),
                       color=(0.5, 0.6, 0.75), fill=(0.92, 0.95, 0.99), width=0.5)
        x += label_col_w
        for prop in chunk:
            rect = fitz.Rect(x, y, x + prop_col_w, y + header_h)
            page.draw_rect(rect, color=(0.5, 0.6, 0.75),
                           fill=(0.92, 0.95, 0.99), width=0.5)
            name = prop.get("name", "") or "—"
            page.insert_textbox(
                fitz.Rect(x + 5, y + 4, x + prop_col_w - 5, y + header_h - 4),
                name,
                fontsize=header_font_size, fontname="HirJP",
                color=(0.10, 0.14, 0.20), align=fitz.TEXT_ALIGN_CENTER,
            )
            x += prop_col_w

        # --- Body rows (one per attribute) ---
        y = table_top + header_h
        for ri, ((key, label), rh) in enumerate(zip(TABLE_ROWS, row_heights)):
            x = margin_left
            stripe = (1, 1, 1) if ri % 2 == 0 else (0.97, 0.98, 1.0)
            # label cell
            label_rect = fitz.Rect(x, y, x + label_col_w, y + rh)
            page.draw_rect(label_rect, color=(0.85, 0.88, 0.93),
                           fill=(0.94, 0.97, 1.0), width=0.4)
            page.insert_textbox(
                fitz.Rect(x + 6, y + 4, x + label_col_w - 6, y + rh - 4),
                label,
                fontsize=label_font_size, fontname="HirJP",
                color=(0.30, 0.36, 0.45), align=fitz.TEXT_ALIGN_LEFT,
            )
            x += label_col_w
            # value cells
            for prop in chunk:
                rect = fitz.Rect(x, y, x + prop_col_w, y + rh)
                page.draw_rect(rect, color=(0.85, 0.88, 0.93), fill=stripe, width=0.4)
                val = prop.get(key, "") or "—"
                page.insert_textbox(
                    fitz.Rect(x + 5, y + 4, x + prop_col_w - 5, y + rh - 4),
                    val,
                    fontsize=cell_font_size, fontname="HirJP",
                    color=(0.12, 0.16, 0.23), align=fitz.TEXT_ALIGN_LEFT,
                )
                x += prop_col_w
            y += rh

    try: doc.subset_fonts()
    except Exception: pass
    out = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return out


def _estimate_text_height(texts: list[str], col_w: float, font_size: float,
                          min_lines: int = 1) -> float:
    """Estimate row height required to fit any text in col_w."""
    max_lines = min_lines
    char_w = font_size * 0.95
    chars_per_line = max(1, int((col_w - 10) / char_w))
    for t in texts:
        if not t:
            continue
        # ASCII chars roughly half-width vs CJK
        weight = sum(0.55 if ord(c) < 0x80 else 1.0 for c in t)
        lines = math.ceil(weight / chars_per_line)
        if lines > max_lines:
            max_lines = lines
    return 8 + max_lines * (font_size + 4)


# =============================================================
# 5. Map image with labeled pins
# =============================================================

TILE_SIZE = 256
TILE_URL = "https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png"


def _latlon_to_pixel(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Web Mercator lat/lon -> global pixel coords at given zoom."""
    n = 2 ** zoom
    x = (lon + 180.0) / 360.0 * n * TILE_SIZE
    lat_rad = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n * TILE_SIZE
    return x, y


def _fetch_tile(z: int, x: int, y: int) -> Image.Image:
    """Fetch a single tile from 国土地理院. Returns white tile on failure."""
    url = TILE_URL.format(z=z, x=x, y=y)
    req = urllib.request.Request(url, headers={"User-Agent": "PropertyMapApp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
            data = resp.read()
            return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        # Blank tile placeholder
        return Image.new("RGB", (TILE_SIZE, TILE_SIZE), (245, 245, 245))


MAX_GSI_ZOOM = 18  # 国土地理院 std タイルは zoom 18 まで


def _pick_zoom(points: list[tuple[float, float]], target_w: int, target_h: int) -> int:
    """Pick zoom level so that bounding box of points fits in ~70% of target image."""
    if not points:
        return 14
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    if len(points) == 1:
        return min(16, MAX_GSI_ZOOM)
    lat_min, lat_max = min(lats), max(lats)
    lon_min, lon_max = min(lons), max(lons)
    # iterate zoom from high to low (capped at MAX_GSI_ZOOM)
    for z in range(MAX_GSI_ZOOM, 5, -1):
        x1, y1 = _latlon_to_pixel(lat_max, lon_min, z)
        x2, y2 = _latlon_to_pixel(lat_min, lon_max, z)
        bbox_w = x2 - x1
        bbox_h = y2 - y1
        if bbox_w <= target_w * 0.7 and bbox_h <= target_h * 0.7:
            return z
    return 8


def make_map_image(properties: list[dict], width: int = 1400, height: int = 1700) -> Image.Image:
    """Compose a map image centered on properties with labeled pins.

    properties: list of {"name": str, "lat": float, "lon": float}
    """
    pts = [(p["lat"], p["lon"]) for p in properties if p.get("lat") is not None]
    if not pts:
        # Empty map placeholder
        img = Image.new("RGB", (width, height), (245, 245, 245))
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype(JP_FONT_PATH, 28)
        draw.text((width // 2 - 100, height // 2), "位置情報なし", fill=(120, 120, 120), font=font)
        return img

    zoom = _pick_zoom(pts, width, height)
    center_lat = sum(p[0] for p in pts) / len(pts)
    center_lon = sum(p[1] for p in pts) / len(pts)

    cx, cy = _latlon_to_pixel(center_lat, center_lon, zoom)
    # top-left of canvas in global pixel space
    origin_x = cx - width / 2
    origin_y = cy - height / 2

    # Tile range
    tile_x0 = int(origin_x // TILE_SIZE)
    tile_y0 = int(origin_y // TILE_SIZE)
    tile_x1 = int((origin_x + width) // TILE_SIZE)
    tile_y1 = int((origin_y + height) // TILE_SIZE)

    canvas = Image.new("RGB", (width, height), (240, 240, 240))
    n_tiles = 2 ** zoom

    for tx in range(tile_x0, tile_x1 + 1):
        for ty in range(tile_y0, tile_y1 + 1):
            wrap_tx = tx % n_tiles
            if ty < 0 or ty >= n_tiles:
                continue
            tile = _fetch_tile(zoom, wrap_tx, ty)
            px = int(tx * TILE_SIZE - origin_x)
            py = int(ty * TILE_SIZE - origin_y)
            canvas.paste(tile, (px, py))

    # Slight white overlay to soften map
    overlay = Image.new("RGBA", (width, height), (255, 255, 255, 40))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")

    # Draw pins
    draw = ImageDraw.Draw(canvas)
    title_font = ImageFont.truetype(JP_FONT_PATH, 32)
    label_font = ImageFont.truetype(JP_FONT_PATH, 22)

    # Title
    draw.rectangle((0, 0, width, 60), fill=(37, 99, 235))
    draw.text((20, 12), "物件位置マップ", fill=(255, 255, 255), font=title_font)

    pin_color = (220, 38, 38)  # red-600
    pin_stroke = (140, 20, 20)

    placed_labels: list[tuple[int, int, int, int]] = []

    for p in properties:
        if p.get("lat") is None:
            continue
        gx, gy = _latlon_to_pixel(p["lat"], p["lon"], zoom)
        x = int(gx - origin_x)
        y = int(gy - origin_y)
        if not (0 <= x < width and 0 <= y < height):
            continue
        _draw_pin(draw, x, y, fill=pin_color, stroke=pin_stroke)

        # Label: anchor below pin tip; shift to avoid overlap
        text = p.get("name", "")
        if not text:
            continue
        bbox = draw.textbbox((0, 0), text, font=label_font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        # default position: below the pin
        lx = x - tw // 2 - 8
        ly = y + 8
        # collision avoidance: try below, above, right, left
        candidates = [
            (lx, ly),
            (x - tw // 2 - 8, y - 50 - th),  # above
            (x + 18, y - 22),                # right
            (x - tw - 36, y - 22),           # left
        ]
        chosen = candidates[0]
        for cx_, cy_ in candidates:
            rect = (cx_, cy_, cx_ + tw + 16, cy_ + th + 10)
            if not any(_rects_overlap(rect, r) for r in placed_labels):
                chosen = (cx_, cy_)
                break
        cx_, cy_ = chosen
        bg = (cx_, cy_, cx_ + tw + 16, cy_ + th + 10)
        # Background rounded rectangle (simple alpha box)
        draw.rounded_rectangle(bg, radius=6, fill=(255, 255, 255), outline=(30, 41, 59), width=2)
        draw.text((cx_ + 8, cy_ + 4), text, fill=(30, 41, 59), font=label_font)
        placed_labels.append(bg)

    # Attribution
    attr_font = ImageFont.truetype(JP_FONT_PATH, 14)
    attr = "地図: 国土地理院"
    bbox = draw.textbbox((0, 0), attr, font=attr_font)
    aw = bbox[2] - bbox[0]
    draw.rectangle((width - aw - 16, height - 26, width, height), fill=(255, 255, 255))
    draw.text((width - aw - 8, height - 22), attr, fill=(60, 60, 60), font=attr_font)

    return canvas


def _rects_overlap(a, b) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _draw_pin(draw: ImageDraw.ImageDraw, x: int, y: int, fill, stroke):
    """Draw a teardrop pin with tip at (x, y)."""
    head_r = 16
    head_cx = x
    head_cy = y - 30
    # Body: triangle from tip up to head circle
    draw.polygon(
        [(x, y), (head_cx - head_r + 2, head_cy + 4), (head_cx + head_r - 2, head_cy + 4)],
        fill=fill,
        outline=stroke,
    )
    # Head
    draw.ellipse(
        (head_cx - head_r, head_cy - head_r, head_cx + head_r, head_cy + head_r),
        fill=fill,
        outline=stroke,
        width=2,
    )
    # Inner dot
    draw.ellipse(
        (head_cx - 6, head_cy - 6, head_cx + 6, head_cy + 6),
        fill=(255, 255, 255),
    )


def make_map_pdf(properties: list[dict]) -> bytes:
    """Render map image into a single A4-portrait PDF page."""
    img = make_map_image(properties, width=1400, height=1700)
    # JPEG keeps the file ~10x smaller than PNG for map imagery
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    img_bytes = buf.getvalue()

    # A4 portrait: 595 x 842
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # Fit image with margin
    margin = 24
    page.insert_image(
        fitz.Rect(margin, margin, 595 - margin, 842 - margin),
        stream=img_bytes,
        keep_proportion=True,
    )
    out = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return out


# =============================================================
# 6. Combine all
# =============================================================

def combine_pdfs(pdf_blobs: list[bytes]) -> bytes:
    """Concatenate multiple PDFs (as bytes) into one."""
    out_doc = fitz.open()
    for blob in pdf_blobs:
        src = fitz.open("pdf", blob)
        out_doc.insert_pdf(src)
        src.close()
    result = out_doc.tobytes()
    out_doc.close()
    return result


# =============================================================
# 7. Geocoding (re-uses logic from app.py - keep local for module isolation)
# =============================================================

def normalize_address(address: str) -> str:
    import unicodedata
    address = unicodedata.normalize("NFKC", address)
    chome_map = {"1": "一", "2": "二", "3": "三", "4": "四", "5": "五",
                 "6": "六", "7": "七", "8": "八", "9": "九", "10": "十"}

    def replace_chome(m):
        chome = chome_map.get(m.group(1), m.group(1))
        return f"{chome}丁目{m.group(2)}-{m.group(3)}"

    address = re.sub(r"(\d+)-(\d+)-(\d+)", replace_chome, address)
    return address


def geocode(address: str) -> tuple[float | None, float | None]:
    normalized = normalize_address(address)
    query = urllib.parse.urlencode({"q": normalized})
    url = f"https://msearch.gsi.go.jp/address-search/AddressSearch?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "PropertyMapApp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data:
                coords = data[0]["geometry"]["coordinates"]
                return float(coords[1]), float(coords[0])
    except Exception as e:
        print(f"Geocoding failed for {address}: {e}")
    return None, None
