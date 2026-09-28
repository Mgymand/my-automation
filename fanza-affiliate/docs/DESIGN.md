# 設計書（Phase 3）: FANZA アフィリエイト 手動投稿アシスト

目的: X への投稿は人間。それ以外（調査・商品選定・素材選定・投稿文作成・投稿計画・効果測定・学習・改善）を AI とプログラムで自動化し、
**Affiliate Profit** を最大化する。投稿を自動実行する機能は存在しない（成人向け商品の X 自動投稿は `policy.py` の HARD BLOCK）。

## 1. SYSTEM ARCHITECTURE

```
FANZA API ──ItemList──▶ products（EAV）──▶ planner ──▶ posts(planned) ──▶ today / Web UI / export ──▶ 人間が X に投稿
X API(READ) ─search──▶ research_posts ──▶ patterns（構造・Trend）┘        ▲                                   │
                                                                          │ posted --url（Post ID 紐付け）◀───┘
X API(READ) ─/2/tweets?ids──▶ post_metrics（24h/72h）◀── CSV/手入力 fallback
FANZA 成果 CSV ──▶ conversions（商品×時間窓の確率帰属, confidence）
                                     └──▶ learn（Revenue/Engagement/Views 合成 → bandit, patterns）──▶ 翌日の plan
Sonnet: 生成/分類   Opus: 日次判断   Fable: 週次戦略   Python/SQL: 集計・スコア・帰属・時刻
```

| モジュール | 責務 | LLM |
|---|---|---|
| `config` | 設定。X は Bearer（READ）のみ | − |
| `db` | SQLite スキーマ | − |
| `dmm_client` | FANZA 商品情報 API | − |
| `x_client` | READ ONLY（検索・投稿取得・ユーザー） | − |
| `policy` | 成人向け X 自動投稿 HARD BLOCK 台帳、公式ページ変更監視、人間投稿の注意文 | − |
| `compliance` | 投稿文の PR 表記・NG ワード・素材権利 | − |
| `research` | 公開投稿の特徴抽出・比率指標・外れ値・分類・Pattern 更新 | Sonnet |
| `patterns` | Winning Pattern DB（15 種 + 発見分。Trend / Last Seen / 実測） | − |
| `products` | EAV（予測 Views × CTR × CVR × 報酬 × 7 補正）と実測補正 | − |
| `media` | 公式素材の候補化・権利記録、AI 補助素材の用途制限 | − |
| `generation` | 5 案生成、source_pattern_id / similarity_score、自動書き直し | Sonnet |
| `scoring` | Predicted CTR / Engagement / Novelty / Pattern Confidence / Similarity Risk / Policy Risk → 最良案 | − |
| `planner` | 本日のパッケージ（時刻・素材・理由・類似成功投稿・注意・代替案）、投稿数の提案 | − |
| `packages` | テキスト / HTML / フォルダ出力 | − |
| `posted` | URL/ID 解析と紐付け、actual_* 記録 | − |
| `metrics` | マイルストーン取得、CSV/手入力、成果の確率帰属、学習 | − |
| `reports` | 日次（時刻表 → 実績 → 判断 → 投稿セット → 調整）、週次 | Opus / Fable |
| `attention` | Human Attention Queue（9 カテゴリ） | − |
| `bootstrap` | 初期設定エージェント | Sonnet（申請文） |
| `webui` | スマホ向け UI（今日の投稿 / 分析） | − |

## 2. DATABASE SCHEMA

