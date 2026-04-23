# Estateforce 既存実装サマリー（Claude Code v7 セッション補助ファイル）

> このファイルは v7 プロンプトの補助情報です。
> handover_complete.md（引継ぎシート完全版）の代わりに、
> Claude Code が実装作業に必要とする要点だけを抽出しています。
> このファイルが手元にある場合、推測による現状把握ではなく
> 本ファイル + リポジトリ実コードの両方を参照してください。

---

## 1. 基本情報

| 項目 | 値 |
|------|------|
| アプリ名 | Estateforce |
| 本番URL | https://my-automation-b3it.onrender.com/ |
| GitHub Repo | Mgymand/my-automation |
| ブランチ | claude/frosty-swartz |
| ログインID | k.iwamoto@lime-fit.com |
| パスワード | Lime0201 |
| 認証方式 | Flask session、USERS辞書（app.py内）、SECRET_KEY 環境変数で署名 |

---

## 2. インフラ構成

### Render
- Web Service名: my-automation
- Service ID: srv-d7ah6s8gjchc73fpd6k0
- プラン: Starter（$7/月）
- Region: Ohio
- Runtime: Python 3.11.12
- 永続ディスク: 1GB、Mount Path `/data`（$0.25/月）
- スナップショット: 24時間ごと自動取得、7日間保持

### GitHub 同期
- 同期内容: データJSON（workspaces, properties, agents, schedules）+ アップロードPDF
- 同期方式: `sync_file_to_github()` で GitHub Contents API push（非同期、PDFのみ blocking=True）
- 環境変数: GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH

---

## 3. プロジェクト構成

```
/Users/kenshiniwamoto/projects/my-automation/
├── .claude/
│   └── worktrees/
│       ├── beautiful-heisenberg/   ← 作業用worktree（編集はここで行う）
│       └── frosty-swartz/          ← デプロイ用worktree（push元）
├── property-map/                    ← 実際のアプリ（Renderの rootDir）
│   ├── app.py                       ← Flaskバックエンド（全API）
│   ├── templates/
│   │   └── index.html               ← フロントエンド全体（SPA単一ファイル）
│   ├── init_data.py                 ← 起動時にGitHub→ローカルへ復元
│   ├── requirements.txt             ← flask, gunicorn, PyMuPDF
│   └── data/                        ← ローカルデータ（Renderでは /data に永続化）
│       ├── workspaces.json
│       ├── agents.json
│       ├── schedules.json
│       ├── pdfs/                    ← アップロードPDF
│       └── workspaces/
│           └── ws_*/properties.json
├── render.yaml                      ← Renderデプロイ設定
└── chrome-extension/                ← 無関係な別プロジェクト
```

---

## 4. デプロイフロー（重要）

```bash
# 1. beautiful-heisenberg で編集
# 2. frosty-swartz にコピーしてpush
cd /Users/kenshiniwamoto/projects/my-automation/.claude/worktrees/frosty-swartz
cp /Users/kenshiniwamoto/projects/my-automation/.claude/worktrees/beautiful-heisenberg/property-map/templates/index.html property-map/templates/index.html
cp /Users/kenshiniwamoto/projects/my-automation/.claude/worktrees/beautiful-heisenberg/property-map/app.py property-map/app.py
git add property-map/
git commit -m "..."
git pull --rebase origin claude/frosty-swartz   # ⚠️ Auto-syncコミット対策で必須
git push origin claude/frosty-swartz
```

- 通常 5〜10分でデプロイ完了
- 確認は `curl https://my-automation-b3it.onrender.com/` でHTML内文字列確認推奨（WebFetchは15分キャッシュあり）

---

## 5. 技術スタック（現行）

| レイヤー | 技術 |
|---------|------|
| フロントエンド | HTML/CSS/JavaScript（単一 index.html） |
| 地図 | Leaflet 1.9.4 + OpenStreetMap (CARTO Voyager) + OpenRailwayMap |
| バックエンド | Flask + Gunicorn |
| PDFパーサー | PyMuPDF (fitz) |
| サーバー設定 | `gunicorn --worker-class gthread --threads 8 --workers 1`（SSE長時間接続用） |
| リアルタイム同期 | Server-Sent Events (SSE) + 3秒ポーリングフォールバック |
| 認証 | Flask session |
| 永続化 | /data ディスク + GitHub Contents API |

