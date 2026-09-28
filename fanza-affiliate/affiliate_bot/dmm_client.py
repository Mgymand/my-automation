"""DMM アフィリエイト API v3 クライアント（商品情報 API）。

公式: https://affiliate.dmm.com/api/  （ItemList / FloorList / GenreSearch / ActressSearch ...）
- 1 リクエストの取得上限は 100 件（hits）。短時間の連続呼び出しはアクセス制限がかかるため、
  呼び出し間隔を空ける。
- 画像・サンプル動画は API が返す URL（= DMM が提供するアフィリエイト素材）のみを使う。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests

API_BASE = "https://api.dmm.com/affiliate/v3"
USER_AGENT = "my-automation-affiliate-bot/0.1 (+https://github.com/mgymand/my-automation)"

# 成人向けと判断する site/floor
ADULT_SITE = "FANZA"


class DMMError(RuntimeError):
    pass


@dataclass
class Product:
    content_id: str
    site: str
    service: str
    floor: str
    title: str
    url: str
    affiliate_url: str
    image_url: str
    sample_image_urls: list[str]
    sample_movie_url: str | None
    price: float | None
    list_price: float | None
    release_date: str | None
    review_count: int
    review_avg: float | None
    actresses: list[str]
    genres: list[str]
    maker: str | None
    series: str | None
    campaign: list[dict]
    is_adult: bool
    raw: dict

    @property
    def discount_rate(self) -> float:
        if self.price and self.list_price and self.list_price > self.price:
            return round(1 - self.price / self.list_price, 3)
        return 0.0


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").replace("円", "")
    # "300~" のような表記
    s = s.split("~")[0].strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_item(item: dict, site: str) -> Product:
    """API の item JSON を Product に正規化する。"""
    info = item.get("iteminfo") or {}
    prices = item.get("prices") or {}
    img = item.get("imageURL") or {}
    sample_imgs: list[str] = []
    si = item.get("sampleImageURL") or {}
    for key in ("sample_l", "sample_s"):
        block = si.get(key) or {}
        imgs = block.get("image") or []
        if imgs:
            sample_imgs = list(imgs)
            break
    sm = item.get("sampleMovieURL") or {}
    movie = None
    for key in ("size_720_480", "size_644_414", "size_560_360", "size_476_306"):
        if sm.get(key):
            movie = sm[key]
            break
    review = item.get("review") or {}
    return Product(
        content_id=str(item.get("content_id") or item.get("product_id") or ""),
        site=site,
        service=str(item.get("service_code") or ""),
        floor=str(item.get("floor_code") or ""),
        title=str(item.get("title") or ""),
        url=str(item.get("URL") or ""),
        affiliate_url=str(item.get("affiliateURL") or ""),
        image_url=str(img.get("large") or img.get("list") or img.get("small") or ""),
        sample_image_urls=sample_imgs,
        sample_movie_url=movie,
        price=_to_float(prices.get("price")),
        list_price=_to_float(prices.get("list_price")),
        release_date=item.get("date"),
        review_count=int(review.get("count") or 0),
        review_avg=_to_float(review.get("average")),
        actresses=[a.get("name") for a in (info.get("actress") or []) if a.get("name")],
        genres=[g.get("name") for g in (info.get("genre") or []) if g.get("name")],
        maker=((info.get("maker") or [{}])[0]).get("name"),
        series=((info.get("series") or [{}])[0]).get("name"),
        campaign=list(item.get("campaign") or []),
        is_adult=(site.upper() == ADULT_SITE),
        raw=item,
    )


class DMMClient:
    def __init__(self, api_id: str, affiliate_id: str, session: requests.Session | None = None, min_interval: float = 1.0):
        if not api_id or not affiliate_id:
            raise DMMError("DMM_API_ID / DMM_AFFILIATE_ID が未設定です")
        self.api_id = api_id
        self.affiliate_id = affiliate_id
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT
        self.min_interval = min_interval
        self._last = 0.0

    def _get(self, endpoint: str, params: dict) -> dict:
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        p = {"api_id": self.api_id, "affiliate_id": self.affiliate_id, "output": "json"}
        p.update({k: v for k, v in params.items() if v is not None})
        r = self.s.get(f"{API_BASE}/{endpoint}", params=p, timeout=30)
        self._last = time.monotonic()
        if r.status_code != 200:
            raise DMMError(f"DMM API {endpoint} HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        result = data.get("result") or {}
        if str(result.get("status")) not in ("200", "200.0"):
            raise DMMError(f"DMM API {endpoint} status={result.get('status')} message={result.get('message')}")
        return result

    def item_list(
        self,
        site: str = "FANZA",
        service: str | None = "digital",
        floor: str | None = "videoa",
        sort: str = "rank",
        hits: int = 100,
        offset: int = 1,
        keyword: str | None = None,
        gte_date: str | None = None,
        lte_date: str | None = None,
        article: str | None = None,
        article_id: str | None = None,
        cid: str | None = None,
    ) -> list[Product]:
        """商品情報 API。sort: rank | price | -price | date | review | match"""
        result = self._get(
            "ItemList",
            {
                "site": site,
                "service": service,
                "floor": floor,
                "sort": sort,
                "hits": min(int(hits), 100),
                "offset": offset,
                "keyword": keyword,
                "gte_date": gte_date,
                "lte_date": lte_date,
                "article": article,
                "article_id": article_id,
                "cid": cid,
            },
        )
        return [parse_item(it, site) for it in (result.get("items") or [])]

    def floor_list(self) -> dict:
        return self._get("FloorList", {})

    def genre_search(self, floor_id: int, hits: int = 100, offset: int = 1, initial: str | None = None) -> dict:
        return self._get("GenreSearch", {"floor_id": floor_id, "hits": hits, "offset": offset, "initial": initial})

    def actress_search(self, keyword: str | None = None, hits: int = 100, offset: int = 1, sort: str | None = None) -> dict:
        return self._get("ActressSearch", {"keyword": keyword, "hits": hits, "offset": offset, "sort": sort})
