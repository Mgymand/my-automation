#!/bin/bash
# =============================================================================
#  孫LOVE かんたんセットアップ（Google Cloud Shell 用・対話式）
#
#  使い方: Google Cloud Console 右上の「Cloud Shell をアクティブにする」を押し、
#          開いた黒い画面に次の1行を貼り付けて Enter:
#
#    bash <(curl -fsSL https://raw.githubusercontent.com/Mgymand/my-automation/main/mago-love/setup-cloudshell.sh)
#
#  質問に答えるだけで Cloud Run（無料枠）にデプロイし、Googleログインまで設定します。
#  何度実行しても安全です（2回目以降は設定の更新だけ行います）。
# =============================================================================
set -euo pipefail

REPO_URL="https://github.com/Mgymand/my-automation.git"
REGION="${REGION:-asia-northeast1}"      # 東京
SERVICE="${SERVICE:-mago-love}"
WORK_DIR="$HOME/mago-love-deploy"

say()  { printf "\n\033[1;35m%s\033[0m\n" "$*"; }
info() { printf "\033[0;36m%s\033[0m\n" "$*"; }
warn() { printf "\033[0;33m%s\033[0m\n" "$*"; }
ask()  { local __var="$1" __prompt="$2" __default="${3:-}"; local __in; read -r -p "$__prompt${__default:+ [$__default]}: " __in; printf -v "$__var" '%s' "${__in:-$__default}"; }

say "=============================================="
say "  孫LOVE セットアップを始めます"
say "=============================================="

# ---- 0. gcloud / アカウント -------------------------------------------------
if ! command -v gcloud >/dev/null; then
  echo "gcloud が見つかりません。Google Cloud Shell で実行してください。"; exit 1
fi
ACCOUNT="$(gcloud config get-value account 2>/dev/null || true)"
if [ -z "$ACCOUNT" ]; then
  gcloud auth login --brief
  ACCOUNT="$(gcloud config get-value account 2>/dev/null)"
fi
info "ログイン中のアカウント: $ACCOUNT"

# ---- 1. プロジェクト ---------------------------------------------------------
say "【1/5】使う Google Cloud プロジェクトを選びます"
gcloud projects list --format="table(projectId,name)" 2>/dev/null || true
CUR="$(gcloud config get-value project 2>/dev/null || true)"
ask PROJECT_ID "プロジェクトID を入力（上の一覧の projectId 列）" "$CUR"
[ -n "$PROJECT_ID" ] || { echo "プロジェクトIDが空です"; exit 1; }
gcloud config set project "$PROJECT_ID" >/dev/null

if ! gcloud beta billing projects describe "$PROJECT_ID" --format="value(billingEnabled)" 2>/dev/null | grep -q True; then
  warn "このプロジェクトは請求先アカウントが未設定の可能性があります。"
  warn "https://console.cloud.google.com/billing/linkedaccount?project=$PROJECT_ID で紐づけてから再実行してください。"
  ask CONT "無視して続けますか？ (y/N)" "N"
  [[ "$CONT" =~ ^[yY]$ ]] || exit 1
fi

# ---- 2. 管理者メール ---------------------------------------------------------
say "【2/5】最初の管理者（あなた）のメールアドレス"
ask ADMIN_EMAIL "管理者メール（Googleログインに使うアドレス）" "$ACCOUNT"

# ---- 3. 必要なAPIとバケット --------------------------------------------------
say "【3/5】必要な機能を有効化しています（1〜2分かかります）"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  storage.googleapis.com aiplatform.googleapis.com texttospeech.googleapis.com --project "$PROJECT_ID" >/dev/null
BUCKET="${PROJECT_ID}-mago-love-data"
if ! gcloud storage buckets describe "gs://$BUCKET" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://$BUCKET" --project "$PROJECT_ID" --location "$REGION" \
    --uniform-bucket-level-access >/dev/null
  info "データ保存用バケットを作成: gs://$BUCKET"
else
  info "データ保存用バケットは作成済み: gs://$BUCKET"
fi

# ---- 3b. ビルド/実行用サービスアカウントに権限を付与 ------------------------------
# 新しいプロジェクトでは標準サービスアカウントに権限が自動付与されないため、
# ソースからのビルド（Cloud Build）とデータ用バケットへのアクセスに必要な役割を明示的に付ける。
say "【3/5】ビルド用サービスアカウントの権限を設定しています"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")"
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
gcloud services enable compute.googleapis.com iam.googleapis.com --project "$PROJECT_ID" >/dev/null 2>&1 || true
for ROLE in roles/cloudbuild.builds.builder roles/artifactregistry.writer roles/logging.logWriter roles/storage.objectAdmin roles/aiplatform.user; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:$SA" --role "$ROLE" \
    --condition=None --quiet >/dev/null 2>&1 || warn "権限付与に失敗: $ROLE（プロジェクトのオーナー権限が必要です）"
done
info "サービスアカウント $SA に権限を付与しました（反映まで少し待ちます）"
sleep 25

# ---- 4. 最新コードを取得してデプロイ ------------------------------------------
say "【4/5】最新のアプリをデプロイしています（初回は3〜5分かかります）"
rm -rf "$WORK_DIR" && git clone -q --depth 1 "$REPO_URL" "$WORK_DIR"

