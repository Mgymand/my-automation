# 営業クラウドを24時間稼働させる（Renderデプロイ手順）

Macを閉じていても全員がブラウザから使える状態にします。
リポジトリに `render.yaml`（設計図）をコミット済みなので、Render側の操作は約10分です。

費用: Starterプラン **$7/月** ＋ ディスク1GB **$0.25/月**（無料プランは再起動でデータが消えるため不可）

## 手順

1. **Renderアカウント作成**
   https://render.com → 「Get Started」→ **GitHubアカウント（Mgymand）でサインアップ**

2. **Blueprintデプロイ**
   ダッシュボード → **New → Blueprint** → `Mgymand/my-automation` を選択 → 「Apply」
   （`render.yaml` が自動で読み込まれ、`eigyo-cloud` というWebサービスが作られます）

3. **環境変数を2つ入力**（Apply時に入力を求められます）
   - `ANTHROPIC_API_KEY` … property-map/.env にあるキーと同じ値
   - `GOOGLE_CLIENT_ID` … `624593039655-….apps.googleusercontent.com`

4. **デプロイ完了を待つ**（3〜5分）
   発行されるURL: `https://eigyo-cloud.onrender.com`（数字付きになる場合あり。ダッシュボードに表示）

5. **Google OAuthに本番URLを追加**（これをしないとGoogleログインが弾かれます）
   https://console.cloud.google.com/apis/credentials → 該当のOAuthクライアント →
   「承認済みの JavaScript 生成元」に発行されたURL（例: `https://eigyo-cloud.onrender.com`）を追加 → 保存
   ※反映に数分かかることがあります

6. **ログイン確認**
   `https://eigyo-cloud.onrender.com/login` → Googleでログイン
   初回起動時に `gtiwamoto@gmail.com` がオーガナイザーとして自動登録されています（ADMIN_EMAIL）。
   あとは /ogn からスタッフ・加盟店を招待するだけです。

## 仕組みメモ

- データ（ユーザー・物件・顧客・提案・チャット等）は永続ディスク `/var/data` に保存。
  デプロイし直しても消えません
- GitHubの `main` にpushすると**自動で再デプロイ**されます（コード更新の反映が楽）
- ローカルの `property-map/data/` のサンプルデータは本番には持ち込まれません。
  本番は ADMIN_EMAIL のオーガナイザー1人から始まります（必要なら後でデータ移行可能）
- 旧ツール（物件マップ・マイソク結合）も本番ではログイン必須にしてあります
- 独自ドメイン（例: cloud.gt-works.net）を使いたい場合はRenderの
  Settings → Custom Domains で追加し、DNSにCNAMEを1行足すだけです
