# 価格交渉マンガ（心情・社会的意義から Evidence につなげる価格交渉）

社内マニュアル『心情・社会的意義からEvidenceにつなげる価格交渉』（PDF・21ページ）を、
**施設長（うさ耳）** と **新人スタッフ（くま耳）** の掛け合いで描いた全11ページの学習マンガです。
外部の画像生成サービスは使わず、SVGベクター作画＋Webフォントだけで構成しています（無料・再編集可）。

## ファイル

| パス | 内容 |
| --- | --- |
| `index.html` | マンガ本体。ブラウザで開くとそのまま読めます。キャラクター（表情・ポーズ）はページ内の JS で SVG 描画 |
| `fonts/` | 使用フォント（Google Fonts の OFL ライセンス書体を使用文字のみにサブセット化） |
| `output/negotiation-manga.pdf` | 印刷・配布用 PDF（800×1131px、全11ページ） |
| `output/page-XX.png` | 各ページの PNG（2倍解像度） |
| `render.py` | `index.html` から PDF/PNG を再生成するスクリプト |

## 再レンダリング

```bash
pip install playwright && playwright install chromium
python3 negotiation-manga/render.py --check   # --check で吹き出しのはみ出しを一覧表示
```

## 編集のしかた

- セリフ・キャプションは `index.html` の各 `<section class="pg">` 内を直接編集します。
- キャラクターは `<div class="char" data-who="s|n|w" data-expr="…" data-pose="…" data-flip="1">` で配置します。
  - `data-who`: `s`=施設長、`n`=新人スタッフ（くま耳）、`w`=スタッフ（おおかみ耳・差し替え用）
  - `data-expr`: `normal / smile / laugh / talk / surprised / worried / serious / think / determined / pout`
  - `data-pose`: `bust / point / phone / note / tablet / camera / fist / stop / hands / chin / cross`
- 吹き出しは `.bb`（`t-l / t-r / t-b / t-t` で尾の向き、`--tx / --ty` で尾の位置）、複数を縦に積む場合は `.stack` で囲みます。

## 完成版（画像生成AIによる作画）

`book/` に、ChatGPT で生成した全ページ（キャラ統一版）を収めた完成版があります。

| パス | 内容 |
| --- | --- |
| `book/index.html` | 本のようにページをめくれるビューア（右綴じ、見開き／単ページ自動切替、キーボード・スワイプ対応） |
| `book/pages/01〜14.jpg` | 表紙・本編11ページ（PHASE 6 は2枚）・奥付・裏表紙 |
| `book/negotiation-manga-book.pdf` | 配布用 PDF（13ページ） |
| `generated/` | ChatGPT 生成の元画像と、吹き出し文字の打ち直し用 spec（`retext.py` 参照） |
| `characters/unified_sheet.png` | 3人のキャラ統一設定画（ChatGPT に添付する「正」の参照画像） |
| `prompts/chatgpt-prompts.md` | ChatGPT 用のページ別プロンプト |
