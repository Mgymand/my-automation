# Estateforce 次世代化構想書 v8 — 12時間半自動モード・夜間継続稼働対応版

> 対象リポジトリ: `Mgymand/my-automation` (branch: `claude/frosty-swartz`)
> 本番環境: https://my-automation-b3it.onrender.com/
> 作成日: 2026年4月23日
> v7からの主要変更:
> - 単発5時間から12時間半自動モードへ移行
> - 「夜間継続稼働サイクル」前提の設計
> - 5回の通知ポイント明確化（岩本様の操作最小化）
> - frosty-swartz 完全版の上で再実装（romantic-murdock 成果は参考）
> - 今月末までに岩本様が触れる状態を目指す

---

## §0 役割・作業境界・運用モデル

### 0.1 役割

あなたは Estateforce プロジェクトの**半自律実装エージェント**です。岩本様は必要に応じて通知を受け取り回答されますが、**操作は最小限**に抑える運用です。5回の通知ポイント（§0.5参照）以外では**自律的に判断・実装・検証**を進めてください。

### 0.2 タイムボックス（厳守）

**作業時間上限: 12時間（720分）**

- 開始時刻を `data/session/v8_started_at.txt` に記録
- 各フェーズ着手前に経過時間を確認
- **660分（11時間）経過時点**で残作業を打ち切り、引継ぎシート作成に着手
- **720分（12時間）到達時点**で、未完了作業があってもセッション終了

### 0.3 運用モデル：夜間継続稼働サイクル

本プロジェクトは**1度の大きなMVP到達**ではなく、**継続的進化モデル**で運用されます：

- **今月末（2026年4月30日）まで**: 岩本様が業務で触り始められる状態へ到達
- **以降**: 夜間・早朝の時間帯に8〜12時間の自律セッションを繰り返し実行
- 岩本様が翌朝 `docs/session_v8/00_session_summary.md` を確認し、次セッションへ継続

この運用前提のため：
- **岩本様が日中触ったデータを壊さない**（セッション開始時に必ずバックアップ）
- **1セッションで「動く中間成果物」を必ず残す**（未完成な状態でセッション終了しない）
- **ロールバック可能な粒度でコミット**（問題が見つかれば部分的に巻き戻せる）

### 0.4 自律稼働の作業境界

1. **指示された範囲のみ実装する**。本書§3「v8 実装計画」以外の機能には触れない
2. **通知ポイント以外では質問しない**。未確定情報は §7「デフォルト判断ルール」に従う
3. **コスト超過する選択をしない**。月額¥10,000 超過する構成は採用不可
4. **既存機能を破壊しない**。引継ぎシート §2.7 の 30+ 機能を1つも失わない
5. **既存コードの地雷を踏まない**。§5.2「地雷リスト」を着手前に必ず読み込む
6. **romantic-murdock-d02008 の成果は参考のみ**。コードは直接マージせず、パターン・設計判断を参照して frosty-swartz 上で再実装

### 0.5 通知ポイント（5回・これ以外は通知不可）

以下の5ポイントでのみ岩本様に通知し、回答を待つ：

| # | タイミング | 通知内容 | 最大待機時間 |
|---|----------|--------|----------|
| N1 | フェーズA完了時（開始30〜60分後） | ブランチ統合方針の最終確認、romantic-murdock-d02008 の成果物差分レポート | 30分 |
| N2 | M1 SF連携の実接続テスト直前 | 認証情報（CLIENT_ID / PRIVATE_KEY）の設定状況確認 | 60分 |
| N3 | M7マルチユーザー実装完了時 | 作成したダミーユーザーの確認、差し替え有無 | 30分 |
| N4 | 設計判断で v7/v8 仕様から逸脱する必要が生じた時 | 具体的な判断要求（複数回可） | 30分/回 |
| N5 | セッション完了時（11〜12時間後） | 完了報告・未完了事項・次セッション申し送り | — |

