# ハジマル（aisalon-hajimaru.com）

まつエク・マツパ・眉毛サロンの開業支援サービス「ハジマル」の LP。静的 HTML/CSS のみ（ビルド不要）。

## 経緯

2026年6月にローカル（`website/hajimaru`）で作成・公開していたが、ソースがリポジトリに未コミットのままだったため、
Google ドライブの「ハジマル SNS content-calendar」に残っていた訴求・数値・LINE URL をもとに再作成した。

## ローカル確認

```sh
python3 -m http.server 8200 --directory website/hajimaru
```

`.claude/launch.json` の `hajimaru` と同じ設定。

## 公開前に確認すること

- フッターの「運営会社名」「所在地」（`index.html` の TODO コメント箇所）。物件の仲介を行う場合は宅建業の免許番号も記載する
- 実績の数値（全国200店舗以上の出店サポート／数百件の美容所登録）がそのまま使えるか
- LINE の URL（`https://lin.ee/5txU0LR`）
- SNS 自動投稿が参照している `/sns-img/ig-01.png`〜`ig-10.png` と `/videos/` は未復元。再公開時に同じパスへ置かないと投稿画像のリンクが切れる

## 公開

静的ホスティング（Vercel など）でルートディレクトリを `website/hajimaru` にして配信し、`aisalon-hajimaru.com` を割り当てる。
