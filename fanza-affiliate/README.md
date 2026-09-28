# DMM/FANZA アフィリエイト × X 自動運用（営業利益最適化）

X（旧 Twitter）公式 API だけを使って DMM/FANZA の商品を紹介し、
「表示 → 興味 → リンククリック → 遷移 → 購入 → 報酬」のファネル全体を投稿単位で計測、
**営業利益（売上 − AI 費 − API 費 − インフラ費）** を目的関数に探索・活用で配分を最適化するシステムです。

- 設計書: [docs/DESIGN.md](docs/DESIGN.md)（アーキテクチャ / スキーマ / モデル配分 / 日次・週次 / KPI / トラッキング / A/B / フェイルセーフ / コスト）
- 規約・法令確認: [docs/COMPLIANCE.md](docs/COMPLIANCE.md) ← **運用前に必読。人間のチェックリストあり**
- 市場調査: [docs/MARKET_RESEARCH.md](docs/MARKET_RESEARCH.md)

## 最重要: 成人向け商品の X 投稿は HARD BLOCK

X の有料パートナーシップ方針（公式・日本語版で確認）は、**アフィリエイトリンクや割引コードを含む投稿を有料パートナーシップ**とし、
現行の英語版は禁止カテゴリに **「Adult and sexual products and services」「Adult entertainment」** を挙げています。
したがって FANZA の成人向け商品のアフィリエイト投稿は「禁止カテゴリの有料パートナーシップ」に該当し、
本システムは `affiliate_bot/policy.py` の台帳に基づき **設定では解除できないハードブロック** として扱います
（センシティブメディアとして投稿できることと、有料パートナーシップとして宣伝できることは別です）。
運用対象は **DMM.com の一般商品**（動画・電子書籍・PC ゲーム等）です。

## セットアップは 1 コマンド（AI 主導）

```bash
cd fanza-affiliate
python -m affiliate_bot bootstrap
```

`bootstrap` は対話型の初期設定エージェントです。環境・Git・Python・依存・DB・環境変数・DMM・X・Anthropic・
トラッキング・デプロイ・Secret・コンプライアンス・DRY_RUN を自動判定し、不足分だけを順に埋めます。
人間が行うのは **ログイン／2FA／規約同意／課金／API Secret のコピー／審査申請** のような本人操作だけで、
画面には `★ここだけ人間★` として管理画面 URL・押すメニュー・設定値・コピーする値を提示します。

- Secret は `getpass` で入力（画面に出ない）→ `.env`（600, gitignore 済）と利用可能な外部ストア（Google Secret Manager / Vercel env / GitHub Actions）に保存 → 即座に疎通確認（DMM: FloorList, X: `GET /2/users/me`, Anthropic: Models API + 1 トークン）→ 成功したら次工程へ
- Anthropic は Sonnet / Opus / Fable の利用可能性を確認し、使えないモデルは自動で代替へルーティング（運用は止めない）
- DMM の媒体登録に必要な媒体名・URL・説明・運営内容は AI が生成（`data/dmm_media_application.md`）。申請だけ本人操作
- X Developer の App 設定（OAuth 1.0a / Read and write / Callback / Website URL）と発行手順を提示し、4 つのキーを疎通確認
- トラッキング URL は人間に用意させず、Vercel（無料）→ Cloud Run の順に自動デプロイ（HTTPS / リダイレクト / healthz / 環境変数まで）。どちらも無ければ直リンク運用を選択可能
- 最終画面は **READY / ACTION REQUIRED / BLOCKED** の 3 状態。全項目 READY のときだけ DRY_RUN=false へ移行でき、その際も **「本番運用開始」の明示入力を 1 回だけ** 要求します。以後の日次運用に人間確認はありません
- 途中で終了しても再実行すれば続きから再開します。`--check` は質問せず現状判定のみ、`--no-network` は疎通・デプロイを省略

## 運用中に人間へ届くもの（Human Attention Queue）

通常運用では報告しません。次の場合だけ Slack（`SLACK_WEBHOOK_URL`）または stdout に通知します:
API 認証失効 / 規約・価格変更の検知 / アカウント警告 / 審査対応 / 課金上限 / 異常な CTR・CVR / トラッキング障害 /
ポリシー判定不能 / 利益が一定期間マイナス / 本番環境障害。`python -m affiliate_bot attention` で一覧・解決。

## 日次の使い方（cron でも `loop` でも可）

```bash
python -m affiliate_bot fetch-products            # DMM から候補取得 + ERPI 推定（認証なしなら --demo）
python -m affiliate_bot plan                      # 本日の投稿計画（時間帯・パターンはバンディット）
python -m affiliate_bot publish                   # 予定時刻を過ぎた投稿を公開（DRY_RUN=true ならログのみ）
python -m affiliate_bot ingest-metrics            # X の指標を取込
python -m affiliate_bot ingest-conversions --csv 成果.csv   # DMM 管理画面の成果 CSV を投稿へ帰属
python -m affiliate_bot learn                     # バンディット・パターン DB を更新
python -m affiliate_bot checks --network          # 自動停止ルール
python -m affiliate_bot report                    # 毎朝の日次レポート（Opus 5.5）
python -m affiliate_bot weekly                    # 週次レビュー（Fable 5.1、7 日に 1 回のみ）
python -m affiliate_bot research --collect --analyze   # 初回市場調査（X 検索 API、有料）
python -m affiliate_bot serve-tracking            # 投稿単位トラッキング用リダイレクト
python -m affiliate_bot loop                      # 上記を 1 プロセスで常駐実行（要対応時のみ通知）
python -m affiliate_bot attention                 # Human Attention Queue の表示 / --resolve ID
python -m affiliate_bot pause --reason "..." / resume
```

## 本人操作が必要な瞬間（bootstrap が案内）

| 場面 | 本人操作 |
|---|---|
| Anthropic | Console でキー作成（ログイン・課金）→ 貼り付け |
| DMM | アカウント作成・API ID 発行（規約同意）→ 貼り付け。媒体登録の審査申請（文面は AI が生成） |
| X | Developer 登録・クレジット購入・App の権限設定・キー発行（2FA）→ 貼り付け |
| Vercel（任意） | トークン発行 → 貼り付け（以後のデプロイは自動） |
| 本番移行 | 全項目 READY 後に「本番運用開始」と入力（1 回だけ） |

## テスト

```bash
python -m pytest -q tests
```

## デプロイ

`Dockerfile` を Cloud Run（Job または常駐 Service）／Render Worker に載せ、`/var/data` に永続ディスクを割り当てる。
このリポジトリの他プロジェクトと同じ手順（[docs/deploy-cloudrun.md](../docs/deploy-cloudrun.md)）で構築できる。