**通知方法**: `docs/session_v8/notifications/N{N}.md` にファイルを作成し、内容を記述。岩本様の回答は同ファイルに追記される想定（Claude Code は再読込して続行）。

**待機時の振る舞い**: 通知送信後、最大待機時間内に回答がなければ**§7 デフォルト判断ルールに従って自律継続**。待機時間中も並行作業可能な別タスクがあれば進める。

### 0.6 セッション完了時に必ず存在すべきファイル

12時間到達時、以下が `docs/session_v8/` 配下に**必ず存在**：

- `00_session_summary.md` — セッションサマリー
- `01_phase_a_summary.md` — 現状把握結果（romantic-murdock 成果物との差分含む）
- `02_design_docs/` — 設計ドキュメント群（前セッションからの更新差分含む）
- `03_implementation_log.md` — 実装機能一覧・到達度・テスト結果
- `04_handover_to_next_session.md` — 次セッション引継ぎシート
- `05_known_issues.md` — 既知問題・未解決事項
- `06_cost_estimate_actual.md` — 実測コスト
- `07_rollback_plan.md` — 問題発生時のロールバック手順
- `notifications/` — N1〜N5 の通知ログ

**660分経過時点**でこれらの作成に着手すること。

---

## §1 ビジョン（簡略）

弊社（株式会社GT-works）の不動産仲介業務を、転記・催促・確認の作業から解放する。オマージュ対象は Salesforce Lightning Experience。

---

## §2 絶対遵守事項

### 2.1 コスト

- **月額予算上限: ¥10,000/月**
- セッション中の Claude API コール量を実測値ベースで月次換算し `06_cost_estimate_actual.md` に記録
- **本セッションのコスト目標: ¥1,000 以内**（Haiku 中心、Sonnet は M6 分類精度改善時のみ限定使用）

### 2.2 既存資産の保護

- 2026-04-22 のデータロス事件を踏まえ、全データを必ず `/data` 永続ディスク または GitHub Contents API に永続化
- **セッション開始時に必ず全データの GitHub バックアップを取る**（/api/backup/download を呼ぶ or 同等処理）
- 既存機能（BGM、猫アニメ含む 30+ 機能）は1つも廃止しない

### 2.3 コード地雷の回避

§5.2 の地雷リスト（Z1〜Z9）を着手前に必ず読了

### 2.4 ブランチ方針（最重要）

- **作業ブランチ: `claude/frosty-swartz`**（完全版・デプロイ対象）
- `romantic-murdock-d02008` は参照のみ、コードをマージしない
- frosty-swartz 上の完全版コードに、romantic-murdock 成果を参考にしつつ**再実装**する
- コミットは段階的に、1コミット1意図で

---

## §3 v8 実装計画（12時間スコープ）

### 3.1 絶対達成目標（今月末までに岩本様が触れる状態）

| # | タスク | 想定時間 | 通知 | 根拠 |
|---|------|--------|------|------|
| T1 | セッション開始・バックアップ・現状把握 | 45分 | — | §8 フェーズ0〜A |
| T2 | romantic-murdock 成果物の差分レポート作成 | 30分 | **N1** | ブランチ統合方針の最終確認 |
| T3 | 簡易設計ドキュメント更新（前回との差分） | 30分 | — | §8 フェーズC |
| T4 | M9 コスト監視ダッシュボード（完成版） | 60分 | — | 運用監視基盤 |
| T5 | M6 PDF分類 Haiku（改善・完成版） | 90分 | — | 現業務で即活用可能 |
| T6 | M8 Toast + Inline Edit + Path コンポーネント | 90分 | — | UI向上 |
| T7 | M7 マルチユーザー基盤（完成版） | 120分 | **N3** | 今月末までの実用化に必須 |
| T8 | M1 SF連携（モックレイヤー + 構造実装） | 90分 | — | 認証情報待ちでもモックで進行可 |
| T9 | M1 SF連携（実接続テスト）※認証情報揃い時のみ | 60分 | **N2** | 認証情報提供を待つ |
| T10 | M10 モバイル最適化（物件登録・詳細・スケジュール閲覧） | 90分 | — | 今月末までに必須 |
| T11 | 統合テスト・既存機能破壊チェック・デプロイ | 60分 | — | 本番反映 |
| T12 | 引継ぎシート作成・セッション終了 | 45分 | **N5** | §8 フェーズF |

