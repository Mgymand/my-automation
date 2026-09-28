#!/usr/bin/env bash
# Phase 4: 実認証・実 API での初回 E2E を一括実行し、各ステップの結果を data/phase4_e2e.log に残す。
# 前提: 環境変数（または fanza-affiliate/.env）に DMM_API_ID / DMM_AFFILIATE_ID / ANTHROPIC_API_KEY（任意: X_BEARER_TOKEN / X_USERNAME）
# Secret は出力しない。X への投稿は行わない（READ ONLY）。
set -uo pipefail
cd "$(dirname "$0")/.."
export DATA_DIR="${DATA_DIR:-$(pwd)/data}"
mkdir -p "$DATA_DIR"
LOG="$DATA_DIR/phase4_e2e.log"
: > "$LOG"
step() { echo "=== $1" | tee -a "$LOG"; }
run() { if "$@" >> "$LOG" 2>&1; then echo "  OK: $*" | tee -a "$LOG"; else echo "  FAIL($?): $*" | tee -a "$LOG"; fi; }

step "0. 疎通（bootstrap --check はネットワークあり・書込なし）"
run python -m affiliate_bot bootstrap --check
step "1. 実商品取得（ランキング / 新着 / レビュー順 × 2 ページ = 最大 600 件、content_id で重複除去）"
run python -m affiliate_bot fetch-products --sorts rank,date,review --pages 2 --hits 100
step "2. 市場調査（X READ があれば収集、無ければ --import-csv を使う）"
if [ -n "${X_BEARER_TOKEN:-}" ]; then run python -m affiliate_bot research --collect --analyze --per-query 100; else echo "  SKIP collect（X_BEARER_TOKEN なし）→ research --import-csv <file> --analyze を手動で" | tee -a "$LOG"; fi
step "3. 本日の投稿パッケージ 5 件"
run python -m affiliate_bot plan
step "4. 表示 / エクスポート"
run python -m affiliate_bot today
run python -m affiliate_bot export
step "5. 学習・レポート・検知・ステータス（コスト含む）"
run python -m affiliate_bot learn
run python -m affiliate_bot report --no-llm
run python -m affiliate_bot checks
run python -m affiliate_bot attention
run python -m affiliate_bot status
echo "ログ: $LOG"
echo "次: Web UI は WEB_TOKEN を設定して 'python -m affiliate_bot serve'。投稿後は 'posted --url <X URL>'。24h/72h 後に 'metrics'。成果 CSV は 'ingest-conversions --csv'。"