---

## 6. 既存実装機能の全リスト（必読 — 1つも壊さない）

### 6.1 ログイン画面
- Salesforce風クラウドロゴ + 「Estateforce」ブランディング
- グラデーション背景（#032D60 → #0176D3 → #1B96FF）
- 未ログイン時は全画面ブロック

### 6.2 地図表示（メイン）
- Leafletマップ、ピンで物件表示
- 駅は電車アイコン + 駅名ラベル
- ピンクリックで右サイドバー展開

### 6.3 物件ステータス（6種類）

| 色 | ラベル | fill |
|---|------|------|
| 🔵 blue | 未内見 | #2563eb |
| 🔴 red | 内見済 | #dc2626 |
| 🟢 green | 申込済 | #16a34a |
| 🟡 yellow | 審査通過 | #eab308 |
| ⚫ black | 審査落ち | #1e293b |
| 🌈 rainbow | 契約済 | SVG linearGradient（赤→橙→黄→緑→青→紫） |

### 6.4 物件登録（3方法）
1. **PDFアップロード**: 「+PDF」ボタン or ドラッグ&ドロップ → 住所・詳細自動抽出 → ジオコーディング
2. **手動入力**: 「手動入力」ボタン
3. **PDFドロップ**: 画面にPDFドラッグで即インポート

### 6.5 物件詳細（サイドバー）
- ヘッダー色がピン色と連動、右側に担当者名表示
- ステータス変更、備考、詳細項目（追加・削除可）、管理会社情報、メモ
- PDFダウンロードリンク + ページプレビュー
- 他エリアへの移動、削除

### 6.6 一覧表示
- テーブル形式（物件名、賃料、共益費、面積、築年数、敷金/保証金、礼金、交通、管理会社、TEL）
- ヘッダークリックでソート
- 検索ボックス（物件名・住所・詳細）
- 行クリックでインラインメモパネル展開
- セルダブルクリックで全文表示

### 6.7 エリア（ワークスペース）管理
- ツールバー左端のセレクトボックスで切替
- 駅登録（検索して追加、半径設定）
- 歯車アイコン: 設定モーダル（名前、駅、選定基準、中心座標、zoom）
- ゴミ箱アイコン: 削除（最後の1つは削除不可）

### 6.8 選定基準フローティングパネル
- 地図左上、ツールバーの下に配置
- 項目: 賃料上限、面積下限（希望ブース数）、駅徒歩、その他条件
- 責任者・担当者の名前を表示（エージェント登録に紐づく）
- 直接編集可能（800ms後に自動保存）
- −/+ ボタンで折りたたみ
- ワークスペース切替時に自動更新

### 6.9 条件比較パネル
- 地図左上、選定基準の上に配置
- 物件詳細項目を選択すると地図上の全ピンにラベル表示
- 固定順: 物件名、賃料、共益費、面積、築年数、敷金/保証金、礼金、交通、管理会社、TEL
- −/+ ボタンで折りたたみ

### 6.10 エージェント管理
- 全画面ビュー（紫ボタン「エージェント」）
- 左カラム: 一覧、右カラム: 詳細 or 登録/編集フォーム
- 項目: 名前、メール、電話番号、統括エリア（責任者）、担当エリア（担当者）、備考
- 統括エリア: 水色チップで複数選択
- 担当エリア: 紫チップで複数選択
- エージェント選択で担当物件一覧（担当+統括エリア横断）

### 6.11 スケジュール/カレンダー
- 全画面ビュー（オレンジボタン「スケジュール」）
- 月表示 / 週表示切替、前後ナビ、今日ボタン
- 日付クリックで予定作成
- 予定の種類: 内見、調査、打合せ、その他（色分け）
- 予定作成モーダル項目: タイトル（必須）、種類、日付（必須）、開始/終了時間、依頼者/担当者、物件、お客様名（必須）、契約種別（法人/個人、必須）、融資（あり/なし、必須）、既存事業内容（必須）、メモ
- Googleカレンダー連携: タイトル入力時に「Googleカレンダーに追加」ボタン出現、依頼者・担当者のメアドが招待者として設定される

