#!/usr/bin/env python3
"""角形A4号封筒用 宛名帯（ラベル）PDF 生成スクリプト

A4 用紙 1 枚に 210mm x 99mm の帯を 3 枚配置し、点線で切り取って封筒に貼る想定。
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
LABEL_H = 99 * mm            # 帯の高さ (297 / 3)
LABELS_PER_PAGE = 3
PAD_X = 12 * mm              # 帯内の左右余白
PAD_Y = 9 * mm               # 帯内の上下余白


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


def layout_label(entry, width):
    """描画する行を (font_size, indent, text, gap_before) のリストで返す"""
    rows = []
    rows.append((18, 0, f"〒 {entry['postal']}", 0))
    first = True
    for part in [entry["address1"], entry.get("address2", "")]:
        if part:
            addr_size = fit_size(part, [14, 13, 12], width)
            for line in wrap(part, addr_size, width):
                rows.append((addr_size, 0, line, 5 * mm if first else 1.5 * mm))
                first = False
    if entry.get("corp"):
        rows.append((13, 4 * mm, entry["corp"], 6 * mm))
    suffix = "　御中"
    name_size = fit_size(entry["name"] + suffix, [24, 22, 20, 18, 17], width - 4 * mm)
    lines = wrap(entry["name"], name_size,
                 width - 4 * mm - pdfmetrics.stringWidth(suffix, FONT, name_size))
    for i, line in enumerate(lines):
        rows.append((name_size, 4 * mm, line + (suffix if i == len(lines) - 1 else ""),
                     4 * mm if i == 0 else 2 * mm))
    return rows


def draw_label(c, entry, index, top_y):
    """top_y: 帯の上端のY座標"""
    left = PAD_X
    right = PAGE_W - PAD_X
    width = right - left
    rows = layout_label(entry, width)
    total = sum(size + gap for size, _, _, gap in rows)
    # 帯内で上下中央（やや上寄せ）
    y = top_y - (LABEL_H - total) / 2 + 2 * mm
    for size, indent, text, gap in rows:
        y -= gap + size
        c.setFont(FONT, size)
        c.drawString(left + indent, y, text)

    # 通し番号（部数一覧との突合用・小さく右下）
    c.setFont(FONT, 7)
    c.setFillGray(0.5)
    c.drawRightString(right, top_y - LABEL_H + 4 * mm, f"No.{index:02d}")
    c.setFillGray(0)


def main(src="addresses.json", out="labels.pdf"):
    entries = json.loads((HERE / src).read_text(encoding="utf-8"))
    c = canvas.Canvas(str(HERE / out), pagesize=A4)
    c.setTitle("角A4封筒 宛名帯")
    for i, entry in enumerate(entries):
        slot = i % LABELS_PER_PAGE
        if slot == 0 and i > 0:
            c.showPage()
        if slot == 0:
            draw_cut_lines(c)
        top_y = PAGE_H - slot * LABEL_H
        draw_label(c, entry, entry.get("no", i + 1), top_y)
    c.save()
    print(f"{len(entries)} 件 -> {out} ({(len(entries) + LABELS_PER_PAGE - 1) // LABELS_PER_PAGE} ページ)")


if __name__ == "__main__":
    main(*sys.argv[1:])
