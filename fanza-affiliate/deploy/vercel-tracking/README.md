# トラッキング用リダイレクト（Vercel Functions, 無料枠）

`python -m affiliate_bot bootstrap` が自動でデプロイします（Vercel のログイン／トークン発行だけ人間）。
手動の場合:

```bash
cd fanza-affiliate/deploy/vercel-tracking
npx vercel --prod --yes            # 初回はプロジェクト作成
npx vercel env add TRACKING_SECRET production   # affiliate_bot と同じ値
```