**合計想定時間: 810分（13.5時間）**
→ **時間オーバー前提**のため、優先度低いタスクから打ち切り可能：
- 打ち切り優先度1: T9（M1実接続テスト、認証情報未提供なら自動スキップ）
- 打ち切り優先度2: T10（M10モバイル最適化のうち、物件詳細のみ優先、他は次セッション）
- 打ち切り優先度3: T8（M1モック、次セッション送り）

### 3.2 次セッション以降に送る機能（今回触れない）

- M2 Slack 通知の実装（Grid 移行完了待ち、EF内ログのみ実装）
- M3 GCal 双方向同期
- M4 Daily モジュール
- M5 タスク管理
- HPB スクレイピング（Phase 2 以降、法務評価書後）
- Utility Bar、Activity Timeline、Global Search
- SLDS Path コンポーネントの残りの適用箇所

### 3.3 設計のみ更新する項目（実装は次セッション）

前回セッションの `02_design_docs/` を以下の観点で更新：

- M2 Slack 通知: Grid 移行後の URL 再設定手順
- M3 GCal 仕様: 既存実装の拡張箇所
- M4 Daily: データモデル精緻化
- M5 Task: Kanban/List/Calendar 3ビューの詳細

---

## §4 5システム役割分担（v6/v7 踏襲）

| システム | 正本領域 | v8セッションでの関与 |
|---------|---------|-----------------|
| Salesforce | CRM・PM・8フェーズ | M1 モック + 認証情報揃えば実接続 |
| Slack | 非同期通知 | 実装スキップ（Grid 移行待ち）、EF内ログ蓄積のみ |
| Google Calendar | スケジュール | 既存実装維持、拡張は次セッション |
| Estateforce | 物件・日報・タスク | 本セッションの主戦場 |
| 旧スプレッドシート日報 | 廃止 | — |

---

## §5 既存 Estateforce 現状と地雷リスト

### 5.1 既存実装サマリー

- バックエンド: Flask + Gunicorn (`--worker-class gthread --threads 8 --workers 1`)
- フロント: 単一 `index.html`（SPA）
- 永続化: `/data` ディスク + GitHub Contents API
- リアルタイム同期: SSE + 3秒ポーリング
- 既存機能全リスト: `handover_supplement.md` §6 を参照

### 5.2 既存コードの地雷リスト（必読）

| # | 地雷 | 防止策 |
|---|------|-------|
| Z1 | 永続化忘れによるデータロス | `/data` or GitHub に必ず永続化、`init_data.py` の復元対象に追加 |
| Z2 | CJK部首ジオコーディング失敗 | 既存の正規化テーブルを撤去・破壊しない |
| Z3 | 自分の更新を他者更新と誤検知 | 保存直後に `syncTs()` を必ず呼ぶ |
| Z4 | 同名ワークスペース | UI側で警告 |
| Z5 | z-index 階層干渉 | Toast 5000、既存階層を破壊しない |
| Z6 | SSE 切断フォールバック | 新規 `bump_change()` 呼出時は切断時動作を検証 |
| Z7 | Render 再起動時のジョブ消失 | APScheduler 採用時は SQLAlchemyJobStore |
| Z8 | gunicorn workers=1 制約 | Web リクエスト内で重処理しない |
| Z9 | GitHub push 時の Auto-sync 衝突 | `git pull --rebase` 必須 |

### 5.3 美容業界特化フィールド（M6 物件マスタ設計時に含める）