### 6.12 契約管理
- 全画面ビュー（赤ボタン「契約管理」）
- 進行中タブ: 申込済（緑）・審査通過（黄）の物件のみエリアごとに表示
- 審査通過の物件に「契約完了にする」ボタン → 虹色ピンに遷移（contractedAt記録）
- エリア全体を「アーカイブ」ボタンで契約完了へ移動
- 契約完了タブ: アーカイブ済みエリアを虹色グラデーション表示

### 6.13 月次統計
- 全画面ビュー（紫ボタン「統計」）
- 過去12ヶ月の推移グラフ: SVG LineChart、5ステータスの月別件数推移
- エリア別契約マトリクス: 行=エリア×列=月、契約件数、合計列
- 契約0のエリアは自動非表示

### 6.14 バックアップ
- 全画面ビュー（グレーボタン「バックアップ」）
- ZIPダウンロード: 全データ（JSON+PDF）を1つのZIPで取得
- ZIP復元: アップロードで全データ復元、GitHubへ自動同期
- Render自動スナップショット（24時間ごと、7日保持）と二重化

### 6.15 地図コントロール
- 右下の⚙ボタン: クリックでズーム(+/-) と移動矢印(上下左右) 出現
- Leafletのデフォルトズームコントロールは無効化

### 6.16 BGM（⚠️ 廃止禁止 — 遊び心要素）
- 右下に▶ボタン: BGM再生/停止（リピート）
- 再生中は猫SVGがBPM140に合わせて踊る（catBounce/catWaveL/catWaveR/catTail）
- 楽曲: Sunoで生成した「物件を探せ息絶えるまで」

---

## 7. APIエンドポイント完全一覧（重複・衝突回避用）

### 認証
- `POST /api/login` — `{email, password}` でログイン
- `POST /api/logout` — ログアウト
- `GET /api/auth-check` — 認証状態確認

### リアルタイム同期
- `GET /api/sync` — タイムスタンプ取得（フォールバック）
- `GET /api/events` — SSEストリーム（change/init イベント配信、15秒ごとpingでキープアライブ）

### ワークスペース
- `GET /api/workspaces` — 一覧
- `POST /api/workspaces` — 作成（name, stations, criteria, center, zoom）
- `PUT /api/workspaces/<id>` — 更新（name, stations, center, zoom, criteria, archived, archivedAt）
- `DELETE /api/workspaces/<id>` — 削除（最後の1つは不可）
- `PUT /api/workspaces/active` — アクティブ切替

### 物件
- `GET /api/properties?ws=<wsId>` — 一覧
- `POST /api/properties/manual?ws=<wsId>` — 手動登録
- `POST /api/upload?ws=<wsId>` — PDF登録（住所自動抽出→ジオコーディング）
- `PUT /api/properties/<id>/memo?ws=<wsId>` — メモ更新
- `PUT /api/properties/<id>/color?ws=<wsId>` — ステータス変更
- `PUT /api/properties/<id>/details?ws=<wsId>` — 詳細更新
- `PUT /api/properties/<id>/move?ws=<wsId>` — エリア間移動
- `PUT /api/properties/<id>/contract?ws=<wsId>` — 契約済みマーク（contractedAt記録）
- `DELETE /api/properties/<id>?ws=<wsId>` — 削除

### エージェント
- `GET /api/agents` — 一覧
- `POST /api/agents` — 登録（name, email, phone, area, managerArea, memo）
- `PUT /api/agents/<id>` — 更新
- `DELETE /api/agents/<id>` — 削除
- `GET /api/agents/<id>/properties` — 担当物件（area + managerArea 横断）

### スケジュール
- `GET /api/schedules?month=YYYY-MM` — 一覧
- `POST /api/schedules` — 作成（title, requesterId, assigneeId, agentId, propertyId, type, date, startTime, endTime, memo, customer, contractType, financing, business）
- `PUT /api/schedules/<id>` — 更新
- `DELETE /api/schedules/<id>` — 削除

