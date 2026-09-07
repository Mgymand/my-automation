#!/usr/bin/env bash
# docs/business-meeting のHTMLをPDFに変換する。
# 使い方: ./build.sh [名前...]   引数なしで全件
set -euo pipefail
cd "$(dirname "$0")"
CHROME_BIN="${CHROME_BIN:-/opt/pw-browsers/chromium}"

# ハンドアウトは _common.css を __CSS__ の位置に流し込んでから描画する
render_handout() {
  local name="$1"
  python3 - "$name" <<'PY'
import sys, pathlib
name = sys.argv[1]
src = pathlib.Path(f"{name}.html").read_text(encoding="utf-8")
css = pathlib.Path("_common.css").read_text(encoding="utf-8")
if "__CSS__" in src:
    src = src.replace("__CSS__", css)
pathlib.Path(f".build-{name}.html").write_text(src, encoding="utf-8")
PY
  "$CHROME_BIN" --headless --disable-gpu --no-sandbox \
    --print-to-pdf="$name.pdf" --no-pdf-header-footer \
    "file://$PWD/.build-$name.html" >/dev/null 2>&1
  rm -f ".build-$name.html"
  python3 -c "
import fitz,sys
d=fitz.open('$name.pdf')
print(f'$name: {d.page_count} ページ  {d[0].rect.width:.0f}x{d[0].rect.height:.0f}pt')
"
}

names=("$@")
if [ ${#names[@]} -eq 0 ]; then
  names=(kickoff-deck screening-flow acceptance-criteria sales-pack)
fi
for n in "${names[@]}"; do render_handout "$n"; done
