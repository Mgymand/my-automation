# 運用の完全自動化（AI 運用本部）

FANZA 手動投稿アシストを、**人間が触るのは「X に投稿して URL を貼る」だけ**の状態で回すための仕組みです。
使うのは無料ツールだけです（GitHub Actions / GitHub Issues / GitHub Mobile / Discord または Slack の Webhook）。AI の API 利用料と X READ の従量課金は別途かかります。

## 1. 自動化の範囲

**X への投稿だけは自動化しません。** X の有料パートナーシップ方針は成人向け商品のアフィリエイト投稿を禁止カテゴリにしています。
本システムには投稿権限を持つコードがなく、環境変数や「了承」で解除する仕組みもありません（`policy.py` の HARD BLOCK）。
X での投稿・リプ欄へのリンク貼り付けは、投稿者本人が規約を確認したうえで手で行います。

| 仕事 | 担当 | 仕組み |
|---|---|---|
| 商品の取得と期待値（EAV）推定 | 自動 | 毎朝 FANZA API |
| 投稿する商品・文章・素材・時刻の決定 | AI | Sonnet が生成、Python が採点、バンディットが時刻を選ぶ |
| 今日の投稿セットを人間に届ける | 自動 | 「📅 投稿セット」Issue。GitHub Mobile と Discord に通知 |
| 投稿時刻のリマインド | 自動 | 毎時ジョブ。Discord、無ければ Issue への @メンション |
| **X に投稿してリプ欄にリンクを貼る** | **人間** | Issue の本文をコピーして投稿 |
| **投稿 URL を Issue にコメント** | **人間** | URL を貼るだけで POST 番号は自動判定 |
| 24h / 72h 指標の取得 | 自動 | X READ。無ければ `/metrics` コメントで手入力 |
| **成果 CSV のアップロード（週 1）** | **人間** | FANZA 管理画面から DL して `inbox/` へ |
| 成果の投稿への帰属・学習 | 自動 | 商品×時間窓の確率帰属 → Thompson Sampling と Pattern DB 更新 |
| 日次分析 / 週次戦略 | AI | 日次は Opus、週次は Fable（予算上限つき） |
| 公開投稿の調査と規約ページの変更検知 | 自動 | 毎週 |
| 障害・異常の検知と起票 | 自動 | 「⚠️ 要対応」「🚨 運用ジョブの失敗」Issue |
| コード保守（失敗の原因調査・修正 PR） | AI | Claude Code の Routine（任意。§6） |

## 2. 構成

```
公開リポジトリ Mgymand/my-automation        private 運用リポジトリ（例: Mgymand/fanza-ops）
  fanza-affiliate/ （コード・テスト）  ──取得──▶  .github/workflows/fanza-ops-*.yml  ← cron / コメント / Issue Close / CSV push
  fanza-affiliate/ops/template/ （雛形）           .github/actions/fanza-run/          コード取得 → DB 復元 → 実行 → DB 保存
                                                    branch fanza-state                  SQLite（1 コミットだけ。履歴は溜めない）
                                                    Issues                              📅 投稿セット / ⚠️ 要対応 / 📈 週次 / 🚨 障害
                                                    inbox/                              成果 CSV の受け口
                        通知 ─▶ GitHub Mobile（Issue・メンション） / Discord・Slack（時刻・件数・リンクのみ）
```

### 運用リポジトリを private に分ける理由
`Mgymand/my-automation` は **public** です。ここで運用すると、Issue（商品名・Affiliate URL）、Actions のログ、状態ブランチの DB（成果・報酬）がすべて公開されます。
そのため運用は private リポジトリで行い、公開側にはコードと雛形だけを置きます。全ワークフローは `github.event.repository.private == true` のときだけ動きます。

## 3. 採用したツールと理由

| ツール | 費用 | 役割 | 採用理由 |
|---|---|---|---|
| GitHub Actions | 無料枠内（§7） | スケジューラ・実行環境 | サーバー不要。Secrets 管理込み。既存 CI と同じ基盤 |
| GitHub Issues + GitHub Mobile | 無料 | 人間の作業画面・通知 | 本文のコピーボタン、チェックリスト、コメントでの登録、スマホ通知がそろう |
| 状態ブランチ（`fanza-state`） | 無料 | SQLite の永続化 | DB は数百 KB〜数 MB。単一コミットを強制更新し、`--force-with-lease` で同時書込を防ぐ |
| Discord / Slack Webhook | 無料 | プッシュ通知（任意） | 1 行で設定できる。成人向けの本文・画像は送らず、埋め込み展開も止める |
| Anthropic API | 従量（日額上限 `DAILY_AI_BUDGET_JPY`） | 生成・分析・戦略 | 上限超過時はテンプレートに自動フォールバック |
| X API READ | 従量（任意） | 指標の自動取得 | 無くても `/metrics` コメントや CSV で回る |
| Claude Code Routine | プランに含まれる | AI による保守 | 失敗ログを読んで修正 PR を出す（§6） |