### 統計・バックアップ
- `GET /api/stats/monthly` — 月次統計データ（workspaces + entries）
- `GET /api/backup/download` — 全データZIP
- `POST /api/backup/restore` — ZIPから復元
- `GET /api/debug/data` — /data内の全ファイル一覧（ログイン必須、デバッグ用）

### ファイル
- `GET /pdf/<filename>` — PDFダウンロード
- `GET /pdf-images/<filename>?page=N` — PDFページをPNG変換
- `GET /api/geocode-station?name=<駅名>` — 駅名→緯度経度

---

## 8. データ構造

### workspaces.json
```json
{
  "activeWorkspace": "ws_1",
  "workspaces": [
    {
      "id": "ws_1",
      "name": "新オフィス・研修室",
      "stations": [{"name": "渋谷駅", "lat": 35.658, "lon": 139.7016, "r": 180}],
      "center": {"lat": 35.6595, "lon": 139.7005},
      "zoom": 16,
      "criteria": {"maxRent": "100万円", "minArea": "40坪", "walkMinutes": "5分以内", "other": "..."},
      "archived": false,
      "archivedAt": 0
    }
  ]
}
```

### workspaces/<wsId>/properties.json
```json
[
  {
    "id": "prop_1712567890123",
    "name": "TMSビル 4F",
    "address": "東京都渋谷区渋谷3-1-6",
    "lat": 35.658,
    "lon": 139.7016,
    "filename": "ＴＭＳビル4F@2.30.pdf",
    "details": {"賃料": "100万円", "面積": "44坪", "管理会社": "...", "TEL": "..."},
    "memo": "",
    "color": "blue",
    "contractedAt": 0
  }
]
```

### agents.json
```json
[
  {
    "id": "agent_1712...",
    "name": "田中太郎",
    "email": "tanaka@example.com",
    "phone": "03-1234-5678",
    "area": "ws_1,ws_1775556114635",
    "managerArea": "ws_1",
    "memo": ""
  }
]
```

### schedules.json
```json
[
  {
    "id": "sch_1712...",
    "title": "TMSビル 内見",
    "type": "内見",
    "date": "2026-04-15",
    "startTime": "10:00",
    "endTime": "11:00",
    "agentId": "agent_xxx",
    "requesterId": "agent_xxx",
    "assigneeId": "agent_yyy",
    "propertyId": "prop_xxx",
    "customer": "山田太郎",
    "contractType": "法人",
    "financing": "なし",
    "business": "飲食店",
    "memo": ""
  }
]
```

---

## 9. 実装上の重要な注意点（必読）

### 9.1 ジオコーディング
- **国土地理院API**: `msearch.gsi.go.jp/address-search/AddressSearch`
- **CJK部首正規化**: PDFから抽出される文字に⻄(U+2EC4)等が混入するため、明示的な変換テーブルで西(U+897F)に置換
  - **このテーブルを撤去・破壊してはならない**
- **番地正規化**: `X丁目Y番Z号` → `X丁目Y-Z`
- **フォールバック**: 失敗時は丁目レベルまで短縮して再検索

### 9.2 GitHub同期
- `sync_file_to_github(path, blocking=False)` — デフォルト非同期スレッド
- **PDFアップロード時のみ `blocking=True`** で同期実行（データロス防止）
- `bump_change()` 呼び出し時に全SSEクライアントへ通知

### 9.3 リアルタイム同期
- サーバー: `_event_listeners` リストで `queue.Queue` を管理、`bump_change()` で全クライアントに配信
- クライアント: EventSource で `/api/events` をリッスン、切断時は5秒ポーリングにフォールバック、10秒後に再接続試行
- gunicorn は `--worker-class gthread --threads 8 --workers 1` 必須（SSE長時間接続のため）

### 9.4 キャッシュ戦略
- `_ws_cache`, `_prop_cache`, `_agents_cache`, `_schedules_cache` は mtime ベース
- データ変更時に `bump_change()` + キャッシュ更新
- `/api/backup/restore` 時は全キャッシュをクリア

### 9.5 z-index 階層（⚠️ 新規Toast 等を追加する際の参考）
- `.toolbar`: 1000
- `.sidebar-header`: 1001
- `.compare-panel`, `.criteria-float`: 1001
- 全画面ビュー（#agent-view, #calendar-view, #contract-view, #stats-view, #backup-view）: 2000
- `#login-screen`: 99999
- モーダルオーバーレイ: 10000

