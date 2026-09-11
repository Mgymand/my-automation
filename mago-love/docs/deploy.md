# 孫LOVE デプロイ手順

「基本無料」で運用する前提の2案です。

| 案 | 月額 | データ永続化 | 備考 |
| --- | --- | --- | --- |
| **A. Google Cloud Run + Cloud Storage（推奨）** | 無料枠内でほぼ0円 | GCS バケットをマウント | 東京リージョン。既存の `property-map` と同じ方式 |
| B. Render | Starter $7（Free はディスク無しで再起動時にデータ消失） | Render Disk | Blueprint (`render.yaml`) で一発 |

## A. Cloud Run（推奨）

前提: `gcloud auth login` 済み、課金有効（無料枠内で運用）。

```bash
export GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com   # Googleログイン
export ADMIN_EMAIL=you@example.com
export CRON_TOKEN=$(openssl rand -hex 24)
./mago-love/deploy-cloudrun.sh
```

スクリプトが行うこと:
1. Cloud Run / Cloud Build / Artifact Registry API を有効化
2. データ用バケット `${PROJECT_ID}-mago-love-data` を作成（存在すればスキップ）
3. `mago-love/` をソースからビルドし、バケットを `/var/data` にマウントしてデプロイ
4. 出力された URL を Google OAuth の「承認済みの JavaScript 生成元」に追加

デプロイ後、アプリの **設定・連携** で Slack Webhook / アプリURL / ZENRIN / Google API キーを入力します。

## B. Render

1. Render → New → Blueprint → このリポジトリを選択 → `render.yaml` の `mago-love` サービスを Apply
2. ダッシュボードで `GOOGLE_CLIENT_ID`（と任意で `ANTHROPIC_API_KEY`）を入力
3. 発行された URL を Google OAuth の承認済み生成元に追加

## 毎朝のSlackリマインド（無料cron）

### GitHub Actions（このリポジトリ）
`.github/workflows/mago-love-digest.yml` が毎朝 8:00 JST に `/api/cron/digest` を叩きます。
リポジトリの Secrets に以下を登録してください。

- `MAGO_APP_URL` … 例 `https://mago-love-xxxx.a.run.app`
- `MAGO_CRON_TOKEN` … `CRON_TOKEN` と同じ値（または設定画面の cron トークン）

### cron-job.org
`GET https://<アプリURL>/api/cron/digest?token=<CRON_TOKEN>` を毎日 8:00 に登録。

## Google ログイン
[docs/google-login-setup.md](../../docs/google-login-setup.md) の手順で OAuth クライアントID（ウェブ）を作成し、`GOOGLE_CLIENT_ID` に設定します。
Drive Picker / フォルダ作成も同じクライアントIDを使います（Google Cloud Console で **Google Picker API** と **Google Drive API** を有効化し、APIキーを作成して設定画面に入力）。
