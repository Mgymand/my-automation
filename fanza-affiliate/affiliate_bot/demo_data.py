"""認証情報がない環境でパイプラインを通すための合成 FANZA 相当商品（ドライラン専用）。実運用では使わない。"""
from __future__ import annotations

from .dmm_client import Product

SAMPLE_ITEMS = [
    {"cid": "demo001", "title": "サンプル作品A 温泉旅館の一夜", "genres": ["人妻", "温泉", "ドラマ"], "act": ["架空 花子"], "price": 300, "list": 1980, "rc": 120, "ra": 4.6, "date": "2026-09-20", "movie": True},
    {"cid": "demo002", "title": "サンプル作品B オフィスの午後", "genres": ["OL", "ドラマ"], "act": ["架空 桜"], "price": 1480, "list": 1480, "rc": 8, "ra": 4.9, "date": "2026-09-27", "movie": False},
    {"cid": "demo003", "title": "サンプル作品C ベスト 8時間", "genres": ["ベスト・総集編"], "act": ["架空 みなみ", "架空 ゆい"], "price": 980, "list": 2980, "rc": 300, "ra": 4.2, "date": "2026-06-01", "movie": True},
    {"cid": "demo004", "title": "サンプル作品D デビュー", "genres": ["デビュー作品", "単体作品"], "act": ["架空 みなみ"], "price": 2480, "list": 2480, "rc": 0, "ra": None, "date": "2026-09-28", "movie": True},
    {"cid": "demo005", "title": "サンプル作品E コスプレ特集", "genres": ["コスプレ"], "act": ["架空 りん", "架空 ゆい"], "price": 500, "list": 1980, "rc": 45, "ra": 4.1, "date": "2026-08-15", "movie": False},
    {"cid": "demo006", "title": "サンプル作品F 田舎の夏休み", "genres": ["ドラマ", "田舎"], "act": ["架空 なつ"], "price": 1980, "list": 1980, "rc": 22, "ra": 4.4, "date": "2026-07-10", "movie": True},
    {"cid": "demo007", "title": "サンプル作品G シリーズ第3弾", "genres": ["企画", "シリーズ"], "act": ["架空 かな"], "price": 1280, "list": 1980, "rc": 60, "ra": 4.3, "date": "2026-09-15", "movie": True},
]


def demo_products(site: str = "FANZA") -> list[Product]:
    out = []
    for d in SAMPLE_ITEMS:
        dom = "dmm.co.jp" if site == "FANZA" else "dmm.com"
        out.append(Product(
            content_id=d["cid"], site=site, service="digital", floor="videoa", title=d["title"],
            url=f"https://www.{dom}/digital/videoa/-/detail/=/cid={d['cid']}/",
            affiliate_url=f"https://al.fanza.co.jp/?lurl=https%3A%2F%2Fwww.{dom}%2Fdigital%2Fvideoa%2F-%2Fdetail%2F%3D%2Fcid%3D{d['cid']}%2F&af_id=demo-990&ch=api&ch_id=link",
            image_url=f"https://pics.{dom}/digital/video/{d['cid']}/{d['cid']}pl.jpg",
            sample_image_urls=[f"https://pics.{dom}/digital/video/{d['cid']}/{d['cid']}jp-{k}.jpg" for k in range(1, 4)],
            sample_movie_url=f"https://cc3001.{dom}/litevideo/freepv/{d['cid']}/{d['cid']}_mhb_w.mp4" if d["movie"] else None,
            price=d["price"], list_price=d["list"], release_date=d["date"], review_count=d["rc"], review_avg=d["ra"],
            actresses=d["act"], genres=d["genres"], maker="架空メーカー", series="架空シリーズ" if "シリーズ" in d["title"] else None,
            campaign=[], is_adult=(site == "FANZA"), raw={},
        ))
    return out


DEMO_RESEARCH_CSV = """x_post_id,followers,text,media_type,created_at,views,likes,reposts,replies,bookmarks,video_seconds
1001,900,"これ本当に温泉旅館の話？\\n後半の展開が想像以上だった\\n↓",video,2026-09-26T12:00:00+00:00,450000,3200,400,60,900,45
1002,15000,"新作 配信開始。人妻ドラマの王道。\\n#FANZA",photo,2026-09-26T13:00:00+00:00,30000,150,20,3,40,0
1003,2500,"今週のセール 50%OFF まとめ 3本\\n1位 …\\n2位 …\\n3位 …",photo,2026-09-27T10:00:00+00:00,80000,600,90,12,300,0
1004,400,"レビュー平均4.8（120件）。OL ものではこれが一番だった",photo,2026-09-27T11:00:00+00:00,26000,210,30,5,80,0
1005,120000,"本日配信。",photo,2026-09-27T12:00:00+00:00,50000,300,20,4,50,0
1006,700,"どっち派？\\n温泉 or オフィス\\n答えは後半で",video,2026-09-27T14:00:00+00:00,120000,900,110,40,260,30
"""
