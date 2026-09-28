# 設計書: DMM/FANZA アフィリエイト × X 自動運用（利益最適化）

目的関数は **営業利益 = アフィリエイト売上 − AI 費 − API 費 − インフラ費 − その他運用費**。
ファネル「表示 → 興味 → プロフィール/リンククリック → FANZA 遷移 → 購入 → 報酬」を投稿単位で計測し、
探索・活用アルゴリズムで「次の 1 円・1 トークン・1 投稿」の配分を決める。

---

## 1. SYSTEM ARCHITECTURE

```
                 ┌──────────────────────── 人間 ───────────────────────┐
                 │ 規約チェックリスト承認 / 成果CSV投入 / 停止解除 / 週次レビュー確認 │
                 └──────────────┬───────────────────────────┬──────────┘
                                │                           │
┌───────────┐   ItemList   ┌────▼────────────────────────────▼───────┐    POST /2/tweets    ┌─────┐
│ DMM API v3│ ───────────► │  affiliate_bot (Python 3.11, SQLite)     │ ───────────────────► │  X  │
└───────────┘              │  products → erpi → scheduler(bandit)    │ ◄─────────────────── │     │
                           │  generation(Sonnet) → scoring → posts   │  GET /2/tweets 指標   └─────┘
┌───────────┐  redirect    │  publisher → metrics → learn → reports  │
│ tracking  │ ◄─────────── │  failsafe（自動停止） / costs（原価台帳）  │
│ /r/<code> │ ──► DMM      └──────────────┬──────────────────────────┘
└───────────┘  affiliate URL              │ 決定論的処理は Python/SQL。LLM は 3 箇所のみ
                                          ▼
                             Sonnet 5（生成/分類）  Opus 5.5（日次分析）  Fable 5.1（週次のみ）
```

**モジュール**（`affiliate_bot/`）

| モジュール | 責務 | LLM |
|---|---|---|
| `config` | 環境変数・人間確認ゲート | − |
| `db` | SQLite スキーマ・原価台帳・イベント | − |
| `dmm_client` | ItemList / FloorList / GenreSearch / ActressSearch。1 秒間隔 | − |
| `x_client` | OAuth1.0a 署名、投稿（`paid_partnership`）、メディア chunked upload、指標取得、検索 | − |
| `policy` | 規約台帳（X 有料パートナーシップ禁止カテゴリ）。成人向け商品の X 投稿を **設定で解除不能な HARD BLOCK** にし、公式ページの変更を監視 | − |
| `compliance` | HARD BLOCK → PR 表記・NG ワード・素材権利・媒体登録ゲート | − |
| `bootstrap` | 対話型初期設定エージェント（環境判定 → Secret 入力 → 疎通 → 自動デプロイ → READY/ACTION/BLOCKED → 本番承認） | Sonnet（媒体登録文） |
| `secrets_store` | .env(600) / Google Secret Manager / Vercel env / GitHub Actions への保存 | − |
| `pricing` | X API・LLM 価格の設定値化と公式ページ照合（固定値に依存しない利益計算） | − |
| `attention` | Human Attention Queue（起票・重複排除・Slack 通知） | − |
| `products` | 候補取得・ERPI 推定（事前分布 × 実測のベイズ的縮小） | − |
| `patterns` | Winning Pattern DB（シード・更新・減衰・降格） | − |
| `generation` | 1 商品 × 複数訴求軸の候補生成（Sonnet／テンプレ） | Sonnet |
| `scoring` | 投稿前スコア（pCTR/pCVR/Novelty/Spam/Policy/Similarity/期待利益/信頼度） | − |
| `bandit` | Thompson Sampling（時間帯・パターン・ジャンル・メディア） | − |
| `scheduler` | 日次計画（商品×時間帯×パターン×候補） | − |
| `publisher` | 公開直前ゲート → メディア → 本文 → リンクリプ。エラー時停止 | − |
| `tracking` | 短縮リダイレクト・クリック記録・ラストクリック帰属 | − |
| `metrics` | X 指標取込・成果 CSV 取込・学習（バンディット/パターン更新） | − |
| `failsafe` | 自動停止ルール | − |
| `reports` | 日次レポート・週次レビュー | Opus / Fable |
| `research` | 市場調査（X 検索 → 比率指標 → 分類 → パターン追加） | Sonnet |
| `cli` | 全ジョブの入口（cron / `loop`） | − |

