#!/usr/bin/env bash
# 老人シェアハウス（住宅型有料老人ホーム）物件ヒアリングシートの HTML を PDF に出力する。
#   elderly-sharehouse-hearing-sheet.html     → A4 1枚版
#   elderly-sharehouse-hearing-sheet-2p.html  → A4 2枚版（記入スペースに余裕を持たせた版）
#   elderly-sharehouse-hearing-sheet-sample.html → 1枚版の記入例（春日部市東中野のマイソク）
# 必要なもの: Chromium（headless）と日本語フォント（IPAGothic 等）
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CHROME="${CHROME_BIN:-}"
if [ -z "$CHROME" ]; then
  for c in /opt/pw-browsers/chromium chromium chromium-browser google-chrome; do
    if command -v "$c" >/dev/null 2>&1 || [ -x "$c" ]; then CHROME="$c"; break; fi
  done
fi
[ -n "$CHROME" ] || { echo "Chromium が見つかりません。CHROME_BIN を指定してください。" >&2; exit 1; }

for name in elderly-sharehouse-hearing-sheet elderly-sharehouse-hearing-sheet-2p elderly-sharehouse-hearing-sheet-sample; do
  src="$DIR/$name.html"
  [ -f "$src" ] || continue
  out="$DIR/$name.pdf"
  "$CHROME" --headless --disable-gpu --no-sandbox --no-pdf-header-footer \
    --print-to-pdf="$out" "file://$src"
  echo "出力: $out"
done