不採用にしたもの:
- **常時稼働サーバー（Cloud Run / Render / VPS）**: 有料、または無料枠がスリープする。GitHub Actions で足りる
- **Web UI の外部公開**: 認証・TLS の管理が増える。Issue で代替できる
- **Google カレンダー連携**: 予定時刻は毎日変わり、通知は GitHub Mobile / Discord で足りる
- **Google Drive / Sheets を受信箱にする案**: サービスアカウントの設定が増える。リポジトリへのアップロードの方が手順が少ない
- **LINE Notify**: 2025 年 3 月にサービス終了

## 4. 1 日の流れ

| JST | 自動 | 人間 |
|---|---|---|
| 06:05 | 商品更新 → 学習 → 異常検知 → 計画 → 日次レポート → 「📅 投稿セット」Issue → 通知 | 通知を見る（任意） |
| 予定の 15〜75 分前 | 「⏰ まもなく POST n」通知 | 本文をコピーして X に投稿し、リプ欄にリンク → 投稿 URL を Issue にコメント |
| コメント直後 | URL から Post ID を解析して登録し、チェックを付けて返信 | — |
| 毎時 45 分 | 24h / 72h 指標取得、コメントの取りこぼし回収、要対応 Issue の起票と解決、受信箱 | — |
| 月曜 07:20 | 公開投稿の調査 → 規約ページ確認 → Fable の週次レビュー Issue | 週次レビューを読む（任意） |
| 週 1 回いつでも | CSV を取り込んで帰属・学習 | 成果 CSV を `inbox/` にアップロード |

Issue へのコメントで使える命令:

```
https://x.com/you/status/123…            予定時刻が一番近い未登録の POST に登録
/posted 2 https://x.com/you/status/123…  POST 2 に登録
/skip 2 理由                             POST 2 を投稿しない
/metrics 2 1200 8 1 0 2                  POST 2 の指標（views likes reposts replies bookmarks）
/help                                    使い方
```

OWNER / MEMBER / COLLABORATOR のコメントだけを処理します。Bot や第三者のコメントは無視します。

## 5. 安全設計

- **公開リポジトリでは動かない**: job の `if` で private を必須にしている
- **外部入力をシェルに展開しない**: コメント本文はワークフローに渡さず、Python が API で読み直す。式に入るのは Issue 番号だけ
- **同時実行の直列化**: 全ワークフローが同じ concurrency グループで動く。保留中のジョブが打ち切られても、毎時ジョブがコメントを回収する
- **状態の競合検知**: `ops_state.sh push` は pull 時点のコミットを lease にして強制更新する。他の書込があれば失敗し、障害 Issue になる
- **通知に成人向けコンテンツを載せない**: Discord / Slack へは時刻・件数・KPI・Issue へのリンクだけを送る。Discord は `SUPPRESS_EMBEDS`、メンションは無効
- **Secrets**: すべて運用リポジトリの Actions Secrets に置く。DB・ログ・Issue・LLM プロンプトには入らない
- **コードの取得元**: 既定は公開リポジトリの `main`。より固くするなら `FANZA_CODE_REF` にコミット SHA を入れて固定する

## 6. AI の管理レイヤー

| 層 | 誰が | 何を |
|---|---|---|
| 毎回の判断 | Python / SQL | 採点、時刻選択（バンディット）、帰属、異常検知 |
| 文章生成 | Sonnet | 1 商品 5 案の生成と書き直し |
| 日次分析 | Opus | 昨日の結果から増やす・減らす・試すを決め、レポートを書く |
| 週次戦略 | Fable | 投稿数、Pattern の追加と削除、テーマ配分を見直す |
| 保守（任意） | Claude Code Routine | 失敗した運用ジョブのログを読み、原因を直す PR を公開リポジトリに出す |

保守 Routine を使う場合は、Claude Code の Routine を週 1 回（または毎日）で作り、運用リポジトリと公開リポジトリをソースに付けて次の指示を入れます。