**デプロイ**: 1 コンテナ（`Dockerfile`）＋永続ディスク（SQLite）。Cloud Run Job／Render Worker／VPS cron いずれでも可。
トラッキングは同じイメージで `serve-tracking` を起動（HTTPS 終端はプラットフォーム側）。

---

## 2. DATABASE SCHEMA（SQLite, `affiliate_bot/db.py`）

| テーブル | 主キー | 主な列 | 用途 |
|---|---|---|---|
| `settings` | key | value, updated_at | 停止状態・学習済み ID・週次レビュー日時 |
| `accounts` | name | theme, target_audience, content_strategy, x_user_id, active | 複数アカウントは必ずテーマを分ける |
| `products` | content_id | site, floor, title, url, affiliate_url, image_url, sample_image_urls(JSON), sample_movie_url, price, list_price, discount_rate, release_date, review_count, review_avg, actresses(JSON), genres(JSON), maker, series, campaign(JSON), rank_position, is_adult, payout_rate, **erpi, erpi_components(JSON)**, raw, fetched_at, last_posted_at | 商品候補と ERPI |
| `patterns` | pattern_id | category, target, hook, structure, cta, media, best_hours(JSON), avg_views, avg_ctr, avg_cvr, avg_epc, uses, recent30_views/ctr/epc/profit, confidence, status(active/demoted), source, last_used_at | Winning Pattern DB |
| `candidates` | id | product_id, pattern_id, angle, text, reply_text, media_plan(JSON), **scores(JSON)**, status(new/scored/selected/rewrite/rejected/human_review), model | 投稿候補と投稿前スコア |
| `posts` | post_id | candidate_id, account, product_id, pattern_id, genre, angle, text, reply_text, media_type, media_source, scheduled_at, slot_hour, posted_at, x_post_id, x_reply_id, **tracking_code**, status(scheduled/posted/failed/blocked/cancelled), error, api_cost_jpy, ai_cost_jpy | 投稿の台帳（Post ID・日時・アカウント・商品・ジャンル・Pattern・コピー・メディア） |
| `post_metrics` | id | post_id, captured_at, views, likes, reposts, replies, quotes, bookmarks, profile_visits, url_clicks | X 指標の時系列 |
| `clicks` | id | tracking_code, ts, ua_hash, referer | 自前リダイレクトのクリック |
| `conversions` | id | ts, post_id, product_id, revenue_jpy, order_ref, source, attribution | 成果（CSV 取込）と帰属 |
| `costs` | id | ts, kind(ai/x_api/dmm_api/infra/other), model, input_tokens, output_tokens, cache_read_tokens, amount_jpy, ref | 原価台帳 |
| `bandit_arms` | (dimension, arm) | alpha, beta, n, reward_sum | Thompson Sampling の状態 |
| `experiments` | id | name, dimension, arms(JSON), hypothesis, min_samples, status, result | A/B テスト台帳 |
| `events` | id | ts, level(info/warn/halt), code, message, data | 監査ログ・停止理由 |
| `research_posts` | id | x_post_id, author_followers, text, media_type, views…, age_hours, views_per_follower, views_per_hour, engagement_rate, category, features(JSON) | 市場調査 |
| `daily_summary` | day | revenue, profit, clicks, conversions, views, ctr, cvr, ai_cost, api_cost, best_pattern, best_product, report_md | 日次スナップショット |

投稿単位の派生指標（CTR・CVR・EPC・Profit）は `metrics.post_profit_rows()` が SQL で算出する（保存せず再計算）。

---

## 3. MODEL ROUTING

