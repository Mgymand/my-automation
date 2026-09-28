"""DMM 認証情報がない環境でパイプラインを通すための合成商品データ（ドライラン専用）。
実運用では使わない。画像 URL は DMM ドメイン形式のダミーで、実際にはダウンロードしない。"""
from __future__ import annotations

from .dmm_client import Product

SAMPLE_ITEMS = [
    {"cid": "demo001", "title": "サンプル作品A 〜温泉旅館の一夜〜", "genres": ["人妻", "温泉"], "act": ["架空 花子"], "price": 300, "list": 1980, "rc": 120, "ra": 4.6, "date": "2026-09-20", "movie": True},
    {"cid": "demo002", "title": "サンプル作品B オフィス・ラブストーリー", "genres": ["OL", "ドラマ"], "act": ["架空 桜"], "price": 1480, "list": 1480, "rc": 8, "ra": 4.9, "date": "2026-09-27", "movie": False},
    {"cid": "demo003", "title": "サンプル作品C ベスト盤 8時間", "genres": ["ベスト・総集編"], "act": [], "price": 980, "list": 2980, "rc": 300, "ra": 4.2, "date": "2026-06-01", "movie": True},
    {"cid": "demo004", "title": "サンプル作品D 新人デビュー", "genres": ["デビュー作品", "単体作品"], "act": ["架空 みなみ"], "price": 2480, "list": 2480, "rc": 0, "ra": None, "date": "2026-09-28", "movie": True},
    {"cid": "demo005", "title": "サンプル作品E コスプレ特集", "genres": ["コスプレ"], "act": ["架空 りん", "架空 ゆい"], "price": 500, "list": 1980, "rc": 45, "ra": 4.1, "date": "2026-08-15", "movie": False},
    {"cid": "demo006", "title": "サンプル作品F 田舎の夏休み", "genres": ["ドラマ", "田舎"], "act": ["架空 なつ"], "price": 1980, "list": 1980, "rc": 22, "ra": 4.4, "date": "2026-07-10", "movie": True},
]


def demo_products(site: str = "DMM.com") -> list[Product]:
    out = []
    for i, d in enumerate(SAMPLE_ITEMS):
        out.append(Product(
            content_id=d["cid"], site=site, service="digital", floor="videoa", title=d["title"],
            url=f"https://www.dmm.com/digital/-/detail/=/cid={d['cid']}/",
            affiliate_url=f"https://al.dmm.com/?lurl=https%3A%2F%2Fwww.dmm.com%2Fdigital%2F-%2Fdetail%2F%3D%2Fcid%3D{d['cid']}%2F&af_id=demo-001&ch=api",
            image_url=f"https://pics.dmm.com/digital/video/{d['cid']}/{d['cid']}pl.jpg",
            sample_image_urls=[f"https://pics.dmm.com/digital/video/{d['cid']}/{d['cid']}jp-{k}.jpg" for k in range(1, 4)],
            sample_movie_url=f"https://cc3001.dmm.com/litevideo/freepv/{d['cid']}/{d['cid']}_mhb_w.mp4" if d["movie"] else None,
            price=d["price"], list_price=d["list"], release_date=d["date"], review_count=d["rc"], review_avg=d["ra"],
            actresses=d["act"], genres=d["genres"], maker="架空メーカー", series=None, campaign=[], is_adult=(site == "FANZA"), raw={},
        ))
    return out
