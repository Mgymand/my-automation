# 規約・法令・API 仕様の確認結果（2026-09-28 時点）

> 本システムの設計前提。X ヘルプセンターは自動取得を拒否する（JS チャレンジ）ため、英語版有料パートナーシップ方針は
> **2026-09-28 に運営者がブラウザで原文を確認**した（affiliate links / discount codes による commission が Paid Partnership に含まれ、
> Prohibited Industries に「Adult and sexual products and services」が含まれることを一次情報で確認済み）。
> `policy.verify_policy()` は直接取得（direct）のみを一次情報確認として扱い、Reader プロキシ経由（proxy）は参考情報に留める。

## 1. 結論（設計に効く事項）

| # | 事項 | 影響 | 本システムの対応 |
|---|---|---|---|
| 1 | **X 有料パートナーシップ方針**: 公式（日本語版, 2026-09-28 自動取得）で「アフィリエイトリンクや割引コードを含むポスト」が有料パートナーシップに該当し開示が必要と明記。公式英語版（2026-09-28 運営者が原文確認）は affiliate links / discount codes の commission を含め、Prohibited Industries に **「Adult and sexual products and services」** を列挙 | FANZA 成人向け商品の X 宣伝は「禁止カテゴリの有料パートナーシップ」に該当する | **HARD BLOCK**（`policy.py` の台帳。環境変数・人間の了承では解除不可）。センシティブメディアとして投稿可能なことと有料パートナーシップとして宣伝可能なことは別物。運用対象は DMM.com 一般商品。`verify_policy()` が公式ページの変更を監視し Attention Queue へ |
| 2 | X API v2 `POST /2/tweets` は `paid_partnership: true` で開示ラベルを付けられる | 本文の「PR」表記に加えて API でもラベル付与が可能 | `USE_PAID_PARTNERSHIP_LABEL=true`（既定）で本文・リプ両方に付与 |
| 3 | X 自動化ルール: 公式 API のみ／スパム禁止／複数アカウントで同一内容禁止／自動リプは @メンションされた投稿へのみ（2026-02-23〜）／トレンド便乗自動投稿禁止 | 画面操作 Bot・自動いいね・自動フォローは不可 | 投稿は `POST /2/tweets` のみ。いいね／フォロー／無差別リプ機能は実装しない。同一本文の重複はフェイルセーフで停止 |
| 4 | X 成人向けコンテンツ方針: 同意のある成人向けコンテンツは可。**メディアにセンシティブ設定**（アカウント設定「投稿するメディアをセンシティブな内容としてマーク」）が必須。プロフィール画像・ヘッダー・ライブ不可。未成年および生年月日未設定ユーザーは閲覧不可。未表示は強制ラベル＋設定変更＋制限の対象 | API v2 の投稿・メディアアップロードに「センシティブ」フラグは無く、**アカウント設定で行う** | `SENSITIVE_MEDIA_SETTING_CONFIRMED=true` を人間が確認するまで成人向けメディア投稿をブロック |
| 5 | X API 料金（pay-per-use、2026-09）: 投稿 $0.015／**URL 付き投稿 $0.20**／ポスト読取 $0.005／自分のデータ読取 $0.001／ユーザー読取 $0.01。旧 Free/Basic/Pro 廃止。`POST /2/tweets` は 100 req/15 分/ユーザー | リンク付き投稿は本文なし投稿の 13 倍。**メディア本文＋リンクはリプに**が費用面でも合理的 | 本文（メディア）$0.015 ＋ リンクリプ $0.20 ≒ ¥32/投稿。コストは `costs` に記録し利益から差し引く |
| 6 | DMM アフィリエイト参加規約（2026-03-01 改定）: 登録した媒体以外への広告掲載禁止（メルマガ・個人宛メール・SNS メッセージ等。**X は禁止列挙から削除**）、素材の無断改変禁止、ID 貸与禁止、自己アフィリ・虚偽クリック禁止、当社キーワードの広告出稿禁止。ラストクリック帰属 | X アカウントを**媒体として登録**して運用する | `DMM_MEDIA_REGISTERED=true` を人間が確認するまで投稿しない |
| 7 | DMM ガイドライン: 過度な暴力・犯罪助長・**児童ポルノ相当は一切禁止**・名誉毀損・**他者著作物の無断転載禁止**・スパム禁止・訪問者を著しく不快にする内容禁止 | 素材は DMM 提供のもののみ | 画像/動画は API が返す DMM ドメインの URL のみ許可（`media_rights_ok`）。NG ワード辞書で未成年・非同意想起表現を排除 |
| 8 | DMM ヘルプ「X にサンプル動画を掲載しても違反ではないか」: **無料動画ツール／サンプル動画として提供されているもののみ**掲載可。提供方法以外は動作保証外。商品ページの共有ボタンは X 非対応 | サンプル動画の**切り抜き・テロップ・音声差し替えは不可**（尺のトリムは承認プロデューサーのみ） | 動画は `sampleMovieURL` をそのまま使用。編集処理は実装しない |
| 9 | DMM ヘルプ「ステマ規制対応」: 各媒体で**客観的に視認できる範囲で「広告」「宣伝」「プロモーション」「PR」**の文言を用い、DMM との関係を明示することを**必須** | 全投稿に PR 表記 | `compliance.has_disclosure` が無い投稿は公開不可。既定は `【PR】` を本文末尾＋リプ先頭 |
| 10 | 景品表示法ステマ規制（2023-10-01 施行）: 規制対象は事業者（広告主）だが、一般消費者が広告と判別困難な表示は不当表示。SNS 投稿も対象 | 同上 | 同上 |
| 11 | FANZA 報酬: カテゴリ別に最大 10〜70%（動画は 2025-07 時点で最大 20% のアップ中の報道あり）。最低支払 ¥5,000／月末締め翌月払い。X 登録は公開アカウント・投稿 5 件以上・18 禁表記 | 報酬率は環境変数で設定し、実測で補正 | `DMM_PAYOUT_RATE`（既定 0.20）。成果 CSV 取込で実測 EPC に置換 |
| 12 | DMM API v3: `ItemList` は 1 リクエスト最大 100 件、短時間の連続呼び出しはアクセス制限。レポート API は無い（成果は管理画面 CSV） | 投稿単位の成果は自前トラッキング＋CSV 取込で帰属 | `DMMClient` は最低 1 秒間隔。`ingest-conversions --csv` |