| 役割 | モデル | effort | 呼び出しタイミング | 1 回あたり概算 |
|---|---|---|---|---|
| 投稿案生成（1 商品 4 案）、リライト、調査投稿の分類・要約 | `claude-sonnet-5` | low | 日次 5〜6 回（商品数分） | 入力 ~1.5k / 出力 ~0.5k tok ≒ ¥1.2 |
| 日次分析（昨日わかったこと／継続／停止／新規テスト／人間確認） | `claude-opus-5-5` | medium（既定） | 毎朝 1 回 | 入力 ~4k / 出力 ~1k ≒ ¥5.4 |
| 週次レビュー（7 日/30 日/全期間比較、アルゴリズム再評価、パラメータ変更案） | `claude-fable-5-1` | high | **7 日に 1 回のみ**（`last_weekly_review_at` で強制） | 入力 ~10k / 出力 ~4k ≒ ¥45 |
| 商品選定・スコアリング・スケジューリング・集計・帰属・停止判定 | **LLM なし**（Python/SQL） | − | 常時 | ¥0 |

- 全呼び出しは `LLMRouter.call(role, ...)` を経由し、`usage` からコストを `costs` に記録。`DAILY_AI_BUDGET_JPY` 超過で Sonnet/Opus は停止しテンプレ生成へフォールバック。
- Fable 5.1 は thinking 常時 ON（パラメータ省略）、`fallbacks="default"`（beta `server-side-fallback-2026-07-01`）で refusal 時にサーバー側で代替モデルへ。`stop_reason=="refusal"` は `LLMUnavailable` として扱い、決定論的処理に切替。
- 構造化出力は `output_config.format=json_schema`。system prompt は `cache_control` でキャッシュ。
- Sonnet の出力は投稿前スコアリング（決定論）が必ず検査し、Opus は日次レポートで Sonnet 成果物（投稿明細）をレビューする。

---

## 4. DAILY WORKFLOW（JST）

| 時刻 | ジョブ | コマンド | 内容 |
|---|---|---|---|
| 毎時 :00 | 公開・計測・監視 | `checks` → `publish` → `ingest-metrics` | 停止条件確認 → 予定時刻を過ぎた投稿を公開（最低間隔遵守） → 14 日以内の投稿の指標取得（$0.001/件） |
| 06:00 | 学習 | `learn` | 24h 経過した投稿の「表示あたり利益」でバンディット更新、パターン統計再計算、減衰 |
| 06:05 | 商品更新 | `fetch-products` | ランキング・新着を各 100 件取得、ERPI 再計算 |
| 06:10 | 日次レポート | `report` | 前日集計（売上/利益/クリック/CV/CTR/CVR/最優秀 Pattern・商品/AI・API 費）＋ Opus の示唆 ＋ 本日予定 |
| 06:15 | 計画 | `plan` | 商品 × 時間帯 × パターン を選び候補生成 → スコア → 予定登録 |
| 随時 | 成果取込 | `ingest-conversions --csv` | DMM 管理画面の成果 CSV（人間がダウンロード）を投稿へ帰属 |

`loop` コマンドが上記を 1 プロセスで実行する（cron 不要）。1 日の結果だけで戦略変更しない（学習は逐次・小幅、判断は週次）。

---

## 5. WEEKLY WORKFLOW（月曜 07:00 JST）

1. `weekly` → Fable 5.1 が 7 日 / 30 日 / 全期間を比較し、商品選定・生成・Pattern DB・投稿時間・モデル選択・トークン量・API 費を再評価
2. パラメータ変更案は `settings.weekly_param_changes` に保存。**人間承認後に `.env` を変更**（自動適用しない）
3. `research --collect --analyze`（任意・月 1 回程度）で公開 Web／X を再調査し、新しい高パフォーマンス構造を R_ パターンとして追加
4. `patterns.decay_stale()` が 30 日未使用パターンの信頼度を 20% 減、20 回以上使用かつ直近 30 日利益マイナスは降格

---

## 6. KPI TREE

