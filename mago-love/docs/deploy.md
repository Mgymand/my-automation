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

## いちばん簡単な方法: Cloud Shell で対話式セットアップ（推奨・PCに何も入れない）

1. https://console.cloud.google.com/ を開き、右上の「Cloud Shell をアクティブにする」（ >_ のアイコン）を押す
2. 画面下に黒い端末が開いたら、次の1行を貼り付けて Enter

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Mgymand/my-automation/main/mago-love/setup-cloudshell.sh)
```

3. 質問（プロジェクトID・管理者メール）に答えると自動でデプロイされ、最後に Google ログイン用クライアントIDの作り方が表示される
4. 表示された手順どおりにクライアントIDを作って貼り付ければ完了。アプリURLが表示される

Googleログインが未設定の間は、誰もログインできない状態（安全側）で公開されます。
アプリを更新したいときも同じ1行を実行するだけです。

## 手動でデプロイする場合（gcloud をPCに入れている人向け）

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


## 画像・動画・音声の生成に使う API
- 画像（表情・背景・場面画像）: Vertex AI（`aiplatform.googleapis.com`）。実行サービスアカウントに `roles/aiplatform.user`
- 動画（待機ループ・会話クリップ）: 同じ Vertex AI の Veo（環境変数 `VIDEO_MODEL`、既定 `veo-3.0-fast-generate-001`。`VIDEO_SECONDS` で秒数）。1本 1〜3 分かかるためサーバー側でキューにして順番に実行し、設定画面が 5 秒ごとに進捗を取得します
- 声: Cloud Text-to-Speech（`texttospeech.googleapis.com`）。setup-cloudshell.sh が有効化します。無料枠内で十分。使えない場合はブラウザ読み上げに自動で切り替わります
- Cloud Run のリクエストタイムアウトは 300 秒に設定しています（setup-cloudshell.sh）
