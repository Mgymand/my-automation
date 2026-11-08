# fanza-ops（private 運用リポジトリ）

FANZA 手動投稿アシストを **GitHub Actions + GitHub Issues** で無人運用するためのリポジトリです。
コードは公開リポジトリ（既定 `Mgymand/my-automation` の `fanza-affiliate/`）から毎回取得し、ここにはワークフロー・状態（DB）・Issue だけを置きます。
商品名・Affiliate URL・成果などのデータが公開されないよう、**このリポジトリは必ず private** にしてください（public ではワークフローが動きません）。

## 人間がやること
| いつ | やること | 所要 |
|---|---|---|
| 毎日（投稿ごと） | 「📅 今日の投稿セット」Issue の本文をコピーして X に投稿 → 投稿 URL を Issue にコメント | 1 分 / 件 |
| 週 1 回 | FANZA 管理画面から成果 CSV をダウンロードし `inbox/` にアップロード | 2 分 |
| 通知が来たとき | 「⚠️ 要対応」Issue の指示どおり対応して Close | 内容による |

それ以外（商品取得・選定・文章作成・時刻決定・リマインド・指標取得・成果の帰属・学習・日次 / 週次レポート・障害検知）はすべて自動です。

## 動いているもの
| ワークフロー | タイミング（JST） | 内容 |
|---|---|---|
| FANZA 毎朝の投稿セット | 毎日 06:05 | 商品更新 → 学習 → 計画 → レポート → 投稿セット Issue → 通知 |
| FANZA 毎時 | 08:45〜23:45 の毎時 | 指標取得 → 投稿リマインド → コメント取込 → 要対応 Issue → 受信箱 |
| FANZA 週次レビュー | 月曜 07:20 | 公開投稿の調査 → 規約ページ確認 → 週次レビュー Issue |
| FANZA 投稿URLの登録 | コメント時 | 投稿 URL / `/posted` / `/skip` / `/metrics` を即時登録 |
| FANZA 要対応の解決 | Issue を Close した時 | Attention Queue を解決 |
| FANZA 受信箱 | `inbox/` に CSV を置いた時 | 成果 / 指標 CSV を取込 |

止めたいときは Settings → Variables で `FANZA_OPS_ENABLED=false`。
