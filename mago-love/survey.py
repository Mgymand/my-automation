"""現地リスク自動調査（すべて無料の公開API）。

「調査データ一覧」の手順をワンクリック化する:
  1. 標高           国土地理院 標高API（5mメッシュ）
  2. 表層地盤       防災科研 J-SHIS（微地形区分・AVS30・増幅率）
  3. ハザードマップ 重ねるハザードマップのタイルを座標で判定
                    （洪水想定最大/計画規模・浸水継続時間・家屋倒壊・土砂災害・津波・高潮）
座標さえあれば取得できる。用途地域・地価公示・埋蔵文化財は窓口/手動入力（リンクを提示）。
"""
from __future__ import annotations

import json
import math
import ssl
import urllib.error
import urllib.parse
import urllib.request

_CTX = ssl.create_default_context()
_UA = {"User-Agent": "MagoLove/1.0 (survey)"}


def _get(url: str, timeout: int = 12) -> bytes | None:
    """200 → bytes / 404 → b"" (データなし) / その他失敗 → None。"""
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return b""
        print(f"[survey] {url}: {e}")
        return None
    except Exception as e:  # noqa: BLE001
        print(f"[survey] {url}: {e}")
        return None


def elevation(lat: float, lon: float) -> dict:
    raw = _get("https://cyberjapandata2.gsi.go.jp/general/dem/scripts/getelevation.php?"
               + urllib.parse.urlencode({"lon": lon, "lat": lat, "outtype": "JSON"}))
    if not raw:
        return {"ok": False}
    try:
        d = json.loads(raw)
        return {"ok": True, "elevation_m": d.get("elevation"), "source": d.get("hsrc", "")}
    except ValueError:
        return {"ok": False}


def ground(lat: float, lon: float) -> dict:
    raw = _get("https://www.j-shis.bosai.go.jp/map/api/sstrct/V2/meshinfo.geojson?"
               + f"position={lon},{lat}&epsg=4301")
    if not raw:
        return {"ok": False}
    try:
        f = json.loads(raw)["features"][0]["properties"]
        arv = float(f.get("ARV") or 0)
        grade = ("揺れやすい（第3種地盤相当）" if arv >= 2.0 else
                 "平均的（第2種地盤相当）" if arv >= 1.4 else "揺れにくい（第1種地盤相当）")
        return {"ok": True, "landform": f.get("JNAME", ""), "avs30": f.get("AVS"), "arv": f.get("ARV"),
                "meshcode": f.get("meshcode"), "grade": grade}
    except (ValueError, KeyError, IndexError):
        return {"ok": False}


# --- ハザードタイル判定 -------------------------------------------------------
_HAZARD_LAYERS = [
    # key, label, tile path, legend {rgb: 判定} (None = 色にかかわらず「該当あり」)
    ("flood_max", "洪水浸水想定区域（想定最大規模）", "01_flood_l2_shinsuishin_data", {
        (247, 245, 169): "0.5m未満", (255, 216, 192): "0.5〜3.0m", (255, 183, 183): "3.0〜5.0m",
        (255, 145, 145): "5.0〜10.0m", (242, 133, 201): "10.0〜20.0m", (220, 122, 220): "20.0m以上"}),
    ("flood_plan", "洪水浸水想定区域（計画規模）", "01_flood_l1_shinsuishin_newlegend_data", {
        (247, 245, 169): "0.5m未満", (255, 216, 192): "0.5〜3.0m", (255, 183, 183): "3.0〜5.0m",
        (255, 145, 145): "5.0〜10.0m", (242, 133, 201): "10.0〜20.0m", (220, 122, 220): "20.0m以上"}),
    ("flood_duration", "浸水継続時間（想定最大規模）", "01_flood_l2_keizoku_data", {
        (160, 210, 255): "12時間未満", (0, 65, 255): "12〜24時間", (250, 245, 0): "24〜72時間",
        (255, 153, 0): "72〜168時間", (255, 40, 0): "168〜336時間", (180, 0, 104): "336時間以上"}),
    ("house_collapse", "家屋倒壊等氾濫想定区域（氾濫流）", "01_flood_l2_kaokutoukai_hanran_data", None),
    ("landslide_debris", "土砂災害警戒区域（土石流）", "05_dosekiryukeikaikuiki", None),
    ("landslide_slope", "土砂災害警戒区域（急傾斜地）", "05_kyuukeishakeikaikuiki", None),
    ("landslide_slide", "土砂災害警戒区域（地すべり）", "05_jisuberikeikaikuiki", None),
    ("tsunami", "津波浸水想定", "04_tsunami_newlegend_data", {
        (247, 245, 169): "0.3m未満", (255, 216, 192): "0.3〜1.0m", (255, 183, 183): "1.0〜3.0m",
        (255, 145, 145): "3.0〜5.0m", (242, 133, 201): "5.0〜10.0m", (220, 122, 220): "10.0〜20.0m"}),
    ("high_tide", "高潮浸水想定", "03_hightide_l2_shinsuishin_data", {
        (247, 245, 169): "0.5m未満", (255, 216, 192): "0.5〜3.0m", (255, 183, 183): "3.0〜5.0m",
        (255, 145, 145): "5.0〜10.0m", (242, 133, 201): "10.0〜20.0m", (220, 122, 220): "20.0m以上"}),
]
_Z = 16