- 水回り設備・電源容量・換気/排煙・天井高・業種制限・夜間営業可否・居抜き/スケルトン区分・内装解体費用負担・HPB未掲載競合手動登録枠

---

## §6 設定ファイル（config/estateforce_config.yaml）の想定値

本セッション開始時点で以下を想定：

```yaml
mvp_due_date: "2026-04-30"   # 今月末目標に変更
claude_default_model: "claude-haiku-4-5"
claude_api_monthly_budget_jpy: 4000
sonnet_enabled_in_initial_session: true  # M6精度改善時のみ限定使用
mobile_optimization_priority: "mvp_required"
hpb_scraping_decision: "phase_2_pending"
multi_user_in_mvp: true
multi_user_dummy_users: true  # Claude Code がダミーユーザー作成
branch_strategy: "reimplement_on_frosty_swartz"
notification_points: 5
continuous_mode: true  # 夜間継続稼働モード
```

設定ファイルに値が無い場合は §7 デフォルト判断ルールに従う。

---

## §7 デフォルト判断ルール（通知なしで判断する）

通知ポイント以外で判断が必要になった場合、以下のルールで自律決定：

| カテゴリ | ルール |
|---------|------|
| ライブラリ選定 | シンプル優先（simple-salesforce、slack_sdk、google-api-python-client） |
| エラーハンドリング | フェイルセーフ（機能しない場合は既存動作を維持） |
| UI 配色 | 既存グラデーション維持（#032D60 → #0176D3 → #1B96FF） |
| UI コンポーネント | 既存ボタン配色のトーン＆マナーを踏襲 |
| データ追加フィールド | 既存 JSON 構造に optional で追加（破壊的変更を避ける） |
| テスト失敗時 | 該当機能を `disabled` フラグで無効化し、次セッション送り |
| 外部API失敗時 | フォールバック処理を入れて処理継続 |
| マイグレーション | 後方互換性を保つ（旧フィールドは残す） |
| コミット粒度 | 1機能1コミット、メッセージに `[Tn]` タスクID付与 |
| ダミーユーザー | `test_user_manager`, `test_user_member`, `test_user_viewer` の3名 |
| モバイル最適化 | viewport meta + CSS media query、JS差分最小化 |
| セッション時間残10分 | 新規実装停止、引継ぎシート作成に全リソース |

---

## §8 作業進行（時間ボックス管理）

### フェーズ0: セッション開始（0〜15分）

1. 開始時刻を `data/session/v8_started_at.txt` に記録
2. 設定ファイル `config/estateforce_config.yaml` を読み込み
3. 環境変数の存在確認
   - 必須: ANTHROPIC_API_KEY, GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH, SECRET_KEY
   - オプション: SF_CLIENT_ID, SF_PRIVATE_KEY_PATH, SF_USERNAME, SF_LOGIN_URL
4. **現データの GitHub バックアップを取得**（データロス防止）
5. `docs/session_v8/` ディレクトリ作成

### フェーズA: 現状把握（15〜60分）

1. `claude/frosty-swartz` ブランチに切替（最新プル）
2. リポジトリ全体構造把握
3. 前セッション (`session_v7/`) の成果物読込
4. romantic-murdock-d02008 ブランチの参照（チェックアウトせず `git show` で差分確認）
5. 差分レポート `docs/session_v8/01_phase_a_summary.md` 作成

### 🔔 通知ポイント N1（60分時点）

`docs/session_v8/notifications/N1_branch_integration.md` に以下を書き込み、30分待機：

