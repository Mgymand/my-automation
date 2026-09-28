# FANZA アフィリエイト 手動投稿アシスト（AI 編集部・リサーチ部・分析部）

X への投稿は **人間が行います**。このシステムは投稿しません。
AI とプログラムが行うのは、調査・商品選定・素材選定・投稿文作成・投稿計画・効果測定・学習・改善です。
人間の毎日の作業は次の 3 つだけです。

1. Claude が作った **今日の投稿セット**（`today` または Web UI）を見る
2. 本文をコピーし、指定の公式素材を添付して **X に手動投稿**
3. 投稿 URL を **`posted --url`** または Web UI の「投稿済み」で登録

> 成人向け商品の X **自動投稿**は `affiliate_bot/policy.py` の HARD BLOCK（X 有料パートナーシップ方針の禁止カテゴリ）として維持しており、
> 投稿権限を持つコード自体が存在しません（`x_client.py` は Bearer Token の READ ONLY）。自動リプ・中間リダイレクト・
> 環境変数や「了承」で解除する仕組みも置いていません。X への投稿の可否は投稿者本人の判断と責任であり、
> 各投稿パッケージに規約上の注意（`HUMAN_POSTING_NOTICE`）を必ず添えます。

- 設計: [docs/DESIGN.md](docs/DESIGN.md) / 規約: [docs/COMPLIANCE.md](docs/COMPLIANCE.md) / 調査: [docs/MARKET_RESEARCH.md](docs/MARKET_RESEARCH.md) / 移行: [docs/MIGRATION_PHASE3.md](docs/MIGRATION_PHASE3.md)

## 初回セットアップ（人間は認証・同意・課金・審査だけ）

```bash
cd fanza-affiliate
pip install -r requirements.txt
python -m affiliate_bot bootstrap
```

`bootstrap` が環境・依存・DB・Secret・コンプライアンス・Anthropic・FANZA API・X READ・常駐を自動判定し、不足分だけを
`★ここだけ人間★` として案内します（管理画面 URL・押すメニュー・コピーする値）。Secret は `getpass` で入力し画面に出しません。

| 人間が用意するもの | どこで |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys（課金残高） |
| `DMM_API_ID` / `DMM_AFFILIATE_ID`（末尾 -990〜-999） | affiliate.dmm.com → API（規約同意）。媒体登録の申請文は AI が生成、申請は本人 |
| `X_BEARER_TOKEN`（任意・READ ONLY） | developer.x.com → App → Keys and tokens → Bearer Token。投稿権限は不要。無ければ指標は CSV/手入力 |
| `X_USERNAME`（任意） | 自分の X ユーザー名（自分の投稿の指標取得に使用） |

## 毎日の流れ

```bash
python -m affiliate_bot morning     # 06:00 に loop が自動実行（fetch-products → learn → report → plan → export）
python -m affiliate_bot today       # 今日の投稿セット（時刻表 → POST 1..5 のパッケージ → 本日の調整）
python -m affiliate_bot serve       # スマホ向け Web UI（本文コピー / 素材 / Affiliate URL / 投稿済み）
python -m affiliate_bot posted --url "https://x.com/…/status/…"   # 投稿後に登録（Post ID を自動解析。--post N で番号指定）
python -m affiliate_bot posted --url … --text "実際の本文" --time … --media …   # 予定と違う内容で投稿した場合
python -m affiliate_bot posted --skip --post 5 --reason "…"        # 投稿しなかった
python -m affiliate_bot metrics                                     # X 読取があれば 24h/72h 時点の指標を自動取得
python -m affiliate_bot metrics --manual POST_ID views likes reposts replies bookmarks   # 手入力 fallback
python -m affiliate_bot metrics --csv metrics.csv                   # CSV fallback（x_post_id,views,likes,…）
python -m affiliate_bot ingest-conversions --csv 成果.csv           # FANZA 管理画面の成果 CSV（商品×時間帯で確率帰属）
python -m affiliate_bot learn / report / weekly / status / attention / checks
python -m affiliate_bot research --collect --analyze                # 公開投稿の調査（X READ）。--import-csv / --demo も可
python -m affiliate_bot export                                      # exports/YYYY-MM-DD/index.html, posts.txt, postN.txt
python -m affiliate_bot loop                                        # 常駐（毎時 metrics、06:00 morning、月曜 07:00 research + weekly）
```

