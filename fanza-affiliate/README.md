# DMM/FANZA アフィリエイト × X 自動運用（営業利益最適化）

X（旧 Twitter）公式 API だけを使って DMM/FANZA の商品を紹介し、
「表示 → 興味 → リンククリック → 遷移 → 購入 → 報酬」のファネル全体を投稿単位で計測、
**営業利益（売上 − AI 費 − API 費 − インフラ費）** を目的関数に探索・活用で配分を最適化するシステムです。

- 設計書: [docs/DESIGN.md](docs/DESIGN.md)（アーキテクチャ / スキーマ / モデル配分 / 日次・週次 / KPI / トラッキング / A/B / フェイルセーフ / コスト）
- 規約・法令確認: [docs/COMPLIANCE.md](docs/COMPLIANCE.md) ← **運用前に必読。人間のチェックリストあり**
- 市場調査: [docs/MARKET_RESEARCH.md](docs/MARKET_RESEARCH.md)

## 最重要の注意（運用前に人間が判断すること）

X の有料パートナーシップ方針は、アフィリエイトリンクを含む投稿を開示対象とし、
**「成人向け・性的な商品/サービス」を禁止カテゴリ**に挙げています（2026-03 導入）。
FANZA の成人向け商品を X で宣伝することは、この方針に抵触する可能性があります。
本システムは `ADULT_ON_X_ACKNOWLEDGED=true` を人間が明示しない限り成人向け商品を投稿しません。
同じ仕組みで **DMM.com の一般商品**（`DMM_SITE=DMM.com`）はそのまま運用できます。

## セットアップ

```bash
cd fanza-affiliate
pip install -r requirements.txt
cp .env.example .env         # 認証情報と人間確認ゲートを記入
python -m affiliate_bot init
python -m affiliate_bot status
```

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
python -m affiliate_bot loop                      # 上記を 1 プロセスで常駐実行
python -m affiliate_bot pause --reason "..." / resume
```

## 必要な認証情報（人間に依頼する項目）

| 変数 | 取得先 |
|---|---|
| `DMM_API_ID`, `DMM_AFFILIATE_ID` | https://affiliate.dmm.com/api/ |
| `X_CONSUMER_KEY`, `X_CONSUMER_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET` | X Developer Console（pay-per-use クレジット購入、OAuth 1.0a Read and Write） |
| `ANTHROPIC_API_KEY` | Anthropic Console |
| `TRACKING_BASE_URL` | リダイレクトサーバーの公開 URL（Cloud Run 等） |

## テスト

```bash
python -m pytest -q tests
```

## デプロイ

`Dockerfile` を Cloud Run（Job または常駐 Service）／Render Worker に載せ、`/var/data` に永続ディスクを割り当てる。
このリポジトリの他プロジェクトと同じ手順（[docs/deploy-cloudrun.md](../docs/deploy-cloudrun.md)）で構築できる。
