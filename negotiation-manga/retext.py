"""画像生成AIが作った漫画ページの吹き出し内の文字を、正しいセリフに打ち直す。

使い方: python3 retext.py <入力画像> <spec.json> <出力画像>
spec.json: {"bubbles": [{"seed": [x, y], "text": "...", "mode": "v"|"h", "size": 任意(最大フォントサイズ), "box": [x0,y0,x1,y1] 任意}]}
 - seed: 吹き出し内部の1点（座標）。その点の周りの色と同じ色の連結領域を「吹き出しの内側」とみなし、
   中の文字を塗り消してから縦書き(v)／横書き(h)でテキストを描く。
"""
import json, sys, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_CANDIDATES = [os.path.join(HERE, 'fonts-ttf/ShipporiAntiqueB1-Regular.ttf'), '/usr/share/fonts/truetype/fonts-japanese-gothic.ttf']
FONT_PATH = next(p for p in FONT_CANDIDATES if os.path.exists(p))
INK = (26, 24, 22)

ROTATE = set('「」『』（）()〈〉《》【】［］[]ー〜～…‥―－-：:；;＝=→←')
PUNCT_UPPER_RIGHT = set('、。，．,.')
SMALL_KANA = set('ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ')
NO_HEAD = set('、。，．」』）〉》】］…‥ーぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮ')

def font(sz): return ImageFont.truetype(FONT_PATH, sz)