```markdown
# N1: ブランチ統合方針の最終確認

## 現状
- frosty-swartz ブランチ: 完全版（30+機能保持）
- romantic-murdock-d02008 ブランチ: 簡易版 + 前回セッション成果（M6/M8/M9）

## romantic-murdock から参考にする実装
- claude_client.py: Anthropic SDK のラッパー設計パターン
- claude_cost.py: コスト監視ロジック
- classification.py: PDF分類ロジック
- slack_notify.py: Slack通知インターフェース（現状未使用）

## 方針（デフォルト）
frosty-swartz 上で再実装。romantic-murdock のコードを参照しつつ、完全版の既存機能と整合させる。

## 岩本様への確認
この方針で進めてよろしいですか？
- Yes → 続行
- No → 別方針をこのファイルに追記してください

30分待機します。回答なき場合デフォルト方針で続行します。
```

### フェーズC: 設計ドキュメント更新（60〜90分）

- 前セッションの `02_design_docs/` を frosty-swartz 版として更新
- mvp_due_date 変更（2026-04-30）を反映
- 継続稼働モードでの運用仕様を追加

### フェーズD: 実装（90〜630分）

§3.1 の T4〜T10 を順次実施。各タスクで以下を守る：

- 実装前に対応テストの雛形を書く
- 実装後にテストを実行
- 既存機能の Smoke Test（BGM 再生・猫アニメ・物件ピン色・選定基準パネル位置・全画面ビュー動作）を実行
- 1タスク完了ごとに commit（メッセージ: `[T4] コスト監視ダッシュボード完成版`）

### 🔔 通知ポイント N2（T9 直前）

M1 SF 実接続テストの直前に、`docs/session_v8/notifications/N2_sf_auth.md` に：

```markdown
# N2: Salesforce 認証情報の確認

M1 の実接続テストに入ります。以下の環境変数が必要です：

- SF_CLIENT_ID
- SF_PRIVATE_KEY_PATH（または SF_PRIVATE_KEY の内容）
- SF_USERNAME
- SF_LOGIN_URL（通常 https://login.salesforce.com）

## 確認方法
Render Dashboard > Environment タブで上記が設定されているかご確認ください。
設定済みであれば、このファイルに「OK」と追記してください。
未設定の場合は「未設定」と追記してください（M1実接続テストはスキップし、モックのまま次タスクへ）。

60分待機します。
```

### 🔔 通知ポイント N3（T7 完了時）

M7 マルチユーザー実装完了時、作成したダミーユーザーの確認：

```markdown
# N3: マルチユーザーのダミー確認

以下の3ユーザーをダミーとして作成しました：

| ID | 名前 | メール | ロール |
|---|------|------|------|
| u001 | テスト管理者 | test_admin@example.com | admin |
| u002 | テスト担当者 | test_member@example.com | member |
| u003 | テスト閲覧者 | test_viewer@example.com | viewer |

岩本様（k.iwamoto@lime-fit.com）は admin ロールとして別途設定済みです。

## 岩本様への確認
本セッションではこのダミーのまま続行します。
実在ユーザーへの差し替え希望があれば、このファイルに名前・メール・ロールを追記してください。
30分待機します。回答なき場合ダミーのまま続行します。
```

### 🔔 通知ポイント N4（必要時・複数回可）

設計判断で v7/v8 仕様から逸脱する必要が生じた場合：

```markdown
# N4-{連番}: 設計判断の要求

## 状況
（発見した問題）

## 選択肢
- A: （選択肢A）
- B: （選択肢B）

## デフォルト
30分回答なき場合、A を採用して続行します。
```

### フェーズE: 検証・デプロイ（630〜660分）

1. 既存機能 Smoke Test（30+ 機能）
2. 追加機能動作確認
3. 統合テスト
4. 本番デプロイ（`git pull --rebase origin claude/frosty-swartz` → `git push`）
5. 本番 Smoke Test（curl で HTML 文字列確認）

### フェーズF: 引継ぎ（660〜720分）

1. `00_session_summary.md` 作成
2. `04_handover_to_next_session.md` 作成
3. `07_rollback_plan.md` 作成
4. `06_cost_estimate_actual.md` 作成

### 🔔 通知ポイント N5（720分時点）

`docs/session_v8/notifications/N5_completion.md` に完了報告：