→ **新規 Toast は z-index 5000 を推奨**（モーダルより下、全画面ビューより上）

### 9.6 選定基準・条件比較パネル
- `positionCriteriaFloat()` で `toolbar.bottom` の下に compare-panel → criteria-float を縦積み
- 各全画面ビュー開閉時に `hideCriteriaFloat()` / 再表示処理必須
- ピン詳細サイドバー開閉時にも同様

---

## 10. 既知の過去トラブル（地雷詳細）

### 10.1 データロス事件（2026-04-22）
- Render無料プランの `/tmp` がデプロイでリセット
- 約20エリアのワークスペースが消失
- Git履歴から5つ復旧、スクリーンショットから29エリアの名前を復元
- PDFは9ファイルのみGitHub同期済みだった
- **対策**: Starterプラン($7) + 永続ディスク `/data` ($0.25) にアップグレード済み
- **再発防止**: 全データを必ず `/data` か GitHub に永続化。新規データ構造は `init_data.py` の復元対象に必ず追加

### 10.2 PDFの「西」文字問題
- 住所の「西」がCJK部首の⻄(U+2EC4)になっていてジオコーディング失敗
- 正規化テーブル追加で解決
- **再発防止**: 既存テーブルを撤去しない、新規アドレス処理を入れる際は同テーブルを通す

### 10.3 ステータス変更が5秒後に戻る
- 自分の変更がポーリングで「他ユーザー変更」と誤検知
- `syncTs()` で保存直後にタイムスタンプ更新して解決
- **再発防止**: 保存直後に必ず `syncTs()` を呼ぶ既存パターンを踏襲

### 10.4 同名ワークスペース
- 既存の「K新宿」×2（ws_1775556114635, ws_1775573727463）
- 後者は「K新宿 (2)」→「神田・秋葉原」にリネーム
- ws_1775610444930 は「T/B本厚木」→「K/T本厚木/海老名/小田原」にリネーム
- **再発防止**: UI側で同名作成時に警告

---

## 11. 環境変数（Render Dashboard Environment タブ）

| 変数 | 用途 |
|------|------|
| RENDER | true |
| PYTHON_VERSION | 3.11.12 |
| GITHUB_TOKEN | GitHub Personal Access Token (contents:write) |
| GITHUB_REPO | Mgymand/my-automation |
| GITHUB_BRANCH | claude/frosty-swartz |
| SECRET_KEY | Flask session署名キー |
| ANTHROPIC_API_KEY | （v7セッションで新規追加） |

---

## 12. push時のよくあるエラー

- リモートに Auto-sync コミットが入っていることが多いため、毎回 `git pull --rebase` が必要
- Conflict発生時は Auto-sync側を受け入れ（`--theirs`）

---

## 13. 元仕様書に記載の未実装項目（v7 セッションでも未着手のまま）

- WebSocket化（現在SSE単方向）
- エージェント別月次統計
- 契約管理からスケジュール・タスク完了状況の連携強化
- PDF複数アップロード対応
- CSV/Excel インポート/エクスポート
- モバイル最適化UI
- パスワード変更UI（現在USERS辞書をコードで編集）
- 複数ユーザー対応（現在1アカウントのみ）

これらはv7プロンプト§3.1のMVP（M1〜M10）で順次対応予定。

---

## 14. 業務文脈（簡略）

- **株式会社GT-works**: 美容業界特化の賃貸仲介ブローカー（本ツール開発元・利用主体）
- **株式会社Lime**: サロンフランチャイズ運営（GT-worksのグループ会社）
- **顧客**: Limeのフランチャイズ加盟店オーナー
- **GT-worksの強み**: 全国の内装施工パートナーネットワークによる「物件＋内装」ワンストップ提案
- **利用想定**: 事業部内10〜20名、月100案件規模、月100〜300件のPDF処理
- **言語**: 日本語UI（必須）

---

**以上が現存システムの実装情報の要点です。これと v7 プロンプト + リポジトリ実コードの3点で、推測なしに作業を進めてください。**
