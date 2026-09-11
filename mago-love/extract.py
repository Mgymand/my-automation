"""物件資料（PDF / 貼り付けテキスト / CSV）→ 統一フォーマット ドラフト生成。

方針:
- PDF はテキストレイヤを PyMuPDF で抽出（無料）。スキャンPDFは Google ドライブの
  「Googleドキュメントで開く」(OCR) や無料OCRツールでテキスト化してから貼り付けでもOK。
- 構造化はヒューリスティック（正規表現）を標準経路とし、ANTHROPIC_API_KEY があれば
  Claude で精度を上げる（任意）。
"""
from __future__ import annotations

import json
import os
import re
import unicodedata

PREFS = ["茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県"]


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    return text.replace("−", "-").replace("‐", "-").replace("–", "-").replace("—", "-")


def pdf_text(path: str) -> str:
    import fitz  # PyMuPDF
    doc = fitz.open(path)
    try:
        return "\n".join(normalize(doc[i].get_text()) for i in range(len(doc)))
    finally:
        doc.close()


def pdf_page_png(path: str, page: int = 0, zoom: float = 1.5) -> bytes:
    import fitz
    doc = fitz.open(path)
    try:
        pg = doc[min(page, len(doc) - 1)]
        pix = pg.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        return pix.tobytes("png")
    finally:
        doc.close()


def _num(s: str | None) -> float | None:
    if not s:
        return None
    s = s.replace(",", "")
    m = re.search(r"[\d.]+", s)
    return float(m.group()) if m else None


def _yen(s: str | None) -> int | None:
    """'1,027,640円' / '102.7万円' / '35万' → 円整数。"""
    if not s:
        return None
    s = s.replace(",", "")
    m = re.search(r"([\d.]+)\s*万", s)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r"([\d.]+)\s*円", s)
    if m:
        return int(float(m.group(1)))
    m = re.search(r"\d{4,}", s)
    return int(m.group()) if m else None


def split_address(addr: str) -> dict:
    """住所 → 都道府県 / 市区町村 / 区(政令市) を分解。"""
    out = {"pref": "", "city": "", "ward": "", "address": addr}
    for p in PREFS:
        if addr.startswith(p):
            out["pref"] = p
            rest = addr[len(p):]
            m = re.match(r"(.+?[市郡])(.+?区)?", rest) if "市" in rest[:8] or "郡" in rest[:6] else None
            if m and m.group(1).endswith("市"):
                out["city"] = m.group(1)
                ward = m.group(2) or ""
                out["ward"] = ward if ward and len(ward) <= 5 else ""
            elif m and m.group(1).endswith("郡"):
                m2 = re.match(r".+?郡(.+?[町村])", rest)
                out["city"] = m2.group(1) if m2 else ""
            else:
                m3 = re.match(r"(.+?[区市町村])", rest)
                out["city"] = m3.group(1) if m3 else ""
            break
    return out


