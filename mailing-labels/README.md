# 角形A4号封筒用 宛名帯（郵送ラベル）

居宅介護支援事業所等 32 件への郵送用に、A4 用紙 1 枚に 210mm × 約74mm の帯を 4 枚配置した PDF を生成します。
点線で切り離して角形A4号封筒（228mm × 312mm）に貼ってください。

## ファイル

| ファイル | 内容 |
|---|---|
| `labels.pdf` | 印刷用 宛名帯（32 件・8 ページ） |
| `送付先確認一覧.xlsx` | 郵便番号・住所・正式名称・部数・確認度・出典URL の一覧（確認度「中」の行は黄色） |
| `addresses.json` | 送付先データ（上記 2 ファイルの元データ） |
| `make_labels.py` | `addresses.json` → `labels.pdf` |
| `make_checklist.py` | `addresses.json` → `送付先確認一覧.xlsx` |

## 使い方

```bash
pip install reportlab openpyxl
python3 make_labels.py      # labels.pdf を生成
python3 make_checklist.py   # 送付先確認一覧.xlsx を生成
```

印刷時は「実際のサイズ（100%）」で、用紙に合わせて縮小しない設定にしてください。
帯は `送付先確認一覧.xlsx` の No 順（1 ページ目の上から No.1, 2, 3, 4 …）に並んでいます。帯自体には番号を印字していません。

住所を修正する場合は `addresses.json` を編集して再生成してください。

## 敬称と個人宛の帯

各エントリの `honorific` で敬称を指定できます（省略時は「御中」。個人宛は `"honorific": "様"`）。
個人宛の住所データは `private/` に置き、Git には含めません（`.gitignore` 済み）。

```bash
python3 make_labels.py private/individuals.json private/labels_individuals.pdf
```
