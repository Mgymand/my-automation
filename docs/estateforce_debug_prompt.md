# Estateforce 緊急デバッグセッション指示書

> 対象リポジトリ: `Mgymand/my-automation` (branch: `claude/frosty-swartz`)
> 本番環境: https://my-automation-b3it.onrender.com/
> 作成日: 2026年4月23日
> セッションタイプ: **緊急デバッグ**（v8 機能拡張セッションの前段）

---

## §0 役割と作業境界

### 0.1 役割

あなたは Estateforce プロジェクトの**緊急デバッグエージェント**です。岩本様が報告した症状の原因を特定し、修正してください。

### 0.2 タイムボックス

**作業時間上限: 2時間（120分）**

- 開始時刻を `data/session/debug_started_at.txt` に記録
- 90分経過時点で修正作業を打ち切り、診断レポート作成へ移行
- 120分到達時点で必ず終了

### 0.3 絶対遵守事項

1. **既存機能を一切拡張しない**。報告された症状の修正のみに集中
2. **新規ファイル・新規API・新規UIを追加しない**（修正のために必要なヘルパー関数は可）
3. **データを削除しない**。`data/` 配下のファイルは読み取り・修正のみ、削除は禁止
4. **コミット粒度を細かく**。1問題1コミットで、ロールバック可能に
5. **修正前に必ずバックアップ**を取る（`git stash` または該当ファイルのコピー）
6. **岩本様への質問は最大1回**まで。それ以外はデフォルト判断ルール（§7）で進行

---

## §1 報告されている症状

### 主症状
**「エリア（ワークスペース）を変更しても、そのエリアの内容（物件等）が反映されない」**

### 状況背景
- 2026-04-23 20:28 頃、Render が再デプロイされた（環境変数を6つ追加）
- 追加した環境変数: ANTHROPIC_API_KEY, GITHUB_REPO, GITHUB_BRANCH, RENDER, SECRET_KEY, GITHUB_TOKEN（既存を新トークンで上書き）
- この再デプロイ後にログインし直したところ、上記症状を確認
- 症状が再デプロイ前から存在したのか、再デプロイで発生したのかは不明

---

## §2 想定される原因（仮説リスト）

優先順位順に検証すること：

### 仮説H1: GitHub 同期失敗による初期データ復元の異常
新トークンの権限不足で `init_data.py` が GitHub からデータを正しく復元できていない。
→ 確認: Render Logs で `init_data` 関連のエラー、`401 Unauthorized` `403 Forbidden` の有無

### 仮説H2: ワークスペース別 properties.json の読み込み失敗
`workspaces/<ws_id>/properties.json` のパス解決に問題。
→ 確認: `/api/properties?ws=<id>` の応答内容、`/data/workspaces/` の存在

### 仮説H3: フロントエンドのキャッシュ起因
ブラウザに古い JS が残っている。サーバ側は正常。
→ 確認: index.html のレスポンスヘッダ、JS ファイルの最終更新

### 仮説H4: SSE / アクティブワークスペース切替の不具合
`PUT /api/workspaces/active` が動いていても、フロントが反映していない。
→ 確認: アクティブWS切替時の SSE イベント、フロントのイベントハンドラ

### 仮説H5: SECRET_KEY 変更による副作用
セッション関連で何らかの状態が壊れた。
→ 確認: ログインセッション再生成時のデータロード処理

### 仮説H6: 元から存在していたバグ
v7 セッション以前から存在し、今回顕在化しただけ。
→ 確認: git log で関連箇所の最終変更日

---

## §3 診断手順（順番に実施）

### フェーズA: 環境状態の把握（0〜15分）

```
1. 開始時刻記録
2. data/session/debug_started_at.txt 作成
3. git status / git log --oneline -10 で現状把握
4. Render Logs を確認（最新200行を解析）
5. 主要ファイルのタイムスタンプ確認
   - property-map/app.py
   - property-map/templates/index.html
   - property-map/init_data.py
   - data/workspaces.json
   - data/workspaces/*/properties.json
6. 結果を docs/session_debug/01_environment_check.md に記録
```

### フェーズB: ライブ動作検証（15〜30分）

```
1. curl で本番APIを呼び、応答を検証:
   - GET /api/workspaces → 全ワークスペース一覧
   - GET /api/workspaces/active → アクティブワークスペース
   - GET /api/properties?ws=<id1> → 物件一覧（複数ID試行）
   - GET /api/properties?ws=<id2> → 物件一覧（別のID）
2. 各応答が期待通りか確認
3. ワークスペース切替APIを叩き、即座に再取得して反映確認:
   - PUT /api/workspaces/active (Cookie必要)
4. 結果を docs/session_debug/02_live_api_test.md に記録
```

ログイン Cookie が必要な API には、テスト用に管理者ログインから取得した Cookie を使用。手順は `/api/login` で `{email, password}` を POST してレスポンスから Set-Cookie を取得。

### フェーズC: 仮説検証（30〜60分）

§2 の仮説H1〜H6 を順に検証。

各仮説について：
1. 該当する Render Logs / コード / API応答を確認
2. 結果を `docs/session_debug/03_hypothesis_verification.md` に記録
3. 確定したら原因として登録

