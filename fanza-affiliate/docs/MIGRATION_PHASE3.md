# Phase 3 移行: 「X 自動投稿 Bot」→「FANZA 手動投稿アシスト（AI 編集部・リサーチ部・分析部）」

方針: X への投稿そのものは人間が行う。AI とプログラムは調査・商品選定・素材選定・投稿文作成・投稿計画・効果測定・学習・改善を行う。
成人向け商品の X 自動投稿 HARD BLOCK（`policy.py`）は維持し、投稿権限を持つコードは削除する。

## ファイル分類（PR #27 時点 → Phase 3）

| 分類 | ファイル | 内容 |
|---|---|---|
| KEEP | `affiliate_bot/__init__.py`, `__main__.py` | そのまま |
| KEEP | `affiliate_bot/policy.py` | 成人向け商品の X 自動投稿 HARD BLOCK 台帳。設定・了承で解除不可。`verify_policy()` の direct/proxy 区別も維持 |
| KEEP | `affiliate_bot/dmm_client.py` | FANZA 商品情報 API v3。サンプル画像・動画 URL の正規化 |
| KEEP | `affiliate_bot/llm.py` | Sonnet / Opus / Fable ルーター、原価台帳、予算、代替ルーティング |
| KEEP | `affiliate_bot/similarity.py` | 文字 3-gram Jaccard |
| KEEP | `affiliate_bot/bandit.py` | Thompson Sampling（時間帯 / パターン / ジャンル / メディア） |
| KEEP | `affiliate_bot/secrets_store.py` | .env(600) / Secret Manager / Vercel env / gh secrets |
| KEEP | `affiliate_bot/pricing.py` | X 読取価格・LLM 価格の設定値化と staged update |
| MODIFY | `affiliate_bot/config.py` | X WRITE 認証（OAuth 1.0a 4 キー）を削除し `X_BEARER_TOKEN`（App-only 読取専用）へ。DMM_SITE 既定 FANZA。DRY_RUN / go-live / tracking / paid_partnership 設定を削除 |
| MODIFY | `affiliate_bot/db.py` | posts を「投稿パッケージ」に再定義（planned/posted/skipped、actual_*、x_url、alternatives、reason、similar_post）。media_assets・metric_snapshots（6h/24h/72h/7d）・conversions.attribution_confidence・patterns 拡張列・research_posts 拡張列 |
| MODIFY | `affiliate_bot/x_client.py` | **書込メソッドを全削除**（create_post / upload_media / delete_post）。Bearer 読取: 投稿検索・投稿取得（public_metrics・著者・メディア）・ユーザー取得 |
| MODIFY | `affiliate_bot/compliance.py` | 投稿文チェック（PR 表記・NG ワード・素材権利）を人間投稿用パッケージに適用。自動投稿ゲートは policy.py の HARD BLOCK のみ残す |
| MODIFY | `affiliate_bot/patterns.py` | 15 カテゴリのシード、Pattern の拡張属性（Hook / Body / CTA / Media / Ideal Length / Ideal Hours / Target Genre / Target Actress Type / Views/Follower / Engagement / CTR / EPC / Conversions / Profit / Trend Score / Last Seen） |
| MODIFY | `affiliate_bot/research.py` | 公開投稿の詳細特徴（文字数・改行・冒頭・CTA・絵文字・ハッシュタグ・メディア種別/枚数/尺・リンク位置・女優名・ジャンル・新作/旧作・価格・割引・ランキング・スタイル・フック）と比率指標（views_per_follower / views_per_hour / engagement_rate / likes_per_1k / reposts_per_1k）。小規模アカウントの外れ値優先。パターン更新（trend_score・last_seen） |
| MODIFY | `affiliate_bot/products.py` | Expected Affiliate Value = 予測 Views × CTR × CVR × 報酬 に Competition / Novelty / Discount Strength / Actress Momentum / Genre Momentum / Historical EPC / Pattern Compatibility を加味。実測で補正 |
| MODIFY | `affiliate_bot/generation.py` | 1 商品につき最低 5 案（A 極短文 / B 女優 / C シチュエーション / D レビュー / E 価格・割引）。source_pattern_id・similarity_score を保存、類似時は自動書き直し |
| MODIFY | `affiliate_bot/scoring.py` | Predicted CTR / Engagement / Novelty / Pattern Confidence / Similarity Risk / Policy Risk → 最良案 1 つ + 代替 1〜2 |
| MODIFY | `affiliate_bot/scheduler.py` → `planner.py` | 本日の投稿パッケージ（既定 5 件、実績から最適数を提案）。推奨時刻・素材・選定理由・類似成功投稿・注意事項 |
| MODIFY | `affiliate_bot/metrics.py` | 投稿後の X 指標を 24h / 72h 基本（6h / 7d 任意）で取得、CSV / 手入力 fallback。成果 CSV の確率帰属（商品×時間帯 → 商品×日付 → channel）と confidence |
| MODIFY | `affiliate_bot/reports.py` | 日次: 時刻表 → 投稿セット → 増減の 4 行。週次: Fable が売れた/売れなかった商品・女優・ジャンル・価格帯・割引・時間・Pattern・文章量・動画/画像・CTA・競合・AI 費を見直し |
| MODIFY | `affiliate_bot/attention.py` | カテゴリを刷新: fanza_auth / x_read_auth / policy_change / media_rights / product_inconsistency / csv_ingest_failed / data_stale / profit_negative / prod_outage |
| MODIFY | `affiliate_bot/failsafe.py` | 自動停止（publish 停止）を廃止し、異常検知 → Attention Queue のみ |
| MODIFY | `affiliate_bot/bootstrap.py` | DMM（API + 媒体登録）/ X 読取（Bearer）/ Anthropic / DB / Secret / 常駐 の初期設定。トラッキング自動構築・本番承認・X App 書込権限の案内を削除 |
| MODIFY | `affiliate_bot/demo_data.py` | FANZA 相当の合成商品（ドライラン用） |
| MODIFY | `affiliate_bot/cli.py` | research / fetch-products / plan / today / export / posted / metrics / ingest-conversions / learn / report / weekly / status / attention / bootstrap / serve / loop |
| DELETE | `affiliate_bot/publisher.py` | X 自動投稿・自動リンクリプ |
| DELETE | `affiliate_bot/tracking.py`, `deploy/vercel-tracking/` | 中間リダイレクト（規約回避と誤解され得る仕組みは持たない） |
| NEW | `affiliate_bot/media.py` | 公式素材（サンプル画像・動画・パッケージ画像）の候補化と権利記録（source_url / source_type / rights_status / product_id）。AI 補助素材の許容ルール |
| NEW | `affiliate_bot/packages.py` | 投稿パッケージのテキスト / Markdown / HTML 整形とフォルダ出力 |
| NEW | `affiliate_bot/posted.py` | `posted --url` の URL / Post ID 解析と予定投稿への紐付け（actual_text / actual_post_time / actual_media） |
| NEW | `affiliate_bot/webui.py` | スマホ向け簡易 Web UI（今日の投稿 / コピー / 投稿済み / 分析タブ） |
| NEW | `tests/test_phase3_*.py` | unit / integration / dry run / manual posting flow / CSV ingest / research |
