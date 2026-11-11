#!/usr/bin/env bash
# private の運用リポジトリにワークフロー一式をコピーする。
#   bash fanza-affiliate/ops/install.sh <運用リポジトリのクローン先>
# 例: gh repo create fanza-ops --private --clone && bash fanza-affiliate/ops/install.sh fanza-ops
set -euo pipefail
dst="${1:?運用リポジトリのディレクトリを指定してください}"
src="$(cd "$(dirname "$0")/template" && pwd)"
[ -d "$dst/.git" ] || { echo "$dst は git リポジトリではありません"; exit 1; }
cp -R "$src/." "$dst/"
echo "コピーしました:"; (cd "$src" && find . -type f | sort | sed 's|^\./|  |')
echo "次: cd $dst && git add -A && git commit -m 'FANZA 運用ワークフロー' && git push"