def heuristic(text: str) -> dict:
    """テキストから統一フォーマットのドラフトを作る（キーなしで動く標準経路）。"""
    t = normalize(text)
    lines = [l.strip() for l in t.splitlines() if l.strip()]
    d: dict = {"name": "", "address": "", "spec": {}, "finance": {}}

    m = re.search(r"(?:物件名|建物名|名称)\s*[:：]?\s*(.+)", t)
    d["name"] = (m.group(1).strip() if m else (lines[0] if lines else ""))[:60]

    m = re.search(r"(?:所在地|住所)\s*[:：]?\s*((?:%s)[^\n]+)" % "|".join(PREFS), t) or \
        re.search(r"((?:%s)[^\n ]{3,40})" % "|".join(PREFS), t)
    if m:
        addr = m.group(1).strip()
        d.update(split_address(addr))

    spec = d["spec"]
    # ラベルと値が同一行（「ラベル : 値」または「ラベル 値」）のものだけ拾う。
    # 表組みPDFはラベル列と値列が別行になるため、後段のフォールバックで補完する。
    pats = {
        "rent_yen": r"(?:賃料|家賃|月額賃料)\s*[:：]?\s*([\d,.]+\s*(?:万円|円|万))",
        "management_fee_yen": r"(?:管理費|共益費)\s*[:：]?\s*([\d,.]+\s*(?:万円|円|万))",
        "deposit": r"(?:敷金|保証金|預託金)\s*[:：]?\s*(\d[^\n/／]{0,15})",
        "key_money": r"(?:礼金)\s*[:：]?\s*(\d[^\n/／]{0,15}|なし|無し?)",
        "structure": r"(?:構造)\s*[:：]?\s*((?:[SRCW木鉄骨造]+|軽量鉄骨)[^\n]{0,20})",
        "built_ym": r"(?:竣工|築年月|建築年月)\s*[:：]?\s*(\d{4}[年/.-]\s*\d{1,2}[^\n]{0,4})",
        "floors": r"(?:規模|階建|階数)\s*[:：]\s*([^\n]{1,16})|((?:地上|地下)?\s*\d+\s*階建[^\n]{0,12})",
        "zoning": r"(?:用途地域)\s*[:：]?\s*([^\n]{1,20})",
        "building_coverage": r"(?:建ぺい率|建蔽率)\s*[:：]?\s*([\d.]+\s*%?)",
        "floor_area_ratio": r"(?:容積率)\s*[:：]?\s*([\d.]+\s*%?)",
        "fire_zone": r"((?:準?防火地域|法22条区域)[^\n]{0,10})",
        "contract_type": r"((?:定期借家|普通借家)[^\n]{0,12})",
        "availability": r"(?:入居可能|入居日|引渡し?)\s*[:：]\s*([^\n]{1,16})",
        "parking": r"(?:駐車場)\s*[:：]?\s*([^\n]{1,20})",
        "property_number": r"(?:物件番号|物件No\.?|ビル番号)\s*[:：]?\s*([\w-]{3,20})",
        "contact": r"(?:担当者?)\s*[:：]\s*([^\n]{2,20})",
        "elevator": r"(?:EV|エレベーター)\s*[:：]\s*([^\n]{1,10})",
    }
    for key, pat in pats.items():
        m = re.search(pat, t)
        if not m:
            continue
        val = next((g for g in m.groups() if g), "").strip()
        if not val:
            continue
        spec[key] = _yen(val) if key.endswith("_yen") else val
    if spec.get("built_ym"):
        mm = re.match(r"(\d{4})[年/.-]\s*(\d{1,2})", spec["built_ym"])
        if mm:
            spec["built_ym"] = f"{mm.group(1)}-{int(mm.group(2)):02d}"
    m = re.search(r"((?:株式会社|有限会社|合同会社)[^\n\s]{1,30}|[^\n\s]{1,30}(?:株式会社|有限会社))", t)
    if m:
        spec["source_company"] = m.group(1)
    if not spec.get("rent_yen"):
        # 表組みフォールバック: 「坪単価」以外で 5万円以上の「N 円」を賃料とみなす
        for mm in re.finditer(r"([\d,]{5,})\s*円", t):
            pre = t[max(0, mm.start() - 8):mm.start()]
            if "坪単価" in pre or "単価" in pre:
                continue
            v = _yen(mm.group(0))
            if v and v >= 50000:
                spec["rent_yen"] = v
                break
    if not spec.get("deposit"):
        m = re.search(r"(\d{1,2})\s*ヶ月", t)
        if m:
            spec["deposit"] = m.group(0)
    if not spec.get("contract_years"):
        m = re.search(r"(?:契約期間|契約年数)\s*[:：]\s*([^\n]{1,12})|定期借家\s*[(（]\s*([^)）]{1,8})[)）]|(\d{1,2}\s*年)\s*$", t, re.M)
        if m:
            spec["contract_years"] = next((g for g in m.groups() if g), "").strip()
    if spec.get("contract_type") and spec.get("contract_years") and spec["contract_years"] in spec["contract_type"]:
        spec["contract_type"] = spec["contract_type"].split("(")[0].split("（")[0]

    m = re.search(r"([\d,.]+)\s*(?:㎡|m2|m²|平米)", t)
    if m:
        spec["floor_area_sqm"] = _num(m.group(1))
    m = re.search(r"([\d,.]+)\s*坪", t)
    if m:
        spec["floor_area_tsubo"] = _num(m.group(1))
    if spec.get("floor_area_sqm") and not spec.get("floor_area_tsubo"):
        spec["floor_area_tsubo"] = round(spec["floor_area_sqm"] * 0.3025, 2)
    m = re.search(r"(?:敷地面積|土地面積)\s*[:：]?\s*([\d,.]+)\s*(?:㎡|m2|m²)", t)
    if m:
        spec["site_area_sqm"] = _num(m.group(1))

    stations = []
    for line, station, walk in re.findall(
            r"((?:JR|東京メトロ|都営|東急|京王|小田急|西武|東武|京成|京急|相鉄|つくばエクスプレス|東京モノレール|ゆりかもめ|[^\s]{2,8}線))\s*[「『]?([^\s「」『』]{1,10}?)[」』]?駅?\s*(?:徒歩|歩)?\s*(\d{1,2})\s*分", t)[:4]:
        stations.append({"line": line, "station": station, "walk_min": int(walk)})
    if stations:
        spec["stations"] = stations
    if spec.get("rent_yen"):
        d["finance"]["monthly_rent_yen"] = spec["rent_yen"]
    d["source"] = {"type": "text", "text": t[:8000]}
    return d


