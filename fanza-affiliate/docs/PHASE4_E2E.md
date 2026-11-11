# Phase 4: 実認証・実 API での初回 E2E 手順

目的: 実 FANZA API / 実 Anthropic API / 実 X READ（または fallback）で、初回運用開始までを完遂する。X への投稿は人間。

## 0. 人間が用意するもの（★ここだけ人間★）

チャットに貼らず、実行環境の環境変数（クラウド環境の設定画面 → Edit → API credentials または環境変数）か
`fanza-affiliate/.env`（bootstrap の getpass 入力）に設定する。

| 変数 | 取得先 | 必須 |
|---|---|---|
| `DMM_API_ID` | affiliate.dmm.com → API → API ID 発行（規約同意） | 必須 |
| `DMM_AFFILIATE_ID` | 同ページ。API 用は末尾 -990〜-999 | 必須 |
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys（課金残高） | 必須 |
| `X_BEARER_TOKEN` | developer.x.com → App → Keys and tokens → Bearer Token（Read のみ・クレジット購入） | 任意（無ければ CSV/手入力 fallback） |
| `X_USERNAME` | 自分の X ユーザー名（@なし） | 任意 |
| `WEB_TOKEN` | 任意の長い文字列（Web UI のアクセストークン） | 推奨 |
| `DMM_MEDIA_REGISTERED` | DMM 管理画面で X アカウントの媒体登録が承認されたら `true` | 成果計上に必要 |

## 1. 実行

```bash
cd fanza-affiliate
python -m affiliate_bot bootstrap          # 対話。疎通確認（DMM: FloorList、Anthropic: Models API + 1 トークン、X: ユーザー取得）
bash scripts/phase4_e2e.sh                 # 商品取得 → 調査 → plan → today → export → learn → report → checks → status（コスト）
WEB_TOKEN=... python -m affiliate_bot serve   # スマホで http://<host>:8500/?t=<WEB_TOKEN>
```

## 2. 初回だけの人間確認（5 件）

`today` の各 POST について: 商品情報 / 女優名 / 価格 / 割引 / 素材 URL が公式（pics.dmm.co.jp 等）/ 事実誤認なし / 他投稿と似すぎていない。
問題がなければそのまま投稿。以後は確認不要。

## 3. 投稿後

```bash
python -m affiliate_bot posted --url "https://x.com/<user>/status/<id>"      # X READ があれば actual_text/time/media を補完
python -m affiliate_bot metrics                                              # 24h / 72h 時点で自動取得（loop なら毎時）
python -m affiliate_bot metrics --manual <POST_ID> <views> <likes> <reposts> <replies> <bookmarks>   # fallback
python -m affiliate_bot ingest-conversions --csv <FANZA 成果 CSV>            # 週 1 回程度。0 件でも可
python -m affiliate_bot learn && python -m affiliate_bot report
python -m affiliate_bot status                                               # 実使用量ベースの 1 日コストと 30 日換算
```

## 4. 完了判定（すべて OK で Draft 解除可能）

FANZA API 実疎通 / Anthropic 実疎通 / X READ または fallback / 実商品取得 / 初回調査 / Pattern 更新 / 投稿 5 件生成 / 公式素材確認 /
Web UI / posted 登録 / metrics / conversion CSV / learn / report / CI green / Secret 漏洩なし。
最初の 7 日間は学習期間（Pattern の削除・大きな戦略変更はしない）。