`today` の出力は、最上部に時刻表（`11:30 POST 1` …）、次に各投稿の完成パッケージ
（推奨投稿時刻 / 優先度 / 商品名 / 女優 / ジャンル / 価格 / 割引 / FANZA URL / Affiliate URL / 使用 Pattern / 選定理由 / 投稿本文 /
使用推奨素材（URL・タイプ・権利状態）/ 期待値 / 類似成功投稿 / 投稿時の注意 / 必要時のみ代替案）、最後に本日の調整（3〜5 行）です。

## AI が自動で行うこと

- **調査**: 公開 X 投稿（READ）を継続収集し、文章ではなく構造（フック・本文構成・CTA・メディア・長さ・時間帯・女優/ジャンル）を特徴化。
  `views_per_follower` / `views_per_hour` / `engagement_rate` / `likes_per_1k_views` / `reposts_per_1k_views` で小規模アカウントの外れ値を優先し、15 カテゴリ + α に分類して Pattern DB（Trend Score / Last Seen）を更新
- **商品選定**: FANZA API から商品情報を取得し、Expected Affiliate Value（予測 Views × CTR × CVR × 報酬 × Competition / Novelty / Discount / Actress・Genre Momentum / Historical EPC / Pattern Compatibility）で選ぶ。単純ランキング順は使わない。実測が増えるほど競合情報の重みを下げ自分の CV・EPC の重みを上げる
- **生成**: 1 商品につき 5 案（極短文 / 女優 / シチュエーション / レビュー / 価格・割引）。source_pattern_id と similarity_score を保存し、既存投稿と似すぎれば自動で書き直す。最良案 1 つを AI が選び、必要時のみ代替 1〜2 案
- **素材**: DMM 公式素材（サンプル画像・動画・パッケージ）のみ候補化し、source_url / source_type / rights_status / product_id を保存。他者投稿からの転載は行わない。AI 生成素材はタイトルカード等の補助デザインに限定
- **計測**: 投稿後 24h / 72h（設定で 6h / 7d 追加）の Views・Likes・Reposts・Replies・Bookmarks。FANZA 成果 CSV は商品×時間窓 → 商品×日付 → channel の順に確率帰属し、`attribution_confidence`（high / medium / low）を保存
- **学習**: Revenue / Engagement / Views の 3 シグナルを Conversion データ量に応じて合成し、Thompson Sampling（時間帯・パターン・ジャンル・メディア）と Pattern DB を更新。翌日の商品・文章・時間帯に反映
- **レポート**: 毎朝、昨日の売上・報酬・Views・最良/最低投稿・CTR 推定・CV・EPC・投稿あたり利益と、AI の判断（分かったこと / 増やす / 減らす / 試す / 本日の調整）
- **週次**: Fable 5.1 が 7 日 / 30 日 / 全期間を比較し、来週増やす・減らす・試すもの、削除・追加する Pattern、投稿数を決定

## 人間が呼ばれる場合だけ（Human Attention Queue）

FANZA API 認証失効 / X READ 認証失効 / 規約変更 / 素材権利が判断できない / 商品情報の不整合 / 成果 CSV 取込失敗 /
7 日以上データ取得不能 / 利益が一定期間マイナス / 本番システム障害。Slack Webhook（`SLACK_WEBHOOK_URL`）または stdout。

## モデル配分とコスト

| 役割 | モデル | 頻度 |
|---|---|---|
| 投稿候補生成・書き直し・競合投稿の抽象化・媒体登録文 | Sonnet 5 | 日次（商品数 × 1 回） |
| 日次分析・調整判断 | Opus 5.5 | 毎朝 1 回 |
| 週次戦略レビュー（増減・Pattern 追加削除・投稿数） | Fable 5.1 | 週 1 回のみ |
| 集計・EAV・類似度・スコア・バンディット・帰属・時刻計算 | Python / SQL | 常時（LLM 不使用） |

月額の目安（5 投稿/日）: AI ¥400〜600（Sonnet ¥150 / Opus ¥160 / Fable ¥180）、X READ $3〜10（調査 400 件 + 指標 300 件）、インフラ ¥0〜1,500。

## テスト

```bash
python -m pytest -q tests
```
