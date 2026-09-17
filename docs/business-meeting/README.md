# business-meeting — 第1回 全体ミーティング資料

老人シェアハウス事業の立ち上げ全体MTG（2026年9月7日）用の一式。

| ファイル | 用途 | 体裁 |
|---|---|---|
| `kickoff-report.md` | **報告文（読み上げ原稿）**。スライド番号 `[S◯]` つき。欠席者向け要約と想定質問を付録に収録 | Markdown |
| `kickoff-deck.html` / `.pdf` | 投影用スライド 19枚 | 16:9（338.667 × 190.5mm） |
| `screening-flow.html` / `.pdf` | 物件 一次判定フロー v1.1（10項目・否決理由コードつき） | A4 縦 1枚 |
| `acceptance-criteria.html` / `.pdf` | 入居 受け入れ可否ライン表。施設へFAX・メール送付する | A4 縦 1枚 |
| `call-script.html` / `.pdf` | 老人ホーム 架電スクリプト v1.0 | A4 縦 1枚 |

## ビルド

```sh
./build.sh                 # 全部
./build.sh call-script     # 個別
```

Chromium のヘッドレス印刷でPDF化する。`CHROME_BIN` 未設定なら `/opt/pw-browsers/chromium` を使う。
実行するとページ数を出力するので、**A4ハンドアウトは必ず「1 ページ」であることを確認する**。

## 作りの決まりごと

- **共通スタイルは `_common.css` に置き、各ハンドアウトの `<style>` 内に `__CSS__` と書く。**
  ビルド時にその位置へ流し込まれる。`kickoff-deck.html` は自前のスタイルを持つので対象外。
- **ハンドアウトはA4 1枚に収める。** 溢れたら文字を削るより先に、行間・パディング・
  テーブルの `padding` を詰める。`call-script.html` のみ `@page` の余白を個別に詰めている。
- **チェックボックスは `class="cb"` だけを付ける。** `□` は `.cb::before` が出すので、
  HTML側に `□` を書くと二重になる。
- **テーブルの列幅は `<colgroup>` で明示する。** 幅を指定しないと日本語が意図しない位置で折り返す。
- 罫線は 1.5pt 以上にする。Chromium は罫線を小数座標の塗り矩形として出力するため、
  1pt 未満はアンチエイリアスで消えたように見える（`../hearing-sheet/README.md` に測定結果あり）。
