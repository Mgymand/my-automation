#!/bin/bash
# 孫LOVE を Google Cloud Run にデプロイするスクリプト（無料枠での運用を想定）
# 前提: gcloud auth login 済み / 課金有効なプロジェクトを選択済み
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-asia-northeast1}"            # 東京
SERVICE="${SERVICE:-mago-love}"
BUCKET="${BUCKET:-${PROJECT_ID}-mago-love-data}"
ADMIN_EMAIL="${ADMIN_EMAIL:?ADMIN_EMAIL を環境変数で渡してください}"
GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID:?GOOGLE_CLIENT_ID を環境変数で渡してください}"
CRON_TOKEN="${CRON_TOKEN:-$(openssl rand -hex 24)}"
ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "== プロジェクト: ${PROJECT_ID} / リージョン: ${REGION}"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com --project "${PROJECT_ID}"

echo "== データ用バケット（存在すればスキップ）"
gcloud storage buckets describe "gs://${BUCKET}" --project "${PROJECT_ID}" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://${BUCKET}" --project "${PROJECT_ID}" \
    --location "${REGION}" --uniform-bucket-level-access

echo "== Cloud Run にデプロイ"
gcloud run deploy "${SERVICE}" \
  --project "${PROJECT_ID}" --region "${REGION}" \
  --source "${SRC_DIR}" \
  --allow-unauthenticated \
  --max-instances 1 --memory 1Gi \
  --add-volume "name=data,type=cloud-storage,bucket=${BUCKET}" \
  --add-volume-mount "volume=data,mount-path=/var/data" \
  --set-env-vars "MAGO_DATA_DIR=/var/data,TRUST_PROXY=1,ADMIN_EMAIL=${ADMIN_EMAIL},GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID},CRON_TOKEN=${CRON_TOKEN},ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}"

URL=$(gcloud run services describe "${SERVICE}" --project "${PROJECT_ID}" \
  --region "${REGION}" --format "value(status.url)")
gcloud run services update "${SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" \
  --update-env-vars "APP_URL=${URL}" >/dev/null
echo ""
echo "============================================================"
echo "  デプロイ完了: ${URL}"
echo "  1) Google OAuth の承認済みJavaScript生成元に ${URL} を追加"
echo "  2) 毎朝のSlackリマインド用 CRON_TOKEN: ${CRON_TOKEN}"
echo "     GitHub Secrets: MAGO_APP_URL=${URL} / MAGO_CRON_TOKEN=${CRON_TOKEN}"
echo "============================================================"
