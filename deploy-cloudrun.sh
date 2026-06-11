#!/bin/bash
# 営業クラウドを Google Cloud Run にデプロイするスクリプト
# 前提: gcloud auth login 済み / 課金有効なプロジェクトを選択済み
set -euo pipefail

# ====== 設定（必要に応じて変更） ======
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-asia-northeast1}"            # 東京
SERVICE="${SERVICE:-eigyo-cloud}"
BUCKET="${BUCKET:-${PROJECT_ID}-eigyo-data}"   # データ永続化用バケット
ADMIN_EMAIL="${ADMIN_EMAIL:-gtiwamoto@gmail.com}"
GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID:?GOOGLE_CLIENT_ID を環境変数で渡してください}"
ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY を環境変数で渡してください}"
# =====================================

echo "== プロジェクト: ${PROJECT_ID} / リージョン: ${REGION}"

echo "== 必要なAPIを有効化"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com --project "${PROJECT_ID}"

echo "== データ用バケットを作成（存在すればスキップ）"
gcloud storage buckets describe "gs://${BUCKET}" --project "${PROJECT_ID}" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://${BUCKET}" \
    --project "${PROJECT_ID}" --location "${REGION}" \
    --uniform-bucket-level-access

echo "== Cloud Run にデプロイ（ソースから自動ビルド）"
gcloud run deploy "${SERVICE}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --source property-map \
  --allow-unauthenticated \
  --max-instances 1 \
  --memory 1Gi \
  --add-volume "name=data,type=cloud-storage,bucket=${BUCKET}" \
  --add-volume-mount "volume=data,mount-path=/var/data" \
  --set-env-vars "PROPERTY_DATA_DIR=/var/data,TRUST_PROXY=1,ADMIN_EMAIL=${ADMIN_EMAIL},GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID},ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}"

URL=$(gcloud run services describe "${SERVICE}" --project "${PROJECT_ID}" \
  --region "${REGION}" --format "value(status.url)")
echo ""
echo "============================================================"
echo "  デプロイ完了: ${URL}"
echo "  次の1手: Google OAuth の承認済みJavaScript生成元に"
echo "           ${URL} を追加してください"
echo "============================================================"
