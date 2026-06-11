"""物件PDF → 構造化データ 抽出パイプライン (Phase1)

役割:
1. テキスト抽出  (PyMuPDF: テキストレイヤ付きPDF)
2. 画像抽出      (建物写真・室内写真・間取り図 → ファイル保存)
3. 構造化        (Claude APIで正規化レコードを生成。キー未設定時はヒューリスティック)

設計方針:
- LLM構造化を主経路とする。万円⇄円・全角半角・複数沿線駅の分解など
  「正規化」をLLMに任せると正規表現より遥かに堅牢。
- ANTHROPIC_API_KEY 未設定 or anthropic未インストール時は _structure_heuristic に
  自動フォールバックし、キーなしでも動く。
- スキャンPDF(テキストレイヤなし)は将来 vision にフォールバック予定（TODO）。

出力スキーマ (PROPERTY_SCHEMA): Facilo準拠。後段のSalesforceマッチングに渡す前提。
"""
from __future__ import annotations

import json
import os
import re
import unicodedata

import fitz  # PyMuPDF

# 構造化レコードの正規スキーマ。LLM/ヒューリスティック双方がこの形を返す。
PROPERTY_SCHEMA = {
    "building_name": "建物名（部屋番号は除く）",
    "room": "部屋番号・区画",
    "property_type": "物件種目（貸店舗/貸事務所/貸マンション/売事務所 等）",
    "transaction_type": "賃貸 or 売買",
    "address": "所在地（都道府県から）",
    "rent_yen": "賃料（円/月, 整数。売買は売価, 万円は円換算）",
    "management_fee_yen": "管理費・共益費（円/月, 整数）",
    "deposit": "敷金・保証金（原文表記）",
    "key_money": "礼金（原文表記）",
    "area_sqm": "面積（㎡, 数値）",
    "area_tsubo": "面積（坪, 数値。なければnull）",
    "layout": "間取り（1LDK 等）",
    "structure": "構造（RC造 等）",
    "floor": "階建/所在階（3階建/1階部分 等）",
    "built_ym": "築年月（YYYY-MM）",
    "stations": "沿線駅リスト [{line, station, walk_min}]（備考内の利用駅も含む）",
    "parking": "駐車場",
    "availability": "引渡/入居可能時期（即時 等）",
    "current_status": "現況（空 等）",
    "deal_type": "取引態様（専任媒介/媒介/専属専任 等）",
    "ad_rate": "広告料(AD)（賃料の100% 等）",
    "source_company": "元付/情報提供会社名",
    "property_number": "物件番号",
    "source_url": "物件URL（athome等。なければnull）",
    "allowed_business": "出店可能業種リスト（事業用のみ。なければ[]）",
    "restricted_business": "不可・禁止業種リスト（飲食不可/風俗不可 等。なければ[]）",
    "facilities": "設備リスト",
    "remarks": "備考（重要事項を要約）",
}

_EMPTY = {k: ([] if k in ("stations", "allowed_business", "restricted_business", "facilities") else None)
          for k in PROPERTY_SCHEMA}

LLM_MODEL = "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# テキスト / 画像 抽出
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Kangxi部首・全角・特殊ダッシュを標準化。"""
    text = unicodedata.normalize("NFKC", text)
    for d in ("−", "‐", "–", "—", "ー"):
        text = text.replace(d, "-") if d != "ー" else text
    return text


def extract_pages(pdf_path: str) -> list[str]:
    """ページごとのテキストをリストで返す（正規化済み）。"""
    doc = fitz.open(pdf_path)
    try:
        return [_normalize(doc[i].get_text()) for i in range(len(doc))]
    finally:
        doc.close()


def extract_text(pdf_path: str) -> str:
    """全ページのテキストを連結して返す。"""
    return "\n".join(extract_pages(pdf_path))


def has_text_layer(pdf_path: str, min_chars: int = 40) -> bool:
    """テキストレイヤの有無を判定（スキャンPDF検出用）。"""
    return len(extract_text(pdf_path).strip()) >= min_chars


def extract_images(pdf_path: str, out_dir: str, min_pixels: int = 200 * 200) -> list[str]:
    """埋め込み画像（建物写真・間取り図）を保存し、保存パスのリストを返す。

    ロゴ・QRコード等の小画像は min_pixels 未満として除外。
    """
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(pdf_path))[0]
    base = re.sub(r"[^\w\-]+", "_", base)
    doc = fitz.open(pdf_path)
    saved: list[str] = []
    seen: set[int] = set()
    try:
        for page in doc:
            for img in page.get_images(full=True):
                xref = img[0]
                if xref in seen:
                    continue
                seen.add(xref)
                base_img = doc.extract_image(xref)
                w, h = base_img.get("width", 0), base_img.get("height", 0)
                if w * h < min_pixels:
                    continue
                ext = base_img.get("ext", "png")
                fname = f"{base}__{xref}.{ext}"
                fpath = os.path.join(out_dir, fname)
                with open(fpath, "wb") as f:
                    f.write(base_img["image"])
                saved.append(fpath)
    finally:
        doc.close()
    return saved


# ---------------------------------------------------------------------------
# 構造化（LLM主経路 + ヒューリスティックfallback）
# ---------------------------------------------------------------------------

def structure_properties(pages: list[str]) -> list[dict]:
    """ページ群を1件以上の正規化レコードに構造化。

    1PDFに複数物件が含まれる場合（図面バンドル等）は複数レコードを返す。
    LLM優先、不可ならページ単位ヒューリスティックにフォールバック。
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return _structure_llm("\n\n===PAGE===\n\n".join(pages))
        except Exception as e:  # APIエラー時も止めず fallback
            print(f"[extractor] LLM failed, falling back to heuristic: {e}")
    records: list[dict] = []
    for page in pages:
        rec = _structure_heuristic(page)
        if rec.get("address") or rec.get("rent_yen"):  # 意味のあるページのみ
            records.append(rec)
    return records or [_EMPTY.copy()]