def llm_structure(text: str, draft: dict) -> dict:
    """ANTHROPIC_API_KEY があれば Claude で精度向上（任意）。失敗時は draft を返す。"""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return draft
    try:
        import anthropic  # type: ignore
    except ImportError:
        return draft
    fields = {
        "name": "建物名", "address": "所在地（都道府県から）",
        "spec": {"property_type": "種別", "structure": "構造", "built_ym": "YYYY-MM", "floors": "階数",
                 "site_area_sqm": "数値", "floor_area_sqm": "数値", "floor_area_tsubo": "数値",
                 "rent_yen": "月額賃料(円,整数)", "management_fee_yen": "整数", "deposit": "文字",
                 "key_money": "文字", "contract_type": "文字", "contract_years": "文字",
                 "availability": "文字", "zoning": "用途地域", "building_coverage": "文字",
                 "floor_area_ratio": "文字", "fire_zone": "文字", "road_access": "接道",
                 "parking": "文字", "elevator": "有/無", "sprinkler": "有/無",
                 "stations": "[{line, station, walk_min}]", "source_company": "文字",
                 "contact": "文字", "property_number": "文字"}}
    prompt = (
        "以下は日本の不動産物件資料のテキストです。次のJSONスキーマに従い、読み取れた項目のみ埋めて"
        "JSONのみを返してください（不明はnull）。\n" + json.dumps(fields, ensure_ascii=False) +
        "\n\n---\n" + text[:12000])
    try:
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=1500,
                                     messages=[{"role": "user", "content": prompt}])
        raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        raw = raw[raw.find("{"): raw.rfind("}") + 1]
        got = json.loads(raw)
        if got.get("name"):
            draft["name"] = got["name"]
        if got.get("address"):
            draft.update(split_address(got["address"]))
        for k, v in (got.get("spec") or {}).items():
            if v not in (None, "", []):
                draft["spec"][k] = v
        if draft["spec"].get("rent_yen"):
            draft["finance"]["monthly_rent_yen"] = draft["spec"]["rent_yen"]
    except Exception as e:  # noqa: BLE001
        print(f"[llm] fallback: {e}")
    return draft


def draft_from_text(text: str) -> dict:
    return llm_structure(text, heuristic(text))