### フェーズD: 修正実施（60〜90分）

#### 修正前の必須事項
1. 該当ファイルを `<filename>.before_debug` として複製
2. git で stash 取得（万一に備えて）
3. ローカルで修正
4. ローカルでテスト

#### 修正後の必須事項
1. ブラウザで本番動作確認用の手順を `docs/session_debug/04_verification_steps.md` に記載
2. 1コミット1意図で commit（メッセージに `[DEBUG-Hn]` を付与）
3. `git pull --rebase` → push
4. Render 再デプロイ完了を待つ（最大10分）
5. 本番で症状解消を確認

#### 修正できないケース
- 仮説検証で原因不明
- 修正実装に60分以上かかる見込み
- 既存機能への副作用リスクが高い

→ 修正は実施せず、診断レポートのみ作成して引継ぎ

### フェーズE: 完了報告（90〜120分）

```
1. docs/session_debug/00_summary.md 作成
   - 報告症状
   - 特定した原因
   - 実施した修正
   - 動作確認結果
   - 残課題
2. docs/session_debug/05_handover_to_v8.md 作成
   - v8 セッションを安全に起動できるか判定
   - 判定結果: 「v8起動可」「v8起動前に追加確認必要」「v8起動不可」
3. デプロイ最終確認
4. セッション終了
```

---

## §4 既存コードの地雷リスト（必読）

修正時に絶対踏んではならない地雷：

| # | 地雷 | 防止策 |
|---|------|-------|
| Z1 | 永続化忘れによるデータロス | `/data` への保存を削除しない |
| Z2 | CJK部首ジオコーディング失敗 | 正規化テーブルを撤去・破壊しない |
| Z3 | 自分の更新を他者更新と誤検知 | `syncTs()` 呼出を消さない |
| Z5 | z-index 階層 | toolbar 1000、全画面 2000 等を破壊しない |
| Z8 | gunicorn workers=1 制約 | リクエスト内で重処理しない |
| Z9 | GitHub push 衝突 | `git pull --rebase` 必須 |

詳細は `docs/estateforce_handover_supplement.md` §10 参照。

---

## §5 単一通知ポイント

緊急判断が必要な場合のみ1回だけ岩本様に通知可。

通知する条件：
- 修正により既存データが破壊される可能性が高い
- ロールバック不可能な変更が必要
- 30分以上の停止が必要な変更
- 上記以外で重大な判断要求

通知方法: `docs/session_debug/notifications/N1_critical.md` に書き込み、30分待機。
30分経過後はデフォルト判断ルール（§7）で自律続行。

---

## §6 完了時に必ず存在すべきファイル

```
docs/session_debug/
├── 00_summary.md                  ← サマリー（最重要）
├── 01_environment_check.md        ← 環境状態
├── 02_live_api_test.md            ← API応答テスト
├── 03_hypothesis_verification.md  ← 仮説検証
├── 04_verification_steps.md       ← 動作確認手順（修正実施時）
├── 05_handover_to_v8.md           ← v8起動可否判定
└── notifications/                  ← 通知ログ（あれば）
```

---

## §7 デフォルト判断ルール（質問なしで判断）

| 状況 | デフォルト判断 |
|------|------------|
| 症状再現できない | 「再現不可」として報告し、ブラウザキャッシュクリアの指示を引継ぎ |
| 原因が複数考えられる | 影響範囲が小さい修正から試す |
| 修正案が複数ある | 既存コードへの変更が最小なものを選ぶ |
| 修正失敗した | git revert で元に戻し、診断レポートのみ残す |
| Render再デプロイ失敗 | 直前のコミットに revert、岩本様に通知 |
| 60分経過時点で原因未特定 | 修正中止、診断レポート作成に専念 |
| GitHub push 競合 | `git pull --rebase` で Auto-sync 取り込み、衝突時は `--theirs` |
| 環境変数値の変更が必要 | 行わない（岩本様の手動操作を引継ぎに記載） |

---

## §8 v8 起動可否の判定基準

セッション完了時、以下のいずれかで判定：

### 「v8起動可」と判定する条件
- 報告症状が解消した
- 既存機能テストが全てパス
- 本番デプロイ成功

### 「v8起動前に追加確認必要」と判定する条件
- 症状の一部のみ解消
- 既存機能の一部に副作用が残る
- 修正は完了したが本番未確認

### 「v8起動不可」と判定する条件
- 症状の原因が特定できなかった
- 修正不能と判断した
- 既存データに損傷リスクがある

---

## §9 参考ファイル

- `docs/estateforce_claude_code_prompt_v8.md` ← 通常のv8プロンプト（参考のみ、実行しない）
- `docs/estateforce_handover_supplement.md` ← 既存実装の要点（必読）
- `docs/notification_guide.md` ← v8通知ガイド（参考）

---

**それでは §3 フェーズA から開始してください。最初の作業は開始時刻記録と環境状態の把握です。**

**重要**: このセッションは v8 機能拡張ではなく**緊急デバッグ**です。新機能を実装してはいけません。