_SYSTEM_PROMPT = (
    "あなたは日本の不動産マイソク（販売図面・物件概要書）から物件情報を抽出し、"
    "正規化するエンジンです。与えられたPDFテキストから、指定スキーマのJSONを1つだけ出力します。\n"
    "規則:\n"
    "- 賃料・管理費は必ず円/月の整数に正規化（例: 22.429万円→224290, 3.9万円→39000, 130,000円→130000）。"
    "売買物件なら売価を rent_yen に入れる。\n"
    "- 全角英数字は半角化、建物名と部屋番号は分離。\n"
    "- 沿線駅は本文と備考(利用駅1/2等)を統合し stations 配列に。徒歩分は整数。\n"
    "- 取引態様・広告料(AD)・元付会社・物件番号・物件URL も拾う。\n"
    "- 事業用なら出店可能業種を allowed_business に。\n"
    "- 「飲食不可」「風俗不可」「事務所のみ」等の業種制限は restricted_business に列挙"
    "（例: 飲食不可→[\"飲食\"]）。本文・備考・チェックポイントから漏れなく拾う。\n"
    "- 不明な項目は null（配列項目は []）。憶測で埋めない。\n"
    "- 1つのPDFに複数物件が含まれる場合は、物件ごとに要素を分ける。\n"
    "- 出力は物件オブジェクトの配列(JSON array)のみ。1物件でも要素1の配列にする。"
    "JSON以外は一切出力しない。"
)


def _structure_llm(text: str) -> list[dict]:
    import anthropic

    client = anthropic.Anthropic()
    schema_doc = json.dumps(PROPERTY_SCHEMA, ensure_ascii=False, indent=2)
    resp = client.messages.create(
        model=LLM_MODEL,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT + "\n\n各物件のスキーマ:\n" + schema_doc,
                # 静的な命令＋スキーマはキャッシュして繰り返し処理のコストを削減
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{
            "role": "user",
            "content": f"次のPDFテキストから物件情報JSON配列を生成してください:\n\n{text}",
        }],
    )
    raw = "".join(b.text for b in resp.content if b.type == "text").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    data = json.loads(raw)
    if isinstance(data, dict):
        data = [data]
    records = []
    for item in data:
        merged = dict(_EMPTY)
        merged.update({k: item[k] for k in item if k in PROPERTY_SCHEMA})
        records.append(merged)
    return records


# ---- ヒューリスティック（キーなしでも動く簡易版） ----

def _rent_to_yen(s: str) -> int | None:
    s = s.replace(",", "").replace(" ", "")
    m = re.search(r"([\d.]+)万円", s)
    if m:
        return int(round(float(m.group(1)) * 10000))
    m = re.search(r"([\d.]+)円", s)
    if m:
        return int(round(float(m.group(1))))
    return None


def _parse_stations(text: str) -> list[dict]:
    stations: list[dict] = []
    seen: set[tuple] = set()
    # "<路線> / <駅> 徒歩N分" / "<路線> <駅> 徒歩N分" / "利用駅1：<路線> <駅> 徒歩N分"
    pat = re.compile(
        r"(?:利用駅\s*[\d１２３]*\s*[:：]?\s*)?"
        r"([^\s/,，、:：\n]{2,20}?(?:線|鉄道))\s*/?\s*"
        r"([^\s/,，、:：\n]{1,12}?駅?)\s*徒歩\s*(\d+)\s*分"
    )
    for m in pat.finditer(text):
        line, station, walk = m.group(1), m.group(2).rstrip("駅"), int(m.group(3))
        key = (line, station, walk)
        if key in seen:
            continue
        seen.add(key)
        stations.append({"line": line, "station": station, "walk_min": walk})
    return stations


