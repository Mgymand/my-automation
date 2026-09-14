"""内見依頼書（FAX送信票 兼 内見予約のお願い）を生成するスクリプト。

物件・担当者・名刺画像を差し替えて A4 縦 1 枚の PDF を出力する。

使い方:
    python3 make_naiken_request.py config.json --card meishi.png --out 内見依頼書.pdf

config.json の例は同じフォルダの sample_config.json を参照。
名刺画像は横向き（名刺の天地が正しい状態）で渡す。PDF を渡した場合は
1 ページ目に埋め込まれた最大の画像を取り出し、--rotate で回転できる。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

import fitz  # PyMuPDF
from PIL import Image

# ---- フォント ------------------------------------------------------------

_FONT_CANDIDATES = {
    "regular": [
        os.environ.get("NAIKEN_FONT_REGULAR", ""),
        "./fonts/NotoSansJP-Regular.ttf",
        "./fonts/NotoSansCJKjp-Regular.otf",
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf",
    ],
    "bold": [
        os.environ.get("NAIKEN_FONT_BOLD", ""),
        "./fonts/NotoSansJP-Bold.ttf",
        "./fonts/NotoSansCJKjp-Bold.otf",
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf",
    ],
}


def _find_font(kind: str) -> str:
    for p in _FONT_CANDIDATES[kind]:
        if p and os.path.exists(p):
            return p
    raise RuntimeError(f"日本語フォント({kind})が見つかりません。NAIKEN_FONT_{kind.upper()} で指定してください")


def _subset_font(path: str, chars: str) -> bytes | None:
    """fontTools で使用文字だけのサブセットを作る。失敗したら None（フル埋め込みにフォールバック）。

    フル埋め込みだと CJK フォント 2 書体で 30MB 近くになるため。
    """
    try:
        from fontTools import subset
        from fontTools.ttLib import TTFont
    except ImportError:
        return None
    try:
        font = TTFont(path, fontNumber=0)
        opts = subset.Options()
        opts.layout_features = ["*"]
        opts.name_IDs = ["*"]
        opts.notdef_outline = True
        sub = subset.Subsetter(options=opts)
        sub.populate(text=chars + "0123456789-:/ ")
        sub.subset(font)
        buf = io.BytesIO()
        font.save(buf)
        return buf.getvalue()
    except Exception as e:  # noqa: BLE001
        print(f"font subset failed for {path}: {e}; embedding full font", file=sys.stderr)
        return None


# ---- 名刺画像 -------------------------------------------------------------

def load_card_image(path: str, rotate: int = 0) -> bytes:
    """名刺画像（PNG/JPG または PDF）を読み込み、JPEG bytes を返す。"""
    if path.lower().endswith(".pdf"):
        doc = fitz.open(path)
        page = doc[0]
        best = None
        for img in page.get_images(full=True):
            info = doc.extract_image(img[0])
            if best is None or info["width"] * info["height"] > best["width"] * best["height"]:
                best = info
        doc.close()
        if best is None:
            raise RuntimeError("PDF に画像が見つかりません")
        im = Image.open(io.BytesIO(best["image"]))
    else:
        im = Image.open(path)
    im = im.convert("RGB")
    if rotate:
        im = im.rotate(rotate, expand=True)  # 反時計回り（PIL の仕様）
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=90)  # スキャン画像は JPEG でサイズを抑える
    return buf.getvalue()


# ---- 描画 ---------------------------------------------------------------

PAGE_W, PAGE_H = 595.92, 842.88
ASCENT = 0.88  # top-of-bbox から baseline までの比率（Noto/ヒラギノでほぼ共通）


class Writer:
    def __init__(self, page: fitz.Page):
        self.page = page
        self.reg = _find_font("regular")
        self.bold = _find_font("bold")
        self._fr = fitz.Font(fontfile=self.reg)
        self._fb = fitz.Font(fontfile=self.bold)
        self._ops: list[tuple[float, float, str, float, bool]] = []

    def flush(self) -> None:
        """溜めた文字列を、使用グリフだけに絞ったフォントで書き込む。"""
        chars = "".join(op[2] for op in self._ops)
        for name, path, bold in (("JPR", self.reg, False), ("JPB", self.bold, True)):
            used = "".join(op[2] for op in self._ops if op[4] == bold)
            buf = _subset_font(path, used or chars)
            if buf is not None:
                self.page.insert_font(fontname=name, fontbuffer=buf)
            else:
                self.page.insert_font(fontname=name, fontfile=path)
        for (x, top, s, size, bold) in self._ops:
            self.page.insert_text(
                (x, top + size * ASCENT), s, fontsize=size,
                fontname="JPB" if bold else "JPR", color=(0, 0, 0),
            )
        self._ops.clear()

    def width(self, text: str, size: float, bold: bool = False) -> float:
        return (self._fb if bold else self._fr).text_length(text, fontsize=size)

    def text(self, x: float, top: float, s: str, size: float, bold: bool = False) -> float:
        """bbox の上端 top を基準に文字を置き、右端 x を返す（実書き込みは flush 時）。"""
        self._ops.append((x, top, s, size, bold))
        return x + self.width(s, size, bold)

    def text_center(self, top: float, s: str, size: float, bold: bool = False) -> None:
        w = self.width(s, size, bold)
        self.text((PAGE_W - w) / 2, top, s, size, bold)

    def text_right(self, right: float, top: float, s: str, size: float, bold: bool = False) -> None:
        w = self.width(s, size, bold)
        self.text(right - w, top, s, size, bold)

    def paragraph(self, x0: float, x1: float, top: float, s: str, size: float, leading: float) -> None:
        """簡易折り返し（行頭禁則のみ対応）。"""
        no_head = "。、」）］・〜ーんっゃゅょ"  # 行頭禁則文字
        line = ""
        y = top
        for ch in s:
            if self.width(line + ch, size) > (x1 - x0) and ch not in no_head:
                self.text(x0, y, line, size)
                y += leading
                line = ch
            else:
                line += ch
        if line:
            self.text(x0, y, line, size)

    def rect(self, r: tuple[float, float, float, float], width: float, fill=None) -> None:
        sh = self.page.new_shape()
        sh.draw_rect(fitz.Rect(*r))
        sh.finish(color=(0, 0, 0) if width else None, width=width, fill=fill)
        sh.commit()


# 表の行（上端 y, 下端 y, ラベル）
ROWS = [
    (127.5, 168.0, "送信先"),
    (168.0, 246.0, "会社名"),
    (246.0, 304.5, "内見担当者"),
    (304.5, 363.0, "物件名"),
    (363.0, 402.0, "売出価格"),
    (402.0, 445.5, "内見希望日時"),
]
LABEL_COL_R = 92.2
CONTENT_X = 101.0
BORDER = 1.5


def build(cfg: dict, card_png: bytes, out_path: str) -> None:
    doc = fitz.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    w = Writer(page)

    # タイトル
    w.rect((1.1, 1.9, 594.4, 61.1), 2.25)
    w.text_center(21, "内 見 依 頼 書", 22, bold=True)
    w.text_center(68, "FAX 送信票　兼　内見予約のお願い", 10)

    # 送信日 / 枚数 / 整理番号
    w.text(0, 100, f"送信日：{cfg['send_date']}", 10)
    w.text(262, 100, f"送信枚数：{cfg.get('pages', '1枚')}", 10)
    w.text_right(595, 100, f"整理番号：{cfg['ref_no']}", 10)

    # 表の罫線
    for (y0, y1, label) in ROWS:
        w.rect((0.0, y0, LABEL_COL_R, y1), 0, fill=None)
        # 外枠 + 仕切り（塗りつぶし矩形で 1.5pt 線を再現）
        for r in [
            (0.0, y0 - BORDER / 2, 595.5, y0 + BORDER / 2),        # 上線
            (0.0, y0, BORDER, y1),                                  # 左線
            (LABEL_COL_R - BORDER, y0, LABEL_COL_R, y1),            # 仕切り
            (595.5 - BORDER, y0, 595.5, y1),                        # 右線
        ]:
            w.rect(r, 0, fill=(0, 0, 0))
        w.rect((0.0, y1 - BORDER / 2, 595.5, y1 + BORDER / 2), 0, fill=(0, 0, 0))
        # ラベル（縦中央）
        w.text(10, (y0 + y1) / 2 - 11 * 0.5, label, 11, bold=True)

    # 送信先
    to = cfg["to"]
    x = w.text(CONTENT_X, 136, f"{to['name']} 御中", 14, bold=True)
    w.text(x, 139, f"　{to.get('attn', 'ご担当者様')}", 11.5)
    if to.get("note"):
        w.text(CONTENT_X, 154, to["note"], 9)

    # 会社名（自社）
    co = cfg["company"]
    x = w.text(CONTENT_X, 180, co["name"], 14, bold=True)
    w.text(x, 183, f"　{co['license']}", 11.5)
    w.text(CONTENT_X, 204, co["address"], 11.5)
    w.text(CONTENT_X, 223, f"TEL：{co['tel']}　／　FAX：{co['fax']}", 11.5)

    # 内見担当者
    st = cfg["staff"]
    w.text(CONTENT_X, 258, f"{st['dept']}　{st['name']}", 14, bold=True)
    w.text(CONTENT_X, 282, f"携帯：{st['mobile']}　／　E-mail：{st['email']}", 11.5)

    # 物件名
    pr = cfg["property"]
    w.text(CONTENT_X, 317, pr["title"], 14, bold=True)
    w.text(CONTENT_X, 340, pr["address"], 11.5)

    # 売出価格
    w.text(CONTENT_X, 375, pr["price"], 14, bold=True)

    # 内見希望日時
    w.text(CONTENT_X, 415, cfg["visit"], 17, bold=True)

    # 本文
    w.paragraph(0, 595, 464,
                "上記のとおり内見をお願いいたします。ご都合が合わない場合は、"
                "お手数ですが上記の携帯またはメールまでご連絡ください。", 11, 18)

    # 名刺
    w.text(0, 515, "［ 名刺 ］", 10)
    im = Image.open(io.BytesIO(card_png))
    card_w = 333.0
    card_h = card_w * im.height / im.width
    r = fitz.Rect(0.75, 533.25, 0.75 + card_w, 533.25 + card_h)
    page.insert_image(r, stream=card_png)
    w.rect((r.x0 - 0.4, r.y0 - 0.4, r.x1 + 0.4, r.y1 + 0.4), 0.75)

    # 注記
    w.paragraph(0, 595, max(745, r.y1 + 16),
                "※ 本書は宅地建物取引業者間の業務連絡です。ご提供いただいた物件資料を、"
                "貴社の承諾なく第三者へ開示・転載することはいたしません。", 9.5, 16)

    w.flush()
    doc.save(out_path, garbage=3, deflate=True)
    doc.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config", help="設定 JSON")
    ap.add_argument("--card", required=True, help="名刺画像（PNG/JPG/PDF）")
    ap.add_argument("--rotate", type=int, default=0, help="名刺画像の回転角（反時計回り、例: 90）")
    ap.add_argument("--out", required=True, help="出力 PDF パス")
    a = ap.parse_args()
    with open(a.config, encoding="utf-8") as f:
        cfg = json.load(f)
    build(cfg, load_card_image(a.card, a.rotate), a.out)
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