## 2. 人間が確認・設定すべき項目（チェックリスト）

これらは `python -m affiliate_bot bootstrap` が順に案内する。本人操作が必要な瞬間だけ `★ここだけ人間★` と表示される。

- [x] 一次情報の確認（英語版、2026-09-28 運営者）: `help.x.com/en/rules-and-policies/paid-partnerships-policy`。禁止カテゴリから成人向けが外れた場合のみ `policy.py` の台帳を更新する（設定では変更できない）
- [ ] 運用対象は **DMM.com 一般商品**（`DMM_SITE=DMM.com`、既定）。FANZA を指定すると bootstrap が BLOCKED を表示し切替を提案する
- [ ] X アカウント設定「投稿するメディアをセンシティブな内容としてマーク」（水着・グラビア等を扱う場合）
- [ ] DMM 媒体登録の審査申請（申請文は bootstrap が生成）→ 承認後に bootstrap で「承認済み」と入力
- [ ] X Developer: 登録・クレジット購入・App 権限（Read and write）・キー発行（bootstrap が手順と設定値を提示）
- [ ] DMM API ID の発行（規約同意）
- [ ] プロフィール画像・ヘッダーに成人向け表現を使わない／bio に PR 表記
- [ ] 複数アカウント運用時は `accounts` テーブルにテーマ・対象・戦略を必ず分ける（同一内容の投稿は禁止）

## 3. 参照した一次・二次資料

- X 自動化ルール: https://help.x.com/en/rules-and-policies/x-automation （二次: opentweet.io, socialnexis.com の 2026 解説）
- X 開発者ポリシー: https://docs.x.com/developer-terms/policy
- X 成人向けコンテンツ方針: https://help.x.com/en/rules-and-policies/adult-content ／ メディア設定: https://help.x.com/en/rules-and-policies/media-settings
- X 有料パートナーシップ方針: https://help.x.com/en/rules-and-policies/paid-partnerships-policy （二次: note.com/munou_ac, TechCrunch 2026-03-02, @XCreators 告知）
- X API 料金: https://docs.x.com/x-api/getting-started/pricing ／ 投稿作成: https://docs.x.com/x-api/posts/manage-tweets/introduction （`paid_partnership`）／ メディア: https://docs.x.com/x-api/media/quickstart/media-upload-chunked
- DMM アフィリエイト参加規約: https://terms.dmm.com/affiliate_service/ ／ ガイドライン: https://terms.dmm.com/affiliate_guideline/
- DMM ヘルプ: サンプル動画の X 掲載 https://support.dmm.com/affiliate/article/47545 ／ 動画素材 https://support.dmm.com/affiliate/article/44088 ／ ステマ規制対応 https://support.dmm.com/affiliate/article/48085 ／ 規約違反非承認 https://support.dmm.com/affiliate/article/48806
- DMM API ガイド: https://affiliate.dmm.com/api/ （日本国外からは地域制限で閲覧不可。パラメータは公開クライアント実装で確認）
- 消費者庁 ステルスマーケティング規制: https://www.caa.go.jp/policies/policy/representation/fair_labeling/stealth_marketing
- 参加規約 2026-03-01 改定の解説: https://note.com/maid_h/n/nf5d5845fcc56
