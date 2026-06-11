# Googleログインの有効化手順（営業クラウド）

現在は**開発用ログイン**で動作しています。以下の手順でWeb用のOAuth Client IDを発行し、
`.env` に1行追加するだけで本物のGoogleログインに切り替わります（コード変更不要）。

所要時間: 約5分。Chrome拡張用のClient ID（`790046521944-…`）と同じGoogle Cloud
プロジェクトに追加発行できます（拡張用IDはWebログインには使えません）。

## 手順

1. https://console.cloud.google.com/apis/credentials を開く
   （Chrome拡張で使っているプロジェクトを選択。新規プロジェクトでも可）

2. 「＋認証情報を作成」→「OAuth クライアント ID」を選択
   - 初回は「OAuth 同意画面」の設定を求められます:
     - User Type: **内部**（Google Workspace利用時。社内のみログイン可で最も安全）
       または **外部**（個人Gmailを使う場合。テストユーザーに各メールを追加）
     - アプリ名: 営業クラウド（任意）

3. アプリケーションの種類: **ウェブ アプリケーション**
   - 名前: 営業クラウド（任意）
   - **承認済みの JavaScript 生成元** に以下を追加:
     - `http://localhost:5000`
     - `http://127.0.0.1:5000`
     - 本番公開時はそのURL（例: `https://example.com`）も追加
   - リダイレクトURIは不要（Google Identity Servicesのポップアップ方式のため）

4. 作成すると `xxxxxxxx.apps.googleusercontent.com` 形式のClient IDが表示される

5. `property-map/.env` に追記（**Client IDは公開情報なので貼ってOK**。
   「クライアント シークレット」はこの方式では使いません）:

   ```
   GOOGLE_CLIENT_ID=xxxxxxxx.apps.googleusercontent.com
   ```

6. サーバを再起動 → ログイン画面が自動でGoogleボタンに切り替わり、
   開発用ログインは**自動的に無効化**されます

## ログインできる人の管理

- ログインできるのは **オーガナイズ画面（/ogn）の「ユーザー」表に登録した
  メールアドレスのみ**（招待制）。未登録のGoogleアカウントは拒否されます。
- 最初に `data/users.json` の `owner@example.com` を**ご自身のGmailに書き換えて**
  ください（そうしないと誰もオーガナイズ画面に入れません）。

## 役割と画面

| 役割 | 画面 | できること |
|---|---|---|
| オーガナイズ（ogn） | /ogn | 最上位。ユーザー招待・権限変更・加盟店追加＋下位画面すべて |
| 管理（admin） | /admin | 全店舗横断のダッシュボード（活動量・提案履歴） |
| 加盟店（store） | /portal | 自店の物件・顧客・提案のみ操作可能 |
