# 店舗開発部 業務管理システム - 導入セットアップガイド

## 作成済みリソース

| リソース | URL |
|---|---|
| スプレッドシート | https://docs.google.com/spreadsheets/d/1wYjuh2jcbbhT2hPtpLI9FdbBfyXAh5zxrqvAW9BuQao |
| GASエディタ | https://script.google.com/d/1b0P7tvLhsMf8HGkFs9dDBNOMdjI33T_KWL9yqmrYmSfWhYNVgihFvZg-/edit |

---

## 1. Slack App 設定手順

### 1-1. Slack App 作成
1. https://api.slack.com/apps にアクセス
2. 「Create New App」→「From scratch」をクリック
3. App Name: `店舗開発BMS`
4. Workspace: `lime-drr1011` を選択
5. 「Create App」をクリック

### 1-2. Bot Token Scopes 設定
1. 左メニュー「OAuth & Permissions」をクリック
2. 「Scopes」セクション → 「Bot Token Scopes」に以下を追加:
   - `chat:write` （メッセージ送信）
   - `commands` （スラッシュコマンド）
   - `incoming-webhook` （Webhook投稿）
3. ページ上部「Install to Workspace」→「許可する」
4. **Bot User OAuth Token** (`xoxb-...`) をコピー → 後で使用

### 1-3. Incoming Webhooks 設定
1. 左メニュー「Incoming Webhooks」→ ON に切替
2. 「Add New Webhook to Workspace」をクリック
3. 以下のチャンネルを新規作成してそれぞれWebhookを生成:

| チャンネル名 | 用途 |
|---|---|
| `#store-dev-daily` | 日報サマリー投稿 |
| `#store-dev-tasks` | タスク通知 |
| `#store-dev-alerts` | アラート・エスカレーション |

4. 各Webhook URLをコピー → 後で使用

### 1-4. Slash Commands 設定
1. 左メニュー「Slash Commands」をクリック
2. 以下の4つのコマンドを作成:

| コマンド | Request URL | 説明 |
|---|---|---|
| `/task` | `{GAS WebApp URL}` | タスク登録 |
| `/cal` | `{GAS WebApp URL}` | カレンダー登録 |
| `/report` | `{GAS WebApp URL}` | 日報確認 |
| `/status` | `{GAS WebApp URL}` | 記入状況確認 |

**GAS WebApp URLの取得方法:**
1. GASエディタ（上記URL）を開く
2. 「デプロイ」→「新しいデプロイ」
3. 種類: 「ウェブアプリ」
4. 次のユーザーとして実行: 「自分」
5. アクセスできるユーザー: 「全員」
6. 「デプロイ」→ URLをコピー

### 1-5. Botをチャンネルに招待
各チャンネルで以下を実行:
```
/invite @店舗開発BMS
```

### 1-6. GASにキーを登録
スプレッドシートを開き:
1. メニュー「業務管理システム」→「管理」→「API設定」
2. 以下を入力して「保存」:
   - **Slack Bot Token**: `xoxb-...`（1-2でコピーしたもの）
   - **Slack Webhook URL (日報)**: `#store-dev-daily` のWebhook URL
   - **Slack Webhook URL (タスク)**: `#store-dev-tasks` のWebhook URL

---

## 2. Anthropic API キー取得手順

### 2-1. アカウント確認・作成
1. https://console.anthropic.com にアクセス
2. 既存アカウントでログイン、またはSign Upで新規作成

### 2-2. APIキー発行
1. ログイン後、左メニュー「API Keys」をクリック
2. 「Create Key」をクリック
3. Name: `store-dev-bms` と入力
4. 「Create Key」→ 表示される `sk-ant-api03-...` をコピー
5. **このキーは一度しか表示されません。必ずコピーして安全に保管してください。**

### 2-3. GASに登録
スプレッドシートのメニュー「業務管理システム」→「管理」→「API設定」:
- **Anthropic API Key**: `sk-ant-...`（上でコピーしたもの）

### 2-4. 料金について
- Claude Sonnet: 入力$3 / 出力$15 per 1M tokens
- 月次評価（11名）: 1回あたり約$0.5〜$1程度
- 月1回実行なので月額コストは非常に低い

---

## 3. Salesforce Connected App 設定手順

### 3-1. Connected App 作成
1. Salesforce にログイン（Enterprise エディション）
2. 「設定」→ クイック検索で「アプリケーションマネージャ」を検索
3. 「新規接続アプリケーション」をクリック
4. 以下を入力:
   - **接続アプリケーション名**: `店舗開発BMS`
   - **API参照名**: `Store_Dev_BMS`
   - **取引先責任者メール**: あなたのメールアドレス

### 3-2. OAuth 設定
1. 「OAuth設定の有効化」にチェック
2. **コールバック URL**: `https://login.salesforce.com/services/oauth2/callback`
3. **選択した OAuth 範囲** に以下を追加:
   - `データへのアクセスと管理 (api)`
   - `いつでも要求を実行 (refresh_token, offline_access)`
4. 「保存」→ 「続行」

### 3-3. コンシューマキー取得（2〜10分待機）
1. 「設定」→「アプリケーションマネージャ」→ 作成したアプリの「管理」
2. 「コンシューマの詳細を管理」をクリック
3. 以下をコピー:
   - **コンシューマキー** (Client ID)
   - **コンシューマシークレット** (Client Secret)

### 3-4. セキュリティトークン取得
1. Salesforceの「私の設定」→「個人」→「私のセキュリティトークンのリセット」
2. メールで届くセキュリティトークンをコピー

### 3-5. GASに登録
GASエディタで以下のスクリプトを実行して設定:
```javascript
function setupSalesforce() {
  var props = PropertiesService.getScriptProperties();
  props.setProperties({
    'SF_CLIENT_ID': 'ここにコンシューマキー',
    'SF_CLIENT_SECRET': 'ここにコンシューマシークレット',
    'SF_USERNAME': 'あなたのSFユーザー名',
    'SF_PASSWORD': 'あなたのSFパスワード',
    'SF_SECURITY_TOKEN': 'ここにセキュリティトークン'
  });
  Logger.log('Salesforce設定完了');
}
```

---

## 4. 初期セットアップ実行

すべてのAPIキーを登録後、以下の順で実行:

1. スプレッドシートを開く
2. メニュー「業務管理システム」→「初期セットアップ」→ OK
3. **メンバー一覧シート**に11名分のデータを入力:
   | ID | 氏名 | メール | Slackユーザー名 | SlackユーザーID | 役割 | 日報シート名 | ステータス |
   |---|---|---|---|---|---|---|---|
   | 1 | 山田太郎 | yamada@lime-fit.com | yamada | U0XXXXXXX | 一般 | (自動) | 有効 |
4. メニュー「業務管理システム」→「管理」→「メンバーシート一括生成」
5. メニュー「業務管理システム」→「管理」→「トリガー設定」
6. 動作確認: 日報シートに感想を記入し、翌日10:00のSlack投稿を確認

---

## トラブルシューティング

| 症状 | 対処法 |
|---|---|
| カスタムメニューが表示されない | スプレッドシートを再読み込み |
| Slack投稿されない | API設定のWebhook URLを再確認 |
| カレンダー同期エラー | GASの承認画面で全権限を許可 |
| AI評価が空 | Anthropic APIキーを確認、残高を確認 |
| Salesforce接続失敗 | セキュリティトークン再取得、IP制限確認 |