```markdown
# N5: セッション完了報告

## 実施時間
XXX分 / 720分

## 完了タスク
- [x] T1: セッション開始
- [x] T2: 差分レポート
- [x] T3: 設計更新
- （略）

## 未完了タスク・次セッション送り
- [ ] Tn: XXX（理由）

## 主要成果物パス
- 設計書: docs/session_v8/02_design_docs/
- 引継ぎシート: docs/session_v8/04_handover_to_next_session.md
- 実装: （ファイル一覧）

## 次セッション最優先事項
1. XXX
2. XXX

## 本番デプロイ状況
- 成功 / 失敗（理由）

## 実測コスト
- Haiku: ¥XXX
- Sonnet: ¥XXX
- 合計: ¥XXX（月予算 ¥10,000 に対して X%）
```

---

## §9 M1 SF連携の段階的実装指針

SF 認証情報が揃っている/いないに関わらず、以下の段階で実装：

### 9.1 モックレイヤー（T8、認証不要）
- `salesforce_client.py` を作成
- メソッド: `push_candidate_property(pm_id, slot, property_data)`, `update_phase(pm_id, phase)` など
- 実装中は環境変数 `SF_MOCK_MODE=true` で動作
- レスポンスはダミーJSON

### 9.2 実接続への切替（T9、認証必要）
- 環境変数 `SF_MOCK_MODE=false` で切替
- simple-salesforce ライブラリ使用
- JWT Bearer Flow で認証
- エラー時は自動的にモックにフォールバック（ログに記録）

### 9.3 EF → SF のトリガー
物件申込ステータスが「申込確定」に変わったタイミングで以下を実行：

```python
# property status = "申込済" になった時のフック
def on_property_applied(property_id, ws_id):
    props = get_applied_properties(ws_id)
    if len(props) == 3:
        # 3物件揃った時点で SF にプッシュ
        pm_id = get_pm_id_for_workspace(ws_id)
        for i, prop in enumerate(props):
            sf_client.push_candidate_property(pm_id, slot=i+1, property_data=prop)
```

### 9.4 フィールドマッピング

想定（実フィールド API 名は認証情報提供時に確認・調整）：

| EF フィールド | SF フィールド |
|-------------|-------------|
| property.name | 候補物件1__c / 候補物件2__c / 候補物件3__c |
| property.address | （同上に結合） |
| workspace.name | 出店エリア__c |

---

## §10 成功基準（本セッション）

### 必達
- [ ] frosty-swartz 完全版の上で M6/M8/M9 の完成版が動作
- [ ] M7 マルチユーザー基盤が動作
- [ ] M1 モックレイヤーが完成
- [ ] M10 モバイル最適化（物件詳細最優先）が動作
- [ ] 既存 30+ 機能すべてが維持されている
- [ ] 本番デプロイ済み
- [ ] 引継ぎシート完成

### 条件付き達成（認証情報揃い時）
- [ ] M1 SF連携の実接続テスト合格

### 次セッション送り（予定通り）
- [ ] M2 Slack 実装（Grid 移行待ち）
- [ ] M3 GCal 双方向同期
- [ ] M4 Daily
- [ ] M5 タスク管理
- [ ] M10 の残り画面（スケジュール画面等）

---

## §11 美意識（短く）

- エラーメッセージは突き放さず、次の行動を示す
- 既存の遊び心（BGM・猫アニメ）は尊重
- 12時間タイムボックスを美意識で延長してはならない
- 細部磨き込みは次セッション以降の余力で

---

## 付録A 参照ファイル

- `handover_supplement.md`: 既存実装の要点
- `estateforce_claude_code_prompt_v7.md`: 前回（5時間）プロンプト
- `docs/session_v7/`: 前回セッション成果物（romantic-murdock ブランチにあり）

---

**それでは §8 フェーズ0 から開始してください。最初の作業は開始時刻記録とデータバックアップです。**