```
fanza-ops の直近 7 日の GitHub Actions 実行と、open の「🚨 運用ジョブの失敗」「⚠️ 要対応」Issue を確認する。
失敗があればログから原因を特定し、Mgymand/my-automation の fanza-affiliate/ を直す draft PR を作る（テストを通すこと）。
要対応 Issue のうち人間の判断が要らないもの（再実行で直るもの等）は対応して Close する。
X への投稿を自動化する変更、HARD BLOCK を弱める変更、Secrets を表示する操作は絶対にしない。
結果を 5 行以内で「📈 週次レビュー」Issue にコメントする。
```

## 7. 無料枠の見積もり（private リポジトリ）

| ジョブ | 回数 / 月 | 1 回の分数（切り上げ） | 分 / 月 |
|---|---|---|---|
| 毎朝 | 30 | 3 | 90 |
| 毎時（08:45〜23:45 の 16 回 / 日） | 480 | 2 | 960 |
| コメント登録（5 件 / 日） | 150 | 1 | 150 |
| 週次 | 4〜5 | 5 | 25 |
| 受信箱・Issue Close | 〜10 | 1 | 10 |
| 合計 | | | 約 1,235 |

GitHub Free の private リポジトリには、月 12 ドル分の実行枠が付いています。標準 Linux ランナーは 1 分 0.006 ドルなので、約 2,000 分です（ジョブごとに 1 分単位で切り上げ。2026-11 に docs.github.com の料金ページで確認）。見積もりの約 1,235 分は約 7.4 ドル分で、枠内に収まります。
足りなくなったら、毎時ジョブの cron を 2 時間おき（`45 23,1-13/2 * * *` など）に変えてください。リマインドの先行時間は `OPS_REMIND_LEAD_MIN` で広げられます。
GitHub の cron は混雑時に数分〜数十分遅れることがあります。リマインドを最大 75 分前に送るのはそのためです。

## 8. セットアップ（初回 15 分）

1. private リポジトリを作る（例: `fanza-ops`）。手元に `gh` があれば次の 3 行で済みます。
   ```bash
   gh repo create fanza-ops --private --clone
   bash my-automation/fanza-affiliate/ops/install.sh fanza-ops
   cd fanza-ops && git add -A && git commit -m "FANZA 運用ワークフロー" && git push -u origin HEAD
   ```
   `gh` が無い場合は、`fanza-affiliate/ops/template/` の中身を GitHub の Web 画面からそのままアップロードします。
2. 運用リポジトリの Settings → Secrets and variables → Actions に登録します（値はチャットに貼らない）。

   | 種類 | 名前 | 必須 | 値 |
   |---|---|---|---|
   | Secret | `DMM_API_ID` / `DMM_AFFILIATE_ID` | 必須 | affiliate.dmm.com の API 情報（Affiliate ID は末尾 -990〜-999） |
   | Secret | `ANTHROPIC_API_KEY` | 推奨 | 無ければ文章はテンプレートで作る |
   | Secret | `X_BEARER_TOKEN` | 任意 | READ ONLY の Bearer。無ければ指標は `/metrics` か CSV |
   | Secret | `DISCORD_WEBHOOK_URL` / `SLACK_WEBHOOK_URL` | 任意 | 無ければ GitHub Mobile の通知だけ |
   | Variable | `DMM_MEDIA_REGISTERED` | 必須 | 媒体登録が承認されたら `true` |
   | Variable | `FANZA_CODE_REF` | — | PR がマージされるまでは `claude/practical-einstein-2yfee6`。以後は `main` か SHA |
   | Variable | `X_USERNAME` / `POSTS_PER_DAY` / `OPS_MENTION` / `DAILY_AI_BUDGET_JPY` | 任意 | 既定は「なし / 3 / リポジトリ所有者 / 300」 |
3. Actions タブで「FANZA 毎朝の投稿セット」を Run workflow で 1 回動かし、「📅 投稿セット」Issue ができることを確認します。
4. スマホに GitHub Mobile を入れ、運用リポジトリを Watch（All Activity）にします。Discord を使う場合は、通知用チャンネルを年齢制限付きにしておくと安全です。

止めたいときは Variable `FANZA_OPS_ENABLED=false` を入れます。再開するときは消します。

## 9. 障害時

- ワークフローが失敗すると「🚨 運用ジョブの失敗」Issue が 1 件だけ作られ、以後の失敗はそこに追記されます。直ったら Close します
- FANZA の認証失効、成果 CSV の取込失敗、7 日間データが取れない、利益が続けてマイナス、規約ページの変更は「⚠️ 要対応」Issue になります。指示どおり対応して Close すると、Attention Queue も解決になります
- 状態ブランチを壊した場合は、ブランチ `fanza-state` を削除すると空の DB から再開します（学習結果は失われます）