def region_mask(img, seed, tol=48, win=20, box=None):
    a = np.asarray(img.convert('RGB')).astype(int)
    h, w, _ = a.shape
    if box:  # 吹き出しが背景や隣の吹き出しとつながっている場合、この矩形の内側だけを対象にする
        bx0, by0, bx1, by1 = box
        a = a.copy()
        a[:by0, :] = -999; a[by1:, :] = -999; a[:, :bx0] = -999; a[:, bx1:] = -999
    x, y = seed
    x0, x1 = max(0, x - win), min(w, x + win + 1); y0, y1 = max(0, y - win), min(h, y + win + 1)
    patch = a[y0:y1, x0:x1].reshape(-1, 3)
    # 窓内で最も多い色（8階調に量子化して最頻値）を吹き出しの地色とする
    q = (patch // 8) * 8 + 4
    vals, counts = np.unique(q, axis=0, return_counts=True)
    ref = vals[counts.argmax()]
    close = (np.abs(a - ref).max(axis=2) <= tol)
    lab, n = ndimage.label(close)
    ids = lab[y0:y1, x0:x1]; ids = ids[ids > 0]
    if ids.size == 0: raise ValueError(f'seed {seed}: 地色領域が見つかりません')
    best = np.bincount(ids).argmax()
    m = lab == best
    m = ndimage.binary_fill_holes(m)
    m = ndimage.binary_erosion(m, iterations=2)
    return m, tuple(int(v) for v in ref)

def cells_of(text):
    """縦書き用に文字列をセル列に分解。数字2-3桁は縦中横、英字列は回転して連続配置。"""
    cells = []; i = 0
    while i < len(text):
        c = text[i]
        if c == '\n': cells.append(('br', '')); i += 1; continue
        if c.isdigit():
            j = i
            while j < len(text) and text[j].isdigit(): j += 1
            run = text[i:j]
            if len(run) <= 3: cells.append(('tcy', run))
            else: cells.extend(('rot', ch) for ch in run)
            i = j; continue
        if c.isascii() and c.isalpha():
            j = i
            while j < len(text) and text[j].isascii() and (text[j].isalnum()): j += 1
            cells.append(('word', text[i:j])); i = j; continue
        if c in ROTATE: cells.append(('rot', c))
        elif c in PUNCT_UPPER_RIGHT: cells.append(('punct', c))
        elif c in SMALL_KANA: cells.append(('small', c))
        elif c == ' ' or c == '　': cells.append(('space', c))
        else: cells.append(('char', c))
        i += 1
    return cells

def cell_height(cell, fs):
    kind, s = cell
    if kind == 'word': return max(1, len(s) * 0.62) * fs  # 回転した英単語の長さ
    return fs

def layout_vertical(cells, fs, max_h):
    """列ごとにセルを詰める。戻り値: 列のリスト（各列はセルのリスト）"""
    cols = []; cur = []; used = 0.0; step = fs * 1.06
    for cell in cells:
        if cell[0] == 'br':
            cols.append(cur); cur = []; used = 0.0; continue
        h = cell_height(cell, fs) if cell[0] == 'word' else step
        if used + h > max_h + 1e-6 and cur:
            if cell[0] in ('punct',) or (cell[0] in ('char', 'small', 'rot') and cell[1] in NO_HEAD):
                cur.append(cell); continue  # ぶら下げ
            cols.append(cur); cur = [cell]; used = h
        else:
            cur.append(cell); used += h
    if cur: cols.append(cur)
    return cols

def draw_rotated_glyph(base, s, fs, x, y, cw):
    f = font(fs); tmp = Image.new('RGBA', (int(fs * 0.7 * max(1, len(s))) + fs, fs + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp); d.text((2, 0), s, font=f, fill=INK + (255,))
    bbox = tmp.getbbox()
    if bbox: tmp = tmp.crop((bbox[0], 0, bbox[2], tmp.height))
    tmp = tmp.rotate(-90, expand=True)
    base.paste(tmp, (int(x + (cw - tmp.width) / 2), int(y)), tmp)
    return tmp.height

def typeset_vertical(img, mask, text, max_fs=34, min_fs=13):
    ys, xs = np.where(mask)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    W, H = x1 - x0, y1 - y0
    pad_x, pad_y = W * 0.12, H * 0.10
    aw, ah = W - 2 * pad_x, H - 2 * pad_y
    cells = cells_of(text)
    for fs in range(max_fs, min_fs - 1, -1):
        cw = fs * 1.28
        cols = layout_vertical(cells, fs, ah)
        if len(cols) * cw <= aw: break
    total_w = len(cols) * cw
    # 各列の実高さ（中央寄せ用）
    def col_h(col): return sum(cell_height(c, fs) if c[0] == 'word' else fs * 1.06 for c in col)
    block_h = max(col_h(c) for c in cols) if cols else 0
    start_x = x0 + pad_x + (aw - total_w) / 2 + total_w - cw   # 右端の列から
    top = y0 + pad_y + (ah - block_h) / 2
    d = ImageDraw.Draw(img); f = font(fs); fsmall = font(int(fs * 0.86))
    for ci, col in enumerate(cols):
        cx = start_x - ci * cw; cy = top
        for kind, s in col:
            if kind == 'char':
                d.text((cx + (cw - fs) / 2, cy), s, font=f, fill=INK); cy += fs * 1.06
            elif kind == 'small':
                d.text((cx + (cw - fs) / 2 + fs * 0.10, cy - fs * 0.08), s, font=f, fill=INK); cy += fs * 1.06
            elif kind == 'punct':
                d.text((cx + (cw - fs) / 2 + fs * 0.55, cy - fs * 0.50), s, font=f, fill=INK); cy += fs * 1.06
            elif kind == 'rot':
                draw_rotated_glyph(img, s, fs, cx, cy, cw); cy += fs * 1.06
            elif kind == 'word':
                h = draw_rotated_glyph(img, s, fs, cx, cy, cw); cy += h + fs * 0.1
            elif kind == 'tcy':
                ft = font(int(fs * (0.95 if len(s) <= 2 else 0.68)))
                tw = d.textlength(s, font=ft)
                d.text((cx + (cw - tw) / 2, cy + fs * 0.05), s, font=ft, fill=INK); cy += fs * 1.06
            elif kind == 'space':
                cy += fs * 0.5
    return fs

def typeset_horizontal(img, mask, text, max_fs=30, min_fs=12, align='center'):
    ys, xs = np.where(mask)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    W, H = x1 - x0, y1 - y0
    aw, ah = W * 0.90, H * 0.80
    d = ImageDraw.Draw(img)
    for fs in range(max_fs, min_fs - 1, -1):
        f = font(fs); lines = []
        for para in text.split('\n'):
            cur = ''
            for ch in para:
                if d.textlength(cur + ch, font=f) > aw and cur:
                    if ch in NO_HEAD: cur += ch; continue
                    lines.append(cur); cur = ch
                else: cur += ch
            lines.append(cur)
        lh = fs * 1.45
        if len(lines) * lh <= ah: break
    block_h = len(lines) * lh
    y = y0 + (H - block_h) / 2
    for ln in lines:
        tw = d.textlength(ln, font=f)
        x = x0 + (W - tw) / 2 if align == 'center' else x0 + W * 0.05
        d.text((x, y), ln, font=f, fill=INK); y += lh
    return fs

def process(inp, spec, out):
    img = Image.open(inp).convert('RGB')
    for b in spec['bubbles']:
        mask, ref = region_mask(img, tuple(b['seed']), tol=b.get('tol', 48), box=b.get('box'))
        arr = np.asarray(img).copy(); arr[mask] = ref; img = Image.fromarray(arr)
        if b.get('mode', 'v') == 'v':
            fs = typeset_vertical(img, mask, b['text'], max_fs=b.get('size', 34))
        else:
            fs = typeset_horizontal(img, mask, b['text'], max_fs=b.get('size', 30), align=b.get('align', 'center'))
        print(f"  seed {b['seed']}: 領域 {int(mask.sum())}px, フォント {fs}px, {b['text'][:14]}…")
    img.save(out, quality=95)
    print('saved', out)

if __name__ == '__main__':
    inp, specp, out = sys.argv[1:4]
    process(inp, json.load(open(specp, encoding='utf-8')), out)
