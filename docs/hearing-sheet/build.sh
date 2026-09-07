#!/usr/bin/env bash
# 老人シェアハウス（住宅型有料老人ホーム）物件ヒアリングシートの HTML を A4 1枚の PDF に出力する。
# 必要なもの: Chromium（headless）と日本語フォント（IPAGothic 等）
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$DIR/elderly-sharehouse-hearing-sheet.html"
OUT="${1:-$DIR/elderly-sharehouse-hearing-sheet.pdf}"

CHROME="${CHROME_BIN:-}"
if [ -z "$CHROME" ]; then
  for c in /opt/pw-browsers/chromium chromium chromium-browser google-chrome; do
    if command -v "$c" >/dev/null 2>&1 || [ -x "$c" ]; then CHROME="$c"; break; fi
  done
fi
[ -n "$CHROME" ] || { echo "Chromium が見つかりません。CHROME_BIN を指定してください。" >&2; exit 1; }

"$CHROME" --headless --disable-gpu --no-sandbox --no-pdf-header-footer \
  --print-to-pdf="$OUT" "file://$SRC"
echo "出力: $OUT"
