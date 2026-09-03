# 稟議書（不動産取得・事業計画）— 春日部市東中野1523-13

生活保護・要介護高齢者向け住宅型有料老人ホーム（9室）用の戸建取得稟議と事業稟議を、
一つの文書に「第Ⅰ部 物件取得稟議」「第Ⅱ部 事業稟議」「第Ⅲ部 総合判定」「別紙A〜F」として分離・統合したもの。

## 成果物
- `稟議書_春日部市東中野1523-13.pdf` … 決裁用PDF（A4・約47頁）
- `index.html` … 同内容のHTML（画像埋め込み・単体で閲覧可）
- `編集版_稟議書_春日部市東中野1523-13.html` … **文章を直接編集できる版**。Chromeで開き「編集モード」→修正→「HTMLをダウンロード」で保存、「印刷／PDF保存」で配布用PDFと同じ体裁のPDFを出力できる（余白「既定」・背景のグラフィックON）。

## 文章を修正するときの使い分け
| 目的 | 方法 |
|---|---|
| 文章・表現の修正 | 編集版HTML（またはclaude.aiの編集版アーティファクト）で直接編集→保存→印刷でPDF |
| 価格・室数・単価など前提の変更（全数値を再計算） | `build/model.py` の PARAMS／PRICING を編集して下記コマンドで再生成 |
| 調査数値・出典の更新 | `build/research.py` を編集して再生成 |

## 再生成（数値を変えて作り直す）
```
cd build
python3 gen.py ../index.html ../稟議書_春日部市東中野1523-13.pdf   # 閲覧版HTML＋PDF
python3 gen.py editable ../編集版_稟議書_春日部市東中野1523-13.html  # 編集版HTML
```
- `build/model.py` … 収支・価格モデル（PARAMS／PRICING を編集すると全数値が再計算される）
- `build/research.py` … 調査で得た数値・出典URL（別紙Aに自動掲載）
- `build/gen_*.py` … 各部の文章・表の生成
- PDF化は Chromium headless（`/opt/pw-browsers/chromium-*/chrome-linux/chrome`）を使用。フォントは Noto Serif JP / Noto Sans JP（ローカルに無い場合は Google Fonts から読み込み）

## 元資料
- `source/` … 元の稟議書雛形（2026-08-18）、販売図面、9室割付図、1棟トータルP/L v2