def _structure_heuristic(text: str) -> dict:
    info = dict(_EMPTY)

    m = re.search(r"建\s*物\s*名\s*([^\n]+)", text)
    if m:
        name = re.sub(r"\s+", " ", m.group(1)).strip()
        rm = re.search(r"\s+(\d+[A-Za-z]?)\s*$", name)
        if rm:
            info["room"] = rm.group(1)
            name = name[: rm.start()].strip()
        info["building_name"] = name

    m = re.search(r"物\s*件\s*種\s*[目別]\s*([^\n]+)", text)
    if m:
        info["property_type"] = re.sub(r"\s+", " ", m.group(1)).strip()[:20]
    info["transaction_type"] = "売買" if ("売" in (info["property_type"] or "")) else "賃貸"

    m = re.search(r"所\s*在\s*地[^\n]*\n?\s*((?:東京都|北海道|(?:京都|大阪)府|[^\s\n]{2,4}県)[^\n]+)", text)
    if not m:
        m = re.search(r"((?:東京都|北海道|(?:京都|大阪)府|[^\s\n]{2,4}県)[^\n]+?[町丁目\d\-]+)", text)
    if m:
        info["address"] = re.sub(r"\s+", "", m.group(1)).strip()

    m = re.search(r"賃\s*料[^\n]*?([\d.,]+\s*万?円)", text)
    if m:
        info["rent_yen"] = _rent_to_yen(m.group(1))
    m = re.search(r"管\s*理\s*費[等]?[^\n]*?([\d.,]+\s*万?円)", text)
    if m:
        info["management_fee_yen"] = _rent_to_yen(m.group(1))

    m = re.search(r"敷\s*金\s*/?\s*保\s*証\s*金\s*([^\n]+)", text) or \
        re.search(r"敷\s*金\s+(\S+)", text)
    if m:
        info["deposit"] = re.sub(r"\s+", " ", m.group(1)).strip()[:30]
    m = re.search(r"礼\s*金\s+(\S+)", text)
    if m:
        info["key_money"] = m.group(1).strip()

    m = re.search(r"([\d.,]+)\s*(?:㎡|m²|m2|平米)", text)
    if m:
        info["area_sqm"] = float(m.group(1).replace(",", ""))
    m = re.search(r"([\d.,]+)\s*坪", text)
    if m:
        info["area_tsubo"] = float(m.group(1).replace(",", ""))

    m = re.search(r"間\s*取(?:タイプ)?[\s　]*([1-9０-９][SLDKR]+|ワンルーム|[1-9]K)", text)
    if m:
        info["layout"] = m.group(1)
    m = re.search(r"構\s*造[・\s]*規?模?\s*([^\n]+)", text)
    if m:
        info["structure"] = re.sub(r"\s+", " ", m.group(1)).strip()[:30]
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月", text)
    if m:
        info["built_ym"] = f"{m.group(1)}-{int(m.group(2)):02d}"

    info["stations"] = _parse_stations(text)

    m = re.search(r"駐\s*車\s*場\s*([^\n]+)", text)
    if m:
        info["parking"] = re.sub(r"\s+", " ", m.group(1)).strip()[:40]
    m = re.search(r"(?:引渡|入居)\s*可\s*能\s*時?\s*期\s*([即時相談応\d年月日近]+)", text)
    if m:
        info["availability"] = m.group(1).strip()
    m = re.search(r"現\s*況\s*([空家賃貸中居抜済\S]{1,8})", text)
    if m:
        info["current_status"] = m.group(1).strip()
    m = re.search(r"取\s*引\s*態\s*様\s*[:：]?\s*(\S+)", text)
    if m:
        info["deal_type"] = m.group(1).strip()
    m = re.search(r"(?:広告|AD)[^\n]*?賃料の\s*([\d]+%[^\n]*)", text)
    if m:
        info["ad_rate"] = "賃料の" + m.group(1).strip()[:20]
    m = re.search(r"物\s*件\s*番\s*号\s*(\d+)", text)
    if m:
        info["property_number"] = m.group(1)
    m = re.search(r"(https?://[^\s\n]+)", text)
    if m:
        info["source_url"] = m.group(1)

    return info


# ---------------------------------------------------------------------------
# CLI: python extractor.py <pdf> [<pdf> ...]
# ---------------------------------------------------------------------------

def process(pdf_path: str, image_dir: str | None = None) -> list[dict]:
    """1ファイルを処理して構造化レコードのリストを返す（複数物件対応）。

    画像保存は image_dir 指定時のみ。抽出画像は全レコード共通の参考情報として付与。
    """
    pages = extract_pages(pdf_path)
    records = structure_properties(pages)
    images = extract_images(pdf_path, image_dir) if image_dir else []
    has_text = bool("".join(pages).strip())
    for rec in records:
        rec["_source_file"] = os.path.basename(pdf_path)
        rec["_text_layer"] = has_text
        if image_dir:
            rec["_images"] = images
    return records


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: python extractor.py <pdf> [<pdf> ...]")
        raise SystemExit(1)
    mode = "LLM" if os.environ.get("ANTHROPIC_API_KEY") else "heuristic"
    print(f"# extraction mode: {mode}\n")
    for path in sys.argv[1:]:
        for rec in process(path):
            print(json.dumps(rec, ensure_ascii=False, indent=2))
            print()
