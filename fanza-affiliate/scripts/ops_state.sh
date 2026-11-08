#!/usr/bin/env bash
# 運用リポジトリの状態（SQLite DB）を専用ブランチに保存 / 復元する。
#   ops_state.sh pull <dir>   ブランチ ${STATE_BRANCH:-fanza-state} の内容を <dir> に展開（無ければ空で開始）
#   ops_state.sh push <dir>   <dir> を 1 コミットだけのブランチとして強制更新（履歴を溜めない。pull 時点から他の更新があれば失敗）
# 運用リポジトリ（private）のチェックアウト直下で実行する。GitHub Actions では concurrency で直列化される。
set -euo pipefail
cmd="${1:?pull|push}"; dir="${2:?dir}"
br="${STATE_BRANCH:-fanza-state}"
tmp="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
base_file="$tmp/fanza-state-base"
gitdir="$(git rev-parse --absolute-git-dir)"

case "$cmd" in
  pull)
    mkdir -p "$dir"
    if git ls-remote --exit-code --heads origin "$br" >/dev/null 2>&1; then
      git fetch -q --depth 1 origin "refs/heads/$br"
      git rev-parse FETCH_HEAD > "$base_file"
      git archive FETCH_HEAD | tar -x -C "$dir"
      echo "state: restored $(git rev-parse --short FETCH_HEAD) → $dir"
    else
      : > "$base_file"
      echo "state: branch $br not found, starting empty"
    fi
    ;;
  push)
    [ -d "$dir" ] || { echo "state: $dir がありません"; exit 0; }
    for db in "$dir"/*.sqlite3; do
      [ -f "$db" ] || continue
      python3 - "$db" <<'PY'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1]); c.execute("PRAGMA wal_checkpoint(TRUNCATE)"); c.close()
PY
      rm -f "$db-wal" "$db-shm"
    done
    export GIT_INDEX_FILE="$tmp/fanza-state.index"
    rm -f "$GIT_INDEX_FILE"
    GIT_DIR="$gitdir" GIT_WORK_TREE="$dir" git -C "$dir" add -A -f .
    tree="$(GIT_DIR="$gitdir" git write-tree)"
    unset GIT_INDEX_FILE
    commit="$(GIT_AUTHOR_NAME=fanza-ops GIT_AUTHOR_EMAIL=fanza-ops@users.noreply.github.com \
              GIT_COMMITTER_NAME=fanza-ops GIT_COMMITTER_EMAIL=fanza-ops@users.noreply.github.com \
              git commit-tree "$tree" -m "state $(date -u +%Y-%m-%dT%H:%M:%SZ)")"
    base="$(cat "$base_file" 2>/dev/null || true)"
    if [ -n "$base" ]; then
      git push -q --force-with-lease="refs/heads/$br:$base" origin "$commit:refs/heads/$br"
    else
      git push -q origin "$commit:refs/heads/$br"
    fi
    echo "$commit" > "$base_file"
    echo "state: saved $(git rev-parse --short "$commit") ($(du -sh "$dir" | cut -f1))"
    ;;
  *) echo "usage: $0 pull|push <dir>"; exit 2 ;;
esac
