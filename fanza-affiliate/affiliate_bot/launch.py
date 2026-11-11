"""新規アカウントの設計（docs/ACCOUNT_STRATEGY.md の決定事項）と初期 10 投稿の生成。

- 名前・@候補・プロフィール・固定投稿は本モジュールの定数（他者のコピーではない）
- 初期 10 投稿は 10 種類の構造テンプレートに、DB にある実商品の事実（価格・割引・配信日・レビュー件数・平均）だけを埋める。
  価格・割引・レビュー・ランキングを捏造しない（該当データが無い型は商品事実を使わない文面にする）
- 出力は exports/launch/ に。X への投稿は人間。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Settings
from .db import Database, loads
from .policy import HUMAN_POSTING_NOTICE

ACCOUNT = {
    # 2026-11-11: 業者感を薄くする方針（人格型。名前＋ひとこと、一人称のゆるい文体）。他アカウントの名前・キャラクターは使わない
    "name": "なつめ｜安くなったら呟く人",
    "name_alternatives": ["しずく🌙夜のお買い物メモ", "ひなた｜セールだけ見てる人"],
    "handle_candidates": ["natsume_yasui", "natsume_yoru", "natsume_memo"],
    "bio": ("FANZAの人気作が500〜1000円まで下がったら、ゆるく呟いてます。セールで値下がりしたやつ、レビュー多めのやつ、"
            "無料で立ち読みできるやつが中心。リンクはリプに置いてます🔗 18歳未満は見ないでね／アフィリエイト（PR）含みます"),
    "brand": {"primary": "#1E293B（夜の紺）", "accent": "#FBBF24（月の黄）", "base": "#FFF7ED（生成り）",
              "motif": "三日月とマグカップ（夜にくつろぐ人）", "text": "アイコン・ヘッダーとも文字なし", "character": "なつめ（アニメ調のオリジナルのお姉さん。成人に見える絵柄・露出なし。業者感を出さない一人称）"},
    # 2026-11-11: 運営者の希望でアニメ調の「かわいいお姉さん」に。オリジナルの絵柄で、成人に見えること・露出しないこと（X はプロフィール画像に成人向け・センシティブな内容を禁止）
    "icon_prompt": ("original anime-style illustration of a cute, friendly adult woman in her mid-20s (older-sister type), smiling, "
                    "head-and-shoulders avatar, wearing a high-neck knit sweater, no cleavage, no lingerie, non-sexual, cozy night tones "
                    "with deep navy #1E293B background and a small warm yellow #FBBF24 crescent moon, no text, 1024x1024"),
    "header_prompt": ("wide banner 1500x500, soft hand-drawn night sky in deep navy #1E293B with a few small stars and a crescent moon in warm yellow "
                      "#FBBF24 at right, cozy and calm, lots of negative space, no text, no people, no photos"),
    "pinned_post": ("はじめまして、なつめです。\nFANZAの人気作が500〜1000円まで下がったタイミングを、夜にゆるく呟いてます。\n"
                    "・セールで値下がりした人気作\n・レビュー多めのやつ、無料で立ち読みできるやつ\n"
                    "リンクはリプに置いてます。気になるのがあればどうぞ。\n18歳未満の方は見ないでください【PR】"),
}

# 10 種類の構造テンプレート（文章ではなく構造。{} は DB の事実で埋める）
LAUNCH_TEMPLATES = [
    ("intro", "アカウント紹介", None),
    ("sale_alert", "セール速報", "discount"),
    ("actress", "女優訴求", "actress"),
    ("bargain", "激安作品", "cheap"),
    ("new", "新作", "new"),
    ("hidden", "掘り出し作品", "review"),
    ("short", "短文", "any"),
    ("video", "動画向け", "movie"),
    ("roundup", "まとめ", "many"),
    ("follow_reason", "フォロー理由強化", None),
]


def _pick(products: list[dict], kind: str, used: set[str]) -> dict | None:
    def ok(p):
        return p["content_id"] not in used
    cands = [p for p in products if ok(p)]
    if kind == "discount":
        cands = [p for p in cands if float(p.get("discount_rate") or 0) >= 0.3]
    elif kind == "actress":
        cands = [p for p in cands if p.get("actresses")]
    elif kind == "cheap":
        cands = [p for p in cands if p.get("price") and p["price"] <= 500]
    elif kind == "new":
        cands = sorted([p for p in cands if p.get("release_date")], key=lambda p: p["release_date"], reverse=True)
    elif kind == "review":
        cands = [p for p in cands if (p.get("review_avg") or 0) >= 4.0 and 5 <= int(p.get("review_count") or 0) <= 60]
    elif kind == "movie":
        cands = [p for p in cands if p.get("sample_movie_url")]
    return cands[0] if cands else None


def _price(p: dict) -> str:
    return f"{int(p['price']):,}円" if p.get("price") else ""


def _disc(p: dict) -> str:
    d = float(p.get("discount_rate") or 0)
    return f"{int(d * 100)}%OFF" if d >= 0.05 else ""


def build_launch_posts(db: Database, settings: Settings) -> list[dict]:
    rows = db.q("SELECT * FROM products ORDER BY eav DESC LIMIT 60")
    products = []
    for r in rows:
        d = dict(r)
        for k in ("genres", "actresses", "sample_image_urls", "campaign"):
            d[k] = loads(d.get(k), [])
        products.append(d)
    used: set[str] = set()
    out: list[dict] = []
    pr = "【PR】"
    for key, label, kind in LAUNCH_TEMPLATES:
        p = _pick(products, kind, used) if kind else None
        if kind == "movie" and not p:
            p = _pick(products, "movie", set())      # 動画付き商品が少ない場合は再掲を許可
        if kind == "many" and not p and products:
            p = products[0]                            # まとめは複数商品を再掲する型なので未使用に限らない
        if kind and not p and kind != "any":
            p = _pick(products, "any", used)
        text, media = "", None
        if key == "intro":
            text = ("はじめまして、なつめです。\nFANZAの人気作が500〜1000円まで下がったら、夜にゆるく呟いていきます。\n"
                    "リンクはリプに置きます。18歳未満の方は見ないでください【PR】")
        elif key == "follow_reason":
            text = ("ここで呟いてること\n・人気作が500〜1000円まで下がったタイミング\n・レビュー多めなのに安くなってるやつ\n・無料で立ち読みできるやつ\n"
                    "買い逃しが減ったらうれしいです。だいたい夜に更新【PR】")
        elif p:
            g = "・".join([x for x in p["genres"] if x][:2]) or "動画"
            a = "・".join(p["actresses"][:2])
            rel = str(p.get("release_date") or "")[:10]
            if key == "sale_alert":
                text = f"{_disc(p) or '割引中'}｜{_price(p)}\n{p['title']}\n{g}{('／' + a) if a else ''}\n期限は配信ページで要確認。リプ欄から。{pr}"
            elif key == "actress":
                text = f"{a or g} の1本。\n{p['title']}\n{(_price(p) + '。') if _price(p) else ''}{(_disc(p) + '。') if _disc(p) else ''}{g}。{pr}"
            elif key == "bargain":
                lp = p.get("list_price")
                normal = f"通常 {int(lp):,}円。" if lp and lp > (p.get("price") or 0) else ""
                text = f"{_price(p) or '低価格'}で買える。\n{p['title']}\n{g}{('／' + a) if a else ''}。{normal}{pr}"
            elif key == "new":
                text = f"{rel} 配信。\n{p['title']}\n{g}{('／' + a) if a else ''}{('。' + _price(p)) if _price(p) else ''}。{pr}"
            elif key == "hidden":
                rc, ra = int(p.get("review_count") or 0), p.get("review_avg")
                text = (f"レビュー{rc}件で平均{ra:.1f}。数は多くないけど評価が高い。\n" if (rc and ra) else "レビュー掲載中。\n") + f"{p['title']}\n{g}。{pr}"
            elif key == "short":
                text = f"{p['title']}。{g}。{(_price(p)) if _price(p) else ''}{pr}"
            elif key == "video":
                text = f"公式サンプル動画あり。\n{p['title']}\n{g}{('／' + a) if a else ''}。{pr}"
                media = p.get("sample_movie_url")
            elif key == "roundup":
                top = ([x for x in products if x["content_id"] not in used] + [x for x in products if x["content_id"] in used])[:3]
                lines = [f"{i}. {x['title'][:22]}{('（' + _price(x) + '）') if _price(x) else ''}" for i, x in enumerate(top, 1)]
                text = "今日のFANZA、価格つきで3本メモ\n" + "\n".join(lines) + f"\n詳細はリプ欄。{pr}"
                for x in top:
                    used.add(x["content_id"])
            if not media:
                imgs = p.get("sample_image_urls") or []
                media = imgs[0] if imgs else p.get("image_url")
            used.add(p["content_id"])
        else:
            text = f"（{label}: 該当する商品データが無いためスキップ。fetch-products 後に再生成）"
        out.append({"key": key, "label": label, "text": text, "product_id": p["content_id"] if p else None,
                    "media": media, "affiliate_url": p.get("affiliate_url") if p else None, "notes": [HUMAN_POSTING_NOTICE]})
    return out


def export_launch(db: Database, settings: Settings, out_dir: Path) -> Path:
    posts = build_launch_posts(db, settings)
    d = out_dir / "launch"
    d.mkdir(parents=True, exist_ok=True)
    lines = [f"# 新規アカウント立ち上げセット（{datetime.now(ZoneInfo(settings.timezone)).strftime('%Y-%m-%d')}）", "",
             f"## アカウント名: {ACCOUNT['name']}", f"@候補: {', '.join('@' + h for h in ACCOUNT['handle_candidates'])}", "",
             "## プロフィール文", ACCOUNT["bio"], "", "## ブランド", *[f"- {k}: {v}" for k, v in ACCOUNT["brand"].items()], "",
             "## アイコン生成プロンプト", ACCOUNT["icon_prompt"], "", "## ヘッダー生成プロンプト", ACCOUNT["header_prompt"], "",
             "## 固定投稿", ACCOUNT["pinned_post"], "", "## 初期 10 投稿（構造を変えた 10 種）", ""]
    for i, p in enumerate(posts, 1):
        lines += [f"### {i}. {p['label']}", p["text"], f"素材: {p['media'] or '-'}", f"Affiliate URL（リプ欄）: {p['affiliate_url'] or '-'}", ""]
    lines += ["## 注意", HUMAN_POSTING_NOTICE]
    (d / "launch.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for i, p in enumerate(posts, 1):
        (d / f"post{i:02d}_{p['key']}.txt").write_text(p["text"] + "\n", encoding="utf-8")
    return d