```
営業利益（最重要）
├─ アフィリエイト売上 = Σ 投稿 × 表示 × CTR × CVR × 平均報酬
│   ├─ 表示（Views）      ← 投稿数 × 投稿あたり表示（パターン・メディア・時間帯・新規性・スパム減衰）
│   ├─ CTR（リンククリック/表示） ← フック・訴求軸・CTA・リンク位置
│   ├─ CVR（購入/クリック）      ← 商品（価格・割引・レビュー・キャンペーン）・訴求と商品の整合
│   └─ 平均報酬（EPC = 売上/クリック） ← 価格帯 × 報酬率
└─ 費用
    ├─ AI 費   ← 生成回数 × トークン（Sonnet 主体、Fable は週 1）
    ├─ API 費  ← 投稿 $0.015 + リンク投稿 $0.20 + 読取
    ├─ インフラ ← コンテナ・ディスク（日割）
    └─ その他
補助 KPI: Profile Visits, いいね/ブックマーク（推薦アルゴリズムの品質シグナル）, 投稿あたり利益, 表示あたり利益（バンディット報酬）
非 KPI: フォロワー数・単純 View 数（利益に結びつかない投稿は評価を下げる）
```

---

## 7. TRACKING DESIGN

- **識別子**: `posts.tracking_code`（8 文字）。リプのリンクは `TRACKING_BASE_URL/r/<code>` → 302 → `products.affiliate_url`
- **クリック**: `clicks`（時刻・UA ハッシュ・Referer）。X 側の `url_link_clicks`（non_public_metrics）と突合し、乖離でトラッキング障害を検知
- **表示・反応**: `post_metrics`（impression_count, like, retweet, reply, quote, bookmark, user_profile_clicks, url_link_clicks）
- **成果**: DMM は成果レポート API を提供しないため、管理画面 CSV を `ingest-conversions` で取込。帰属は
  1. 同一商品 × 直近クリック（`ATTRIBUTION_WINDOW_HOURS`=72）→ `last_click`
  2. 商品不明 → 直近クリック → `last_click_any`
  3. なし → `unattributed`（売上には計上、投稿には紐付けない）
- **チャネル補助**: DMM アフィリエイト ID 末尾（-001〜-999）をアカウント別に分けると管理画面側でもアカウント単位の成果が分かる
- **コスト**: `costs` に AI（モデル・トークン別）、X API（投稿・読取）、日割インフラ

---

## 8. A/B TEST DESIGN

- **基本機構**: Thompson Sampling（`bandit_arms`）。次元 = `hour_slot`（8 枠）, `pattern`, `genre`, `media`。
  報酬 = 表示あたり利益を直近中央値でロジスティック正規化（0..1）。新アームは Beta(1,1) で自然に探索、加えて 15% は試行数の少ないアームを優先。
- **明示的 A/B**（`experiments`）: 同一商品で訴求軸（例: price vs review）・CTA・メディア（image vs video）を別日に比較。
  最小サンプル 30 投稿または 20,000 表示、判定は CTR/EPC の差の両側検定（p<0.05）＋利益差。週次レビューで結論。
- **禁止**: 同一本文の反復投稿での比較（規約リスク）。テストは必ず本文を変える。
- **投稿前スコアリング**が実験の前提（Similarity ≥ 0.55 は書き直し、≥ 0.80 は却下、Policy risk ≥ 0.7 は公開不可）。

---

## 9. FAIL-SAFE DESIGN

| トリガー | 検知 | 動作 |
|---|---|---|
| X API 401/403/429 | `publisher` | 即時停止（`paused=1`）。回避せず原因解決後に `resume` |
| DMM API エラー | `fetch-products` | ログ、当日は既存商品で運用 |
| CTR 異常低下 | 直近 3 日 vs 過去 14 日（各 ≥5,000 表示）で 50% 未満 | 停止 |
| CVR 異常低下 | 同（各 ≥100 クリック） | 停止 |
| トラッキング障害 | X url_clicks ≥30 かつ自前クリック 0（2 日） | 停止 |
| リンク障害 | 予定投稿のアフィリエイト URL が 4xx/5xx | 停止 |
| 投稿重複 | 3 日以内に同一本文 2 件以上 | 停止 |
| 素材権利不明 | メディア URL が DMM ドメイン外 | 当該投稿をブロック |
| 成人向け商品（FANZA / 成人向けジャンル） | `policy.x_affiliate_hard_block` | **HARD BLOCK**（候補・計画・公開直前の 3 箇所で除外。設定で解除不可） |
| センシティブになり得るメディア | 水着・グラビア等 × `SENSITIVE_MEDIA_SETTING_CONFIRMED` 未設定 | 当該投稿を人間レビューへ（policy_undecidable） |
| 規約・価格の変更 | `policy.verify_policy` / `pricing.verify_x_pricing`（bootstrap と週次） | Attention Queue（policy_change） |
| 本番承認なし | `DRY_RUN=false` かつ `go_live_approved_at` 未記録 | 投稿しない（bootstrap で「本番運用開始」を要求） |
| 媒体未登録 | `DMM_MEDIA_REGISTERED` 未設定 | 全投稿ブロック |
| アカウント警告 | 人間が `settings.account_warning=1` | 停止 |
| AI 予算超過 | 24h の AI 費 ≥ `DAILY_AI_BUDGET_JPY` | テンプレ生成へ切替（投稿は継続） |
| 規約変更 | 週次レビューのチェック項目（人間） | 人間判断 |

