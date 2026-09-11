# 孫LOVE デプロイ手順（無料運用）

## 方針: Render は解約 → Google Cloud Run（無料枠）

| 項目 | Cloud Run + Cloud Storage | 備考 |
| --- | --- | --- |
| 月額 | **0円**（無料枠: リクエスト200万/月、Cloud Storage 5GB） | 社内利用の規模なら枠内に収まります |
| データ永続化 | GCS バケットを `/var/data` にマウント | JSON・PDF・キャラ画像をそのまま保存 |
| 起動 | リクエスト時に起動（コールドスタート数秒） | 最小インスタンス0で課金なし |
| 既存 | `property-map`（営業クラウド）と同じ方式 | 同じプロジェクトで運用可 |

Render の Starter（$7/月）は永続ディスクのためだけに必要でした。Cloud Run では GCS が無料枠に収まるため不要です。
**Render 解約手順**: Render ダッシュボード → 対象サービス → Settings → Delete Web Service（Disk も削除）。解約前に `/var/data` のJSONをダウンロードして GCS バケットへコピーすればデータも引き継げます。

### 他の無料候補（参考）
- **Oracle Cloud Always Free（VM）**: 完全無料で常時起動できるが、サーバー運用（OS更新・HTTPS）が必要
- **PythonAnywhere Free**: 永続ディスクありだが外部API接続がホワイトリスト制（国土地理院・Slack が使えない可能性）
- **Vercel / Netlify / Koyeb Free**: 永続ディスクなし（JSON保存方式と相性が悪い）

→ 運用の手間と自由度から Cloud Run を推奨します。

## Cloud Run デプロイ

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

デプロイ後、アプリの **設定・連携** で Slack Webhook / アプリURL / ZENRIN / Google API キー / キャラ画像を設定します。

## スマホ対応
レスポンシブ対応済み（ボトムナビ・ドロワー全画面）。iPhone / Android は Chrome / Safari で URL を開き「ホーム画面に追加」するとアプリのように使えます。

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