get_env() {  # 既存サービスの環境変数を取得（無ければ空）
  gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT_ID" --format=json 2>/dev/null \
    | python3 -c "import json,sys
d=json.load(sys.stdin)
env=d['spec']['template']['spec']['containers'][0].get('env',[])
print(next((e.get('value','') for e in env if e.get('name')=='$1'),''))" 2>/dev/null || true
}
EXISTING_CLIENT_ID="$(get_env GOOGLE_CLIENT_ID)"
EXISTING_CRON="$(get_env CRON_TOKEN)"
GOOGLE_CLIENT_ID="${EXISTING_CLIENT_ID:-pending}"     # 未設定の間は開発用ログインを無効化するためのダミー
CRON_TOKEN="${EXISTING_CRON:-$(openssl rand -hex 24)}"

gcloud run deploy "$SERVICE" \
  --project "$PROJECT_ID" --region "$REGION" \
  --source "$WORK_DIR/mago-love" \
  --allow-unauthenticated --execution-environment gen2 \
  --max-instances 1 --memory 1Gi --timeout 300 \
  --add-volume "name=data,type=cloud-storage,bucket=$BUCKET" \
  --add-volume-mount "volume=data,mount-path=/var/data" \
  --set-env-vars "MAGO_DATA_DIR=/var/data,TRUST_PROXY=1,ADMIN_EMAIL=$ADMIN_EMAIL,GOOGLE_CLIENT_ID=$GOOGLE_CLIENT_ID,CRON_TOKEN=$CRON_TOKEN" \
  --quiet

URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --format "value(status.url)")"
gcloud run services update "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --update-env-vars "APP_URL=$URL" --quiet >/dev/null
info "アプリのURL: $URL"

# ---- 5. Googleログイン（OAuthクライアントID） --------------------------------
say "【5/5】Googleログインの鍵（OAuth クライアントID）を設定します"
if [ "$GOOGLE_CLIENT_ID" = "pending" ] || [[ ! "$GOOGLE_CLIENT_ID" =~ apps\.googleusercontent\.com$ ]]; then
  cat <<EOS

  ブラウザの別タブで次の手順を行ってください（約5分）。

  A. OAuth 同意画面（初回のみ）
     https://console.cloud.google.com/auth/overview?project=$PROJECT_ID
     ・「開始」→ アプリ名: 孫LOVE / サポートメール: $ADMIN_EMAIL
     ・対象: 「内部」（Google Workspace の場合。社内アカウントだけ許可）
             Workspace でなければ「外部」を選び、あとで「対象 → テストユーザー」に各自のGmailを追加
     ・連絡先メール: $ADMIN_EMAIL → 同意して「作成」

  B. クライアントIDの作成
     https://console.cloud.google.com/apis/credentials?project=$PROJECT_ID
     ・「＋ 認証情報を作成」→「OAuth クライアント ID」
     ・アプリケーションの種類: 「ウェブ アプリケーション」
     ・名前: 孫LOVE
     ・「承認済みの JavaScript 生成元」→「＋ URI を追加」に次を貼り付け:
           $URL
     ・「作成」→ 表示される「クライアント ID」（末尾が .apps.googleusercontent.com）をコピー
       ※ クライアント シークレットは使いません。閉じて構いません。

EOS
  while :; do
    ask GOOGLE_CLIENT_ID "コピーした クライアントID を貼り付けて Enter（あとで設定する場合は空のまま Enter）" ""
    [ -z "$GOOGLE_CLIENT_ID" ] && break
    [[ "$GOOGLE_CLIENT_ID" =~ ^[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com$ ]] && break
    warn "形式が違うようです（例: 123456789012-abcdefg.apps.googleusercontent.com）。もう一度貼り付けてください。"
  done
  if [ -n "$GOOGLE_CLIENT_ID" ]; then
    gcloud run services update "$SERVICE" --project "$PROJECT_ID" --region "$REGION" \
      --update-env-vars "GOOGLE_CLIENT_ID=$GOOGLE_CLIENT_ID" --quiet >/dev/null
    info "Googleログインを有効化しました。"
  else
    warn "Googleログインは未設定です。設定するときはこのスクリプトをもう一度実行してください。"
  fi
else
  info "Googleログインは設定済みです（$GOOGLE_CLIENT_ID）。"
fi

say "=============================================="
say "  セットアップ完了！"
say "=============================================="
cat <<EOS
  アプリURL（スマホ・PCどちらでも）: $URL
  ログイン: $ADMIN_EMAIL の Google アカウント

  次にやること（アプリ内の「設定・連携」画面）:
   1. パートナーキャラの画像4枚をアップロード → 「表情を生成」で笑顔・驚きなどのバリエーションを自動生成
      （Vertex AI の画像モデルを使用。1枚あたり数円がプロジェクトに課金されます）
   2. Slack の Webhook URL を貼り付けて「テスト送信」
   3. Google ドライブのルートフォルダURLを登録
   4. 「ユーザー」で同僚のメールを招待

  毎朝のSlackリマインドを有効にする場合は、GitHub リポジトリの Settings → Secrets に:
     MAGO_APP_URL   = $URL
     MAGO_CRON_TOKEN = $CRON_TOKEN

  更新版を反映したいときは、このスクリプトをもう一度実行するだけです。
EOS