def _tile(lat: float, lon: float):
    n = 2 ** _Z
    x = (lon + 180) / 360 * n
    y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
    return int(x), int(y), int((x % 1) * 256), int((y % 1) * 256)


def _nearest(rgb, legend: dict) -> str:
    best, bd = None, 1e9
    for c, lab in legend.items():
        d = sum((a - b) ** 2 for a, b in zip(rgb, c))
        if d < bd:
            best, bd = lab, d
    return best if bd < 60 ** 2 else "該当あり（区分不明）"


def hazards(lat: float, lon: float) -> list[dict]:
    import fitz  # PyMuPDF（PNGのピクセル読み取りに使う）
    tx, ty, px, py = _tile(lat, lon)
    out = []
    for key, label, path, legend in _HAZARD_LAYERS:
        url = f"https://disaportaldata.gsi.go.jp/raster/{path}/{_Z}/{tx}/{ty}.png"
        raw = _get(url, timeout=10)
        item = {"key": key, "label": label, "hit": False, "detail": "該当なし", "tile_url": url}
        if raw is None:
            item["detail"] = "取得できませんでした（再調査してください）"
            item["error"] = True
        elif raw:
            try:
                pix = fitz.Pixmap(raw)
                p = pix.pixel(px, py)
                alpha = p[3] if pix.alpha and len(p) > 3 else 255
                if alpha > 30 and not (p[0] > 245 and p[1] > 245 and p[2] > 245):
                    item["hit"] = True
                    item["detail"] = _nearest(p[:3], legend) if legend else "該当あり"
                    item["rgb"] = list(p[:3])
            except Exception as e:  # noqa: BLE001
                item["detail"] = f"判定不可: {e}"
        out.append(item)
    return out


def run(lat: float, lon: float) -> dict:
    hz = hazards(lat, lon)
    flood = next((h for h in hz if h["key"] == "flood_max"), {})
    notes = []
    if flood.get("hit"):
        notes.append("浸水想定区域内の要配慮者利用施設（有料老人ホーム）は、水防法により避難確保計画の作成と避難訓練が義務。開設準備タスクとして見込むこと。")
    if any(h["hit"] for h in hz if h["key"].startswith("landslide")):
        notes.append("土砂災害警戒区域に該当。同様に避難確保計画が必要。急傾斜地は建築制限（特別警戒区域）も確認。")
    if next((h for h in hz if h["key"] == "house_collapse"), {}).get("hit"):
        notes.append("家屋倒壊等氾濫想定区域に該当。建物流失リスクがあるため立地は慎重に判断。")
    return {
        "lat": lat, "lon": lon,
        "elevation": elevation(lat, lon),
        "ground": ground(lat, lon),
        "hazards": hz,
        "notes": notes,
        "links": {
            "重ねるハザードマップ": f"https://disaportal.gsi.go.jp/maps/?ll={lat},{lon}&z=16&base=pale&vs=c1j0l0u0t0h0z0",
            "地理院地図": f"https://maps.gsi.go.jp/#16/{lat}/{lon}/",
            "不動産情報ライブラリ（地価・用途地域）": "https://www.reinfolib.mlit.go.jp/",
            "J-SHIS 地震ハザード": "https://www.j-shis.bosai.go.jp/map/",
        },
    }
