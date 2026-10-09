#!/usr/bin/env python3
"""角形A4号封筒用 宛名帯（ラベル）PDF 生成スクリプト

A4 用紙 1 枚に 210mm x 約74mm の帯を 4 枚配置し、点線で切り取って封筒に貼る想定。
入力: addresses.json（送付先一覧） / 出力: labels.pdf
"""
import json
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

HERE = Path(__file__).parent
FONT_PATH = "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"
FONT = "IPAGothic"
pdfmetrics.registerFont(TTFont(FONT, FONT_PATH))

PAGE_W, PAGE_H = A4          # 210 x 297 mm
LABELS_PER_PAGE = 4
LABEL_H = PAGE_H / LABELS_PER_PAGE   # 帯の高さ (297 / 4 ≈ 74.25mm)
PAD_X = 12 * mm              # 帯内の左右余白
PAD_Y = 6 * mm               # 帯内の上下余白
NAME_SIZE = 20               # 宛名の文字サイズ（全件共通）


def wrap(text, font_size, max_width):
    """文字幅ベースで折り返し（日本語は1文字ずつ判定）"""
    lines, cur = [], ""
    for ch in text:
        if pdfmetrics.stringWidth(cur + ch, FONT, font_size) > max_width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def draw_cut_lines(c):
    c.setDash(3, 3)
    c.setLineWidth(0.3)
    c.setStrokeGray(0.6)
    for i in range(1, LABELS_PER_PAGE):
        y = PAGE_H - i * LABEL_H
        c.line(0, y, PAGE_W, y)
    c.setDash()
    # 四隅のトンボ風マーク（用紙端の確認用）
    c.setStrokeGray(0.6)
    for i in range(1, LABELS_PER_PAGE):
        y = PAGE_H - i * LABEL_H
        c.line(0, y, 4 * mm, y)
        c.line(PAGE_W - 4 * mm, y, PAGE_W, y)


def fit_size(text, sizes, max_width):
    """1行に収まる最大の文字サイズを返す（収まらなければ最小サイズ）"""
    for size in sizes:
        if pdfmetrics.stringWidth(text, FONT, size) <= max_width:
            return size
    return sizes[-1]


def layout_label(entry, width, name_size):
    """描画する行を (font_size, indent, text, gap_before, align) のリストで返す"""
    rows = []
    # 郵便番号（右上）
    rows.append((18, 0, f"〒 {entry['postal']}", 0, "right"))
    first = True
    for part in [entry["address1"], entry.get("address2", "")]:
        if part:
            addr_size = fit_size(part, [14, 13, 12], width)
            for line in wrap(part, addr_size, width):
                rows.append((addr_size, 0, line, 3 * mm if first else 1.5 * mm, "left"))
                first = False
    if entry.get("corp"):
        rows.append((13, 4 * mm, entry["corp"], 5 * mm, "left"))
    honorific = entry.get("honorific", "御中")   # 法人・事業所は「御中」、個人は「様」
    suffix = "　" + honorific
    name_width = width - 4 * mm
    if pdfmetrics.stringWidth(entry["name"] + suffix, FONT, name_size) <= name_width:
        rows.append((name_size, 4 * mm, entry["name"] + suffix, 3 * mm, "left"))
    else:
        # 長い宛名は名称を1行（必要なら折返し）にし、「御中」を次行に右寄せ
        for i, line in enumerate(wrap(entry["name"], name_size, name_width)):
            rows.append((name_size, 4 * mm, line, 3 * mm if i == 0 else 2 * mm, "left"))
        rows.append((name_size, 0, honorific, 2 * mm, "right"))
    return rows


def draw_label(c, entry, top_y, name_size):
    """top_y: 帯の上端のY座標"""
    left = PAD_X
    right = PAGE_W - PAD_X
    width = right - left
    rows = layout_label(entry, width, name_size)
    total = sum(size + gap for size, _, _, gap, _ in rows)
    # 帯内で上下中央（やや上寄せ）
    y = top_y - (LABEL_H - total) / 2
    for size, indent, text, gap, align in rows:
        y -= gap + size
        c.setFont(FONT, size)
        if align == "right":
            c.drawRightString(right, y, text)
        else:
            c.drawString(left + indent, y, text)


def main(src="addresses.json", out="labels.pdf"):
    entries = json.loads((HERE / src).read_text(encoding="utf-8"))
    (HERE / out).parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(HERE / out), pagesize=A4)
    c.setTitle("角A4封筒 宛名帯")
    name_size = NAME_SIZE
    for i, entry in enumerate(entries):
        slot = i % LABELS_PER_PAGE
        if slot == 0 and i > 0:
            c.showPage()
        if slot == 0:
            draw_cut_lines(c)
        top_y = PAGE_H - slot * LABEL_H
        draw_label(c, entry, top_y, name_size)
    c.save()
    print(f"{len(entries)} 件 -> {out} ({(len(entries) + LABELS_PER_PAGE - 1) // LABELS_PER_PAGE} ページ)")


if __name__ == "__main__":
    main(*sys.argv[1:])