停止中は `publish` が何もしない。`events` に停止理由を記録し、日次レポート冒頭に「停止中」を表示。

**Human Attention Queue**（`attention_queue`）: 通常運用では人間に報告しない。起票カテゴリは
auth_expired / policy_change / account_warning / review_needed / billing_cap / metric_anomaly / tracking_failure /
policy_undecidable / profit_negative / prod_outage の 10 種のみ。同一 dedupe_key の open 項目は再起票しない。
通知は Slack Webhook。送信成功時のみ notified_at を確定し、失敗時は次回再送する。Slack 未設定時は stdout に出すが、
`NOTIFY_CONSOLE_DELIVERY=true`（人間がログを監視していると明示）でない限り「配送済み」にはしない。`attention --resolve ID` で解決。

**Secret の保存先**: local / docker 実行では `.env`（600）を primary に外部ストアへ複製。Cloud Run / Vercel / GitHub Actions / Render では
外部 Secret ストア（Secret Manager / Vercel env / GitHub Actions Secrets）を primary にし、`.env` へは書かない。

**トラッキングの自動構築**: `TRACKING_SECRET` を生成し、署名付きペイロード（`/r/<payload>.<sig>`）で DB を持たない
リダイレクトを Vercel Functions（`deploy/vercel-tracking`, 無料枠）または Cloud Run に bootstrap がデプロイする。
クリック時刻は X の `url_link_clicks` の毎時差分から推定し、成果帰属に使う。

---

## 10. COST ESTIMATE（月次、1 アカウント・5 投稿/日・USD/JPY=150）

| 項目 | 計算 | 月額 |
|---|---|---|
| X API 投稿 | 150 投稿 × $0.015 | ¥340 |
| X API リンクリプ | 150 × $0.20 | ¥4,500 |
| X API 指標読取 | 150 投稿 × 14 日 × $0.001 | ¥315 |
| X API 市場調査（初回のみ） | 400 ポスト × $0.005 + 著者 | ¥300〜900（初月） |
| AI: Sonnet 5 生成 | 150 回 × ¥1.2 | ¥180 |
| AI: Opus 5.5 日次 | 30 回 × ¥5.4 | ¥160 |
| AI: Fable 5.1 週次 | 4 回 × ¥45 | ¥180 |
| インフラ | 小型コンテナ＋1GB ディスク | ¥1,000〜1,500 |
| **合計** | | **約 ¥6,700〜7,900 / 月** |

- 損益分岐: 平均報酬 ¥300/CV なら **月 25 CV**（1 日 0.8 CV）。CVR 2% なら 1,250 クリック/月、CTR 0.8% なら 156k 表示/月（≒1,040 表示/投稿）。
- 価格は固定値ではなく設定値（`X_PRICE_*`）。bootstrap と週次が公式ページと照合し、必須 5 項目が全件抽出できた場合のみ候補化、10% 以内の変動は自動適用、それ以上は候補として保存し人間確認（`pricing --apply`）まで旧価格で計算する。
- 費用の 2/3 は「リンク付き投稿 $0.20」。週次レビューで **リンクリプを固定投稿／プロフィールへ集約する変種**（投稿費 $0.015 のみ）を A/B し、EPC が維持できればコストを 1/6 に圧縮できる。
- AI 費は投稿数に線形。Fable は週 1 回に固定し、日次運用では呼ばない。
