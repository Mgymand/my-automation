# 営業クラウドをGoogle Cloud（Cloud Run）で24時間稼働させる

WEC（Firebase）と同じGoogleの基盤で動かします。Python製のこのツールの場合、
Firebaseファミリーでの実行先は **Cloud Run**、データ保存は **Cloud Storage** です。

- 費用: この規模なら **ほぼ0円〜数百円/月**（リクエストが無い時間は自動停止、無料枠が大きい）
- URL: `https://eigyo-cloud-xxxxx.run.app` 形式（独自ドメインも設定可）
- GitHubのコード更新を反映したい時は `deploy-cloudrun.sh` を再実行するだけ

## あなたにお願いする操作（初回のみ・約5分）

1. **gcloudにログイン**（ターミナルで実行。ブラウザが開くのでGoogleアカウントで許可）
   ```
   gcloud auth login
   ```

2. **プロジェクトの選択（または作成）と課金の有効化**
   - 既存プロジェクト（OAuthクライアントを作った `624593039655` のプロジェクト）を使うのが楽です:
     ```
     gcloud projects list
     gcloud config set project <そのPROJECT_ID>
     ```
   - 課金が未設定なら https://console.cloud.google.com/billing でプロジェクトに請求先を紐付け
     （無料枠内でも紐付け自体は必要です）

3. ここまで終えたらClaude（私）に「ログインしました」と言ってください。
   **デプロイの実行・動作確認は私がやります。**

## 私（または手動）が実行するデプロイコマンド

```
cd ~/projects/my-automation
GOOGLE_CLIENT_ID=624593039655-…apps.googleusercontent.com \
ANTHROPIC_API_KEY=（property-map/.envの値） \
./deploy-cloudrun.sh
```

スクリプトが行うこと:
- 必要なAPI（Cloud Run / Cloud Build / Artifact Registry）の有効化
- データ永続化用のCloud Storageバケット作成（`<project>-eigyo-data`）
- ソースから自動ビルドしてCloud Runへデプロイ（東京リージョン）
  - `/var/data` にバケットをマウント → ユーザー・物件・顧客・提案データが永続化
  - `max-instances 1`（JSONファイル保存の整合性のため。チーム規模なら十分）
  - 初回起動時に `ADMIN_EMAIL` がオーガナイザーとして自動登録

## デプロイ後の1手（必須）

発行されたURL（例: `https://eigyo-cloud-xxxxx.run.app`）を
Google OAuthクライアントの **「承認済みのJavaScript生成元」** に追加
→ https://console.cloud.google.com/apis/credentials

## 将来の発展

- WECとの統合時はデータ層をFirestoreへ移行（load/save関数が一箇所に集約済みなので移行は局所的）
- 独自ドメイン: Cloud Run → カスタムドメインマッピングで `cloud.gt-works.net` 等を設定可能