`products`（EAV・素材 URL）/ `patterns`（Hook / Body / CTA / Media / Ideal Length / Ideal Hours / Target Genre / Target Actress Type /
Avg Views / Views/Follower / Engagement / CTR / EPC / Conversions / Profit / Uses / Confidence / Trend Score / Last Seen）/
`candidates`（angle・source_pattern_id・similarity_score・rewrite_count・scores）/ `media_assets`（source_url / source_type / rights_status / product_id）/
`posts`（day・seq・text・alternatives・media・reason・similar_post・notes・scheduled_at・predicted・status planned/posted/skipped・x_post_id・x_url・actual_text/time/media）/
`post_metrics`（milestone_hours・source x_api/csv/manual）/ `conversions`（attribution・attribution_confidence・attribution_share・channel）/
`research_posts`（比率指標・outlier_score・category・hook_type・features）/ `bandit_arms` / `costs` / `events` / `attention_queue` / `daily_summary`。

## 3. MODEL ROUTING

Sonnet 5（生成・書き直し・競合抽象化・申請文、effort low）/ Opus 5.5（日次判断、medium）/ Fable 5.1（週 1 回の戦略、high、`last_weekly_review_at` で強制）。
LLM で解く必要のない処理（集計・EAV・類似度・スコア・バンディット・帰属・時刻）は Python / SQL。利用不可モデルは代替チェーンへ。

## 4. DAILY WORKFLOW（JST）

| 時刻 | 誰 | 内容 |
|---|---|---|
| 06:00 | loop（自動） | fetch-products → learn → checks → report（Opus）→ plan（Sonnet）→ export → 要対応があれば通知 |
| 朝 | 人間 | `today` / Web UI を見る（数分） |
| 各推奨時刻 | 人間 | 本文コピー → 公式素材添付 → X に投稿 → `posted --url` / 「投稿済み」 |
| 毎時 | loop（自動） | X READ があれば 24h / 72h 時点の指標取得 |
| 随時 | 人間（週 1〜2 回） | FANZA 管理画面の成果 CSV を `ingest-conversions` |

## 5. WEEKLY WORKFLOW

月曜 07:00: research（X READ）→ analyze（Sonnet）→ policy 変更監視 → weekly（Fable）。Fable の決定（削除 Pattern・追加 Pattern・投稿数）は
自動反映（削除は demoted、追加は confidence 0.3）。人間の確認事項は本当に必要なものだけ。

## 6. KPI TREE

Affiliate Profit = Σ 投稿 (Views × CTR × CVR × 報酬) − AI 費 − X READ 費 − インフラ。初期は Revenue / Engagement / Views シグナルを
Conversion 件数に応じた重み（20 件で 0.5、上限 0.8）で合成し、十分な CV 後は EPC / Revenue per Post / Revenue per 1,000 Views を中心に最適化。

## 7. TRACKING DESIGN

投稿単位の識別は人間が登録する Post ID（`posted --url`）。指標は X READ（public_metrics）を 24h / 72h で取得し、無ければ CSV / 手入力。
成果は FANZA CSV を商品 × 時間窓（72h）で帰属: 1 件 → high、複数 → Views 按分 medium、同日窓外 → low、なし → unattributed。
中間リダイレクトや短縮 URL は使わない。

## 8. A/B TEST DESIGN

Thompson Sampling（時間帯 / パターン / ジャンル / メディア）。同一商品 × 訴求軸の比較は別日に行う。類似度 ≥ 0.55 で書き直し、≥ 0.8 で却下。

## 9. FAIL-SAFE DESIGN

自動投稿がないため「停止」は存在しない。異常は Attention Queue へ: fanza_auth / x_read_auth / policy_change / media_rights /
product_inconsistency / csv_ingest_failed / data_stale / profit_negative / prod_outage。通知は Slack 成功時のみ確定。

## 10. COST ESTIMATE（月、5 投稿/日）

Sonnet 150 回 × ¥1 ≒ ¥150 / Opus 30 回 × ¥5 ≒ ¥160 / Fable 4 回 × ¥45 ≒ ¥180 / X READ: 調査 400 件 × $0.005 + 指標 300 件 × $0.001 ≒ $2.3（¥350）
/ インフラ ¥0（ローカル）〜¥1,500（小型 VPS）。合計 **約 ¥850〜2,300 / 月**。
