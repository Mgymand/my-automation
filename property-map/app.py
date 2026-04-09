import os
import json
import re
import ssl
import urllib.request
import urllib.parse
import time
from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect
from functools import wraps
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "estateforce-secret-key-2026")

# --- Supabase client ---
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://wfkglabydjucrzahvrrc.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Indma2dsYWJ5ZGp1Y3J6YWh2cnJjIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTczOTQwMSwiZXhwIjoyMDkxMzE1NDAxfQ.Dm7AHknnZmS5WJULgJtyWpC6YYScGCxT8rxlnvNDc6Y")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Authentication ---
USERS = {
    "k.iwamoto@lime-fit.com": "Lime0201",
}


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Render: use /data disk if writable, else /tmp/property-data (Render free), else local ./data
if os.path.isdir("/data") and os.access("/data", os.W_OK):
    DATA_DIR = "/data"
elif os.environ.get("RENDER"):
    DATA_DIR = os.path.join("/tmp", "property-data")
else:
    DATA_DIR = os.path.join(BASE_DIR, "data")
PDF_DIR = os.path.join(DATA_DIR, "pdfs")

os.makedirs(PDF_DIR, exist_ok=True)

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


# --- Workspace helpers (Supabase) ---

DEFAULT_STATIONS = [
    {"name": "\u6e0b\u8c37\u99c5", "lat": 35.6580, "lon": 139.7016, "r": 180},
    {"name": "\u8868\u53c2\u9053\u99c5", "lat": 35.6654, "lon": 139.7122, "r": 120},
    {"name": "\u660e\u6cbb\u795e\u5bae\u524d\u99c5", "lat": 35.6699, "lon": 139.7024, "r": 100},
]


def _get_app_setting(key, default=None):
    """Get a value from the app_settings table."""
    try:
        resp = supabase.table("app_settings").select("value").eq("key", key).execute()
        if resp.data:
            return resp.data[0]["value"]
    except Exception as e:
        print(f"app_settings read error: {e}")
    return default


def _set_app_setting(key, value):
    """Upsert a value in the app_settings table."""
    try:
        supabase.table("app_settings").upsert({"key": key, "value": value}).execute()
    except Exception as e:
        print(f"app_settings write error: {e}")


def load_workspaces():
    """Load workspace list + activeWorkspace from Supabase."""
    resp = supabase.table("workspaces").select("*").execute()
    rows = resp.data or []
    workspaces = []
    for r in rows:
        workspaces.append({
            "id": r["id"],
            "name": r["name"],
            "stations": r.get("stations") or DEFAULT_STATIONS,
            "center": r.get("center") or {"lat": 35.6595, "lon": 139.7005},
            "zoom": r.get("zoom") or 16,
            "criteria": r.get("criteria"),
        })
    active_ws = _get_app_setting("activeWorkspace", "ws_1")
    if not workspaces:
        _migrate_to_workspaces()
        return load_workspaces()
    return {"activeWorkspace": active_ws, "workspaces": workspaces}


def save_workspaces(data):
    """Save workspace list + activeWorkspace to Supabase."""
    _set_app_setting("activeWorkspace", data.get("activeWorkspace", "ws_1"))
    for ws in data.get("workspaces", []):
        supabase.table("workspaces").upsert({
            "id": ws["id"],
            "name": ws.get("name", ""),
            "stations": ws.get("stations"),
            "center": ws.get("center"),
            "zoom": ws.get("zoom", 16),
            "criteria": ws.get("criteria"),
        }).execute()
    bump_change()


def _migrate_to_workspaces():
    """Create default workspace in Supabase if none exist."""
    ws_id = "ws_1"
    supabase.table("workspaces").upsert({
        "id": ws_id,
        "name": "\u65b0\u30aa\u30d5\u30a3\u30b9\u7528",
        "stations": DEFAULT_STATIONS,
        "center": {"lat": 35.6595, "lon": 139.7005},
        "zoom": 16,
    }).execute()
    _set_app_setting("activeWorkspace", ws_id)


def get_active_ws_id():
    ws_id = request.args.get("ws")
    if ws_id:
        return ws_id
    return _get_app_setting("activeWorkspace", "ws_1")


# --- Property helpers (Supabase, workspace-aware) ---

def load_properties(ws_id=None):
    if ws_id is None:
        ws_id = get_active_ws_id()
    resp = supabase.table("properties").select("*").eq("workspace_id", ws_id).execute()
    rows = resp.data or []
    props = []
    for r in rows:
        props.append({
            "id": r["id"],
            "name": r.get("name", ""),
            "address": r.get("address", ""),
            "lat": r.get("lat"),
            "lon": r.get("lon"),
            "filename": r.get("filename", ""),
            "pdf_url": r.get("pdf_url", ""),
            "details": r.get("details") or {},
            "memo": r.get("memo", ""),
            "color": r.get("color", "blue"),
        })
    return props


def save_properties(props, ws_id=None):
    """Overwrite all properties for a workspace (delete + re-insert)."""
    if ws_id is None:
        ws_id = get_active_ws_id()
    # Delete existing properties for this workspace
    supabase.table("properties").delete().eq("workspace_id", ws_id).execute()
    # Insert all
    for p in props:
        supabase.table("properties").insert({
            "id": p["id"],
            "workspace_id": ws_id,
            "name": p.get("name", ""),
            "address": p.get("address", ""),
            "lat": p.get("lat"),
            "lon": p.get("lon"),
            "filename": p.get("filename", ""),
            "pdf_url": p.get("pdf_url", ""),
            "details": p.get("details") or {},
            "memo": p.get("memo", ""),
            "color": p.get("color", "blue"),
        }).execute()
    bump_change()


def _upsert_property(prop, ws_id):
    """Upsert a single property (more efficient for single-record ops)."""
    supabase.table("properties").upsert({
        "id": prop["id"],
        "workspace_id": ws_id,
        "name": prop.get("name", ""),
        "address": prop.get("address", ""),
        "lat": prop.get("lat"),
        "lon": prop.get("lon"),
        "filename": prop.get("filename", ""),
        "pdf_url": prop.get("pdf_url", ""),
        "details": prop.get("details") or {},
        "memo": prop.get("memo", ""),
        "color": prop.get("color", "blue"),
    }).execute()
    bump_change()


# --- Address / PDF helpers ---

def normalize_address(address):
    import unicodedata
    address = unicodedata.normalize("NFKC", address)
    CJK_RADICAL_MAP = {
        "\u2EC4": "\u897f",
        "\u2F3B": "\u65e5",
        "\u2F64": "\u7530",
        "\u2F8F": "\u8349",
        "\u2ECD": "\u91cc",
        "\u2F97": "\u8c37",
        "\u2F72": "\u77f3",
        "\u2ECB": "\u8fba",
        "\u2ECC": "\u8fbb",
    }
    for radical, kanji in CJK_RADICAL_MAP.items():
        address = address.replace(radical, kanji)
    address = re.sub(r"\s+", "", address)
    chome_map = {"1": "\u4e00", "2": "\u4e8c", "3": "\u4e09", "4": "\u56db", "5": "\u4e94",
                 "6": "\u516d", "7": "\u4e03", "8": "\u516b", "9": "\u4e5d", "10": "\u5341"}
    def replace_chome(m):
        chome = chome_map.get(m.group(1), m.group(1))
        return f"{chome}\u4e01\u76ee{m.group(2)}-{m.group(3)}"
    address = re.sub(r"(\d+)-(\d+)-(\d+)", replace_chome, address)
    address = re.sub(r"(\d+)\u4e01\u76ee\s*(\d+)\u756a\s*(\d+)\u53f7?", lambda m: f"{chome_map.get(m.group(1), m.group(1))}\u4e01\u76ee{m.group(2)}-{m.group(3)}", address)
    address = re.sub(r"(\d+)\u756a\s*(\d+)\u53f7?", r"\1-\2", address)
    return address


def _gsi_geocode(query_str):
    """Call GSI geocoding API with a query string."""
    query = urllib.parse.urlencode({"q": query_str})
    url = f"https://msearch.gsi.go.jp/address-search/AddressSearch?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "PropertyMapApp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data:
                coords = data[0]["geometry"]["coordinates"]
                return float(coords[1]), float(coords[0])
    except Exception:
        pass
    return None, None


def geocode_address(address):
    normalized = normalize_address(address)
    lat, lon = _gsi_geocode(normalized)
    if lat is not None:
        return lat, lon
    short = re.sub(r"(\u4e01\u76ee).*", r"\1", normalized)
    if short != normalized:
        lat, lon = _gsi_geocode(short)
        if lat is not None:
            print(f"Geocoding partial match for: {address} -> {short}")
            return lat, lon
    print(f"Geocoding failed for: {address}")
    return None, None


def extract_property_info(pdf_path):
    """PDF\u304b\u3089\u7269\u4ef6\u60c5\u5831\u3092\u7db2\u7f85\u7684\u306b\u62bd\u51fa\u3002\u5fc5\u9808\u9805\u76ee: \u8cc3\u6599, \u5171\u76ca\u8cbb, \u9762\u7a4d, \u7bc9\u5e74\u6570, \u5099\u8003."""
    import fitz
    import unicodedata
    from datetime import datetime

    doc = fitz.open(pdf_path)
    raw_text = doc[0].get_text()
    doc.close()
    text = unicodedata.normalize("NFKC", raw_text)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    info = {"name": "", "address": "", "details": {}}
    details = info["details"]
    remarks = []

    m_bldg = re.search(r"\u5efa\u7269\u540d\s*\n?\s*(.+)", text)
    if m_bldg:
        info["name"] = m_bldg.group(1).strip()
    elif lines:
        for l in lines[:5]:
            if not re.match(r"^(\u5c02\u6709\u9762\u7a4d|\u7bc9\u5e74\u6708|\u5f15\u6e21|\u8cb8\u5e97\u8217|\u8cb8\u4e8b\u52d9\u6240|\d)", l):
                info["name"] = l
                break

    addr_match = re.search(r"\u6240\u5728\u5730\s*[:\uff1a]\s*(.+)", text)
    if addr_match:
        info["address"] = addr_match.group(1).strip()
    else:
        for pat in [r"(\u6771\u4eac\u90fd[^\n]+)", r"(\u795e\u5948\u5ddd\u770c[^\n]+)", r"(\u57fc\u7389\u770c[^\n]+)",
                    r"(\u5343\u8449\u770c[^\n]+)", r"(\u5927\u962a\u5e9c[^\n]+)", r"(\u798f\u5ca1\u770c[^\n]+)"]:
            m = re.search(pat, text)
            if m:
                addr = m.group(1).strip()
                if "\u77e5\u4e8b\u514d\u8a31" not in addr and "\u3012" not in addr:
                    info["address"] = addr
                    break

    is_gtworks = "\u3010\u7269\u4ef6\u6982\u8981\u3011" in text

    if is_gtworks:
        _extract_gtworks(text, lines, details, remarks)
    else:
        _extract_infosheet(text, lines, details, remarks)

    station_parts = re.findall(
        r"((?:JR|\u6771\u4eac\u30e1\u30c8\u30ed|\u6771\u6025|\u4eac\u738b|\u5c0f\u7530\u6025|\u90fd\u55b6|\u897f\u6b66|\u6771\u6b66)[^\n]+)\n([^\n]+)\n(\d+\u5206)",
        raw_text
    )
    if station_parts:
        details["\u4ea4\u901a"] = "; ".join(f"{l} {s} {t}" for l, s, t in station_parts[:4])
    else:
        m = re.search(r"((?:JR|\u6771\u4eac\u30e1\u30c8\u30ed|\u6771\u6025|\u4eac\u738b|\u90fd\u55b6)\S+\s+\S+\s+\u5f92\u6b69\d+\u5206)", text)
        if m:
            details["\u4ea4\u901a"] = m.group(1)

    company_match = re.search(r"(\u682a\u5f0f\u4f1a\u793e\S+|\u6709\u9650\u4f1a\u793e\S+)", text)
    if company_match:
        details["\u7ba1\u7406\u4f1a\u793e"] = company_match.group(1)
    tel_match = re.search(r"TEL[:\uff1a]?\s*([\d-]+)", text)
    if tel_match:
        details["TEL"] = tel_match.group(1)
    fax_match = re.search(r"FAX[:\uff1a]?\s*([\d-]+)", text)
    if fax_match:
        details["FAX"] = fax_match.group(1)

    if remarks:
        details["\u5099\u8003"] = " / ".join(remarks)

    for key in ["\u8cc3\u6599", "\u5171\u76ca\u8cbb", "\u9762\u7a4d", "\u7bc9\u5e74\u6570", "\u6577\u91d1/\u4fdd\u8a3c\u91d1", "\u793c\u91d1", "\u7ba1\u7406\u4f1a\u793e", "TEL"]:
        if key not in details:
            details[key] = "-"

    return info


def _extract_gtworks(text, lines, details, remarks):
    """GT-works\u5f62\u5f0f\u306ePDF\u62bd\u51fa."""
    from datetime import datetime

    rent_matches = re.findall(r"([\d,]+)\s*\u5186\s*\n?\s*\(\u5761\u5358\u4fa1[:\uff1a]?([\d,]+)\s*\u5186\)", text)
    if rent_matches:
        rents = [f"{r[0]}\u5186 (@{r[1]}\u5186)" for r in rent_matches]
        details["\u8cc3\u6599"] = " / ".join(rents)
    else:
        m = re.search(r"\u8cc3\u6599\s*\n?\s*([\d,]+)\s*\u5186", text)
        if m:
            details["\u8cc3\u6599"] = m.group(1) + "\u5186"
        elif "\u7121\u3057" in text and re.search(r"\u8cc3\u6599\s*\n", text):
            details["\u8cc3\u6599"] = "\u975e\u516c\u958b"

    m = re.search(r"\u5171\u76ca\u8cbb\s*\n?\s*([\d,]+)\s*\u5186", text)
    if m:
        details["\u5171\u76ca\u8cbb"] = m.group(1) + "\u5186"
    elif re.search(r"\u5171\u76ca\u8cbb\s*\n?\s*\u8fbc\b", text) or re.search(r"\n\u8fbc\n", text):
        details["\u5171\u76ca\u8cbb"] = "\u8cc3\u6599\u8fbc\u307f"
    elif re.search(r"\u5171\u76ca\u8cbb\s*\n?\s*\u7121\u3057", text) or re.search(r"\u5171\u76ca\u8cbb\s*\n?\s*\u306a\u3057", text):
        details["\u5171\u76ca\u8cbb"] = "\u306a\u3057"

    area_matches = re.findall(r"(\d+(?:\.\d+)?)\s*\u5751\s*\n?\s*\(([\d.]+)\s*m", text)
    if area_matches:
        areas = [f"{a[0]}\u5751 ({a[1]}m\u00b2)" for a in area_matches]
        details["\u9762\u7a4d"] = " / ".join(areas)

    m = re.search(r"\u7aef\u5de5\s*[:\uff1a]\s*(\d{4})[/\u5e74](\d{1,2})", text)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        age = datetime.now().year - year
        details["\u7bc9\u5e74\u6570"] = f"{age}\u5e74 ({year}/{month:02d})"

    m = re.search(r"\u69cb\u9020\s*[:\uff1a]\s*(\S+)", text)
    if m:
        structure = m.group(1)
        m2 = re.search(r"\u898f\u6a21\s*[:\uff1a]\s*(\S+)", text)
        if m2:
            structure += f" {m2.group(1)}"
        details["\u69cb\u9020"] = structure

    m = re.search(r"\u5165\u5c45\u65e5\n([\s\S]+?)\u6240\u5728\u5730", text)
    if m:
        block = m.group(1)
        floors = re.findall(r"^(\d+)\n", block, re.MULTILINE)
        if floors:
            details["\u968e\u6570"] = "F / ".join(floors) + "F"

    dep_matches = re.findall(r"(\d+\u30f6\u6708)", text)
    if dep_matches:
        details["\u9810\u8a17\u91d1"] = dep_matches[0]

    contracts = re.findall(r"(\u5b9a\u671f\u501f\u5bb6[^\n]*|\d+\u5e74)", text)
    if contracts:
        details["\u5951\u7d04"] = contracts[0].strip()

    entry_matches = re.findall(r"(\u5373|\u76f8\u8ac7|\d{4}/\d{1,2}(?:/\d{1,2})?(?:\u4ee5\u964d|\u4e88\u5b9a)?)", text)
    if entry_matches:
        details["\u5165\u5c45\u65e5"] = entry_matches[-1]

    for label, key in [("EV", "EV"), ("\u8b66\u5099", "\u8b66\u5099"), ("\u7a7a\u8abf", "\u7a7a\u8abf"),
                       ("\u30c8\u30a4\u30ec", "\u30c8\u30a4\u30ec"), ("\u4f7f\u7528\u6642\u9593", "\u4f7f\u7528\u6642\u9593")]:
        m = re.search(rf"{label}\s*[:\uff1a]\s*(.+)", text)
        if m:
            remarks.append(f"{key}: {m.group(1).strip()}")

    bed_matches = re.findall(r"(OA\u30d5\u30ed\u30a2\u30fc|\u30bf\u30a4\u30eb\u30ab\u30fc\u30da\u30c3\u30c8|\u30d5\u30ea\u30fc\u30a2\u30af\u30bb\u30b9|P\u30bf\u30a4\u30eb)", text)
    if bed_matches:
        remarks.append(f"\u5e8a: {bed_matches[0]}")

    ng = re.findall(r"(\u30cd\u30c3\u30c8\u9762\u7a4d|\u30b0\u30ed\u30b9\u9762\u7a4d)", text)
    if ng:
        remarks.append(ng[0])

    m = re.search(r"\u66f4\u65b0\u6599\s*\n?\s*(\S+)", text)
    if m and m.group(1) not in ("-", "\u7121\u3057", "\u511f\u5374\u8cbb"):
        remarks.append(f"\u66f4\u65b0\u6599: {m.group(1)}")
    m = re.search(r"\u511f\u5374\u8cbb?\s*\n?\s*(\S+)", text)
    if m and m.group(1) not in ("-", "\u7121\u3057", "\u793c\u91d1"):
        remarks.append(f"\u511f\u5374: {m.group(1)}")

    m = re.search(r"\u793c\u91d1\s*\n?\s*(\S+)", text)
    if m and m.group(1) not in ("-", "\u7121\u3057", "\u5951\u7d04\u671f\u9593"):
        details["\u793c\u91d1"] = m.group(1)
    else:
        details["\u793c\u91d1"] = "\u306a\u3057"

    if "\u9810\u8a17\u91d1" in details:
        details["\u6577\u91d1/\u4fdd\u8a3c\u91d1"] = details.pop("\u9810\u8a17\u91d1")


def _extract_infosheet(text, lines, details, remarks):
    """infosheet\u5f62\u5f0f\u306ePDF\u62bd\u51fa."""
    from datetime import datetime

    m = re.search(r"\u8cc3\u6599\s*([\d,.]+\u4e07?\u5186)", text)
    if m:
        details["\u8cc3\u6599"] = m.group(1)

    m = re.search(r"\u5171\u76ca\u8cbb([\d,]+\u5186/\u6708|\u306a\u3057)", text)
    if m:
        details["\u5171\u76ca\u8cbb"] = m.group(1)
    else:
        m = re.search(r"\u7ba1\u7406\u8cbb\u7b49\s*\n?\s*([\d,]+\u5186/\u6708|\u306a\u3057)", text)
        if m:
            details["\u5171\u76ca\u8cbb"] = m.group(1)
        else:
            m = re.search(r"([\d,]+)\u5186/\u6708\s*\u5171\u76ca\u8cbb", text)
            if m:
                details["\u5171\u76ca\u8cbb"] = m.group(1) + "\u5186/\u6708"

    m = re.search(r"\u9762\s*\u7a4d\s*\n?\s*([\d.]+)\s*m|\u9762\u7a4d\s*\n?\s*([\d.]+)m|([\d.]+)\s*m\u00b2|([\d.]+)\s*\u33a1", text)
    if m:
        sqm = next(g for g in m.groups() if g)
        tsubo = round(float(sqm) / 3.30579, 2)
        details["\u9762\u7a4d"] = f"{tsubo}\u5751 ({sqm}m\u00b2)"
    else:
        m = re.search(r"([\d.]+)\s*\u5751", text)
        if m:
            details["\u9762\u7a4d"] = m.group(1) + "\u5751"

    m = re.search(r"\u7bc9\s*\u5e74\s*\u6708?\s*\n?\s*(\d{4})\u5e74(\d{1,2})\u6708", text)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        age = datetime.now().year - year
        details["\u7bc9\u5e74\u6570"] = f"{age}\u5e74 ({year}/{month:02d})"

    m = re.search(r"\u69cb\u9020[\u30fb\uff65]?\u898f\u6a21\s*\n?\s*(\S+\s+\S+)", text)
    if m:
        details["\u69cb\u9020"] = m.group(1).strip()

    dep_parts = []
    for label in ["\u6577\u91d1", "\u4fdd\u8a3c\u91d1"]:
        m = re.search(rf"{label}\s+([\d.]+\u30f6\u6708|\u306a\u3057|[\d,]+\u4e07?\u5186)", text)
        if m and m.group(1) != "\u306a\u3057":
            dep_parts.append(f"{label}{m.group(1)}")
    if dep_parts:
        details["\u6577\u91d1/\u4fdd\u8a3c\u91d1"] = " / ".join(dep_parts)

    m = re.search(r"\u793c\u91d1\s+([\d.]+\u30f6\u6708|\u306a\u3057|[\d,]+\u4e07?\u5186)", text)
    if m and m.group(1) != "\u306a\u3057":
        details["\u793c\u91d1"] = m.group(1)
    else:
        details["\u793c\u91d1"] = "\u306a\u3057"

    m = re.search(r"\u5951\u7d04\u671f\u9593\s*\n?\s*(\d+\u5e74|\u5b9a\u671f\u501f\u5bb6)", text)
    if m:
        details["\u5951\u7d04"] = m.group(1)

    m = re.search(r"\u5f15\u6e21\u53ef\u80fd\s*\n?\s*\u6642\s*\u671f\s*\n?\s*(\S+)", text)
    if m:
        details["\u5165\u5c45\u65e5"] = m.group(1)

    m = re.search(r"\u8a2d\s*\u5099\s*\n?\s*(.+?)(?:\n\u5099\s*\u8003|\n$)", text, re.DOTALL)
    if m:
        equip = m.group(1).strip().replace("\n", ", ")
        if equip and equip != "-":
            remarks.append(f"\u8a2d\u5099: {equip}")

    m = re.search(r"\u5099\s*\u8003\s*\n(.+?)(?:\n\u3053\u306e\u56f3\u9762|\ninfosheet)", text, re.DOTALL)
    if m:
        biko = " ".join(m.group(1).split())
        if len(biko) > 200:
            biko = biko[:200] + "..."
        remarks.append(biko)

    m = re.search(r"\u30c1\u30a7\u30c3\u30af\u30dd\u30a4\u30f3\u30c8\uff01\s*\n(.+?)(?:\n\u7269)", text, re.DOTALL)
    if m:
        cp = m.group(1).strip().replace("\n", ", ")
        remarks.append(f"\u7279\u5fb4: {cp}")


# ===================== Routes =====================

# --- Sync / polling ---
_last_change_ts = time.time()


def bump_change():
    global _last_change_ts
    _last_change_ts = time.time()


@app.route("/api/sync")
def get_sync():
    """Return current change timestamp for polling."""
    return jsonify({"ts": _last_change_ts})


@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    email = data.get("email", "").strip()
    password = data.get("password", "")
    if email in USERS and USERS[email] == password:
        session["logged_in"] = True
        session["user_email"] = email
        return jsonify({"status": "ok"})
    return jsonify({"error": "invalid", "message": "ID\u307e\u305f\u306f\u30d1\u30b9\u30ef\u30fc\u30c9\u304c\u6b63\u3057\u304f\u3042\u308a\u307e\u305b\u3093"}), 401


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"status": "ok"})


@app.route("/api/auth-check")
def auth_check():
    if session.get("logged_in"):
        return jsonify({"loggedIn": True, "email": session.get("user_email", "")})
    return jsonify({"loggedIn": False})


@app.route("/")
def index():
    return render_template("index.html")


# --- Workspace API ---

@app.route("/api/workspaces")
def get_workspaces():
    return jsonify(load_workspaces())


@app.route("/api/workspaces", methods=["POST"])
def create_workspace():
    data = request.json
    ws_id = f"ws_{int(time.time() * 1000)}"
    new_ws = {
        "id": ws_id,
        "name": data.get("name", "\u65b0\u898f\u30ef\u30fc\u30af\u30b9\u30da\u30fc\u30b9"),
        "stations": data.get("stations", []),
        "center": data.get("center", {"lat": 35.6812, "lon": 139.7671}),
        "zoom": data.get("zoom", 14),
    }
    supabase.table("workspaces").insert({
        "id": new_ws["id"],
        "name": new_ws["name"],
        "stations": new_ws.get("stations"),
        "center": new_ws.get("center"),
        "zoom": new_ws.get("zoom", 14),
    }).execute()
    bump_change()
    return jsonify({"status": "ok", "workspace": new_ws})


@app.route("/api/workspaces/<ws_id>", methods=["PUT"])
def update_workspace(ws_id):
    updates = request.json
    update_data = {}
    if "name" in updates:
        update_data["name"] = updates["name"]
    if "stations" in updates:
        update_data["stations"] = updates["stations"]
    if "center" in updates:
        update_data["center"] = updates["center"]
    if "zoom" in updates:
        update_data["zoom"] = updates["zoom"]
    if "criteria" in updates:
        update_data["criteria"] = updates["criteria"]
    if not update_data:
        return jsonify({"status": "ok"})
    resp = supabase.table("workspaces").update(update_data).eq("id", ws_id).execute()
    if not resp.data:
        return jsonify({"error": "not found"}), 404
    bump_change()
    return jsonify({"status": "ok"})


@app.route("/api/workspaces/<ws_id>", methods=["DELETE"])
def delete_workspace(ws_id):
    # Check count
    resp = supabase.table("workspaces").select("id").execute()
    if len(resp.data or []) <= 1:
        return jsonify({"error": "\u6700\u5f8c\u306e\u30ef\u30fc\u30af\u30b9\u30da\u30fc\u30b9\u306f\u524a\u9664\u3067\u304d\u307e\u305b\u3093"}), 400
    # Delete properties for this workspace
    supabase.table("properties").delete().eq("workspace_id", ws_id).execute()
    # Delete workspace
    supabase.table("workspaces").delete().eq("id", ws_id).execute()
    # Update active workspace if needed
    active = _get_app_setting("activeWorkspace")
    if active == ws_id:
        remaining = supabase.table("workspaces").select("id").limit(1).execute()
        new_active = remaining.data[0]["id"] if remaining.data else "ws_1"
        _set_app_setting("activeWorkspace", new_active)
        bump_change()
        return jsonify({"status": "ok", "activeWorkspace": new_active})
    bump_change()
    return jsonify({"status": "ok", "activeWorkspace": active})


@app.route("/api/workspaces/active", methods=["PUT"])
def set_active_workspace():
    ws_id = request.json.get("id")
    resp = supabase.table("workspaces").select("id").eq("id", ws_id).execute()
    if not resp.data:
        return jsonify({"error": "not found"}), 404
    _set_app_setting("activeWorkspace", ws_id)
    bump_change()
    return jsonify({"status": "ok"})


# --- Property API (workspace-aware) ---

@app.route("/api/properties")
def get_properties():
    return jsonify(load_properties(get_active_ws_id()))


@app.route("/api/properties/<prop_id>/memo", methods=["PUT"])
def update_memo(prop_id):
    memo = request.json.get("memo", "")
    resp = supabase.table("properties").update({"memo": memo}).eq("id", prop_id).execute()
    if not resp.data:
        return jsonify({"error": "not found"}), 404
    bump_change()
    return jsonify({"status": "ok"})


@app.route("/api/properties/<prop_id>/color", methods=["PUT"])
def update_color(prop_id):
    color = request.json.get("color", "blue")
    if color not in ("blue", "red", "green"):
        color = "blue"
    resp = supabase.table("properties").update({"color": color}).eq("id", prop_id).execute()
    if not resp.data:
        return jsonify({"error": "not found"}), 404
    bump_change()
    return jsonify({"status": "ok"})


@app.route("/api/upload", methods=["POST"])
def upload_pdf():
    ws_id = get_active_ws_id()
    if "pdf" not in request.files:
        return jsonify({"error": "no file"}), 400
    file = request.files["pdf"]
    if not file.filename.endswith(".pdf"):
        return jsonify({"error": "not a PDF"}), 400
    filename = file.filename
    filepath = os.path.join(PDF_DIR, filename)
    file.save(filepath)
    info = extract_property_info(filepath)
    manual_address = request.form.get("address", "").strip()
    if manual_address:
        info["address"] = manual_address
    if not info["address"]:
        return jsonify({"error": "address_not_found", "extracted": info,
                        "filename": filename, "message": "\u4f4f\u6240\u3092\u81ea\u52d5\u62bd\u51fa\u3067\u304d\u307e\u305b\u3093\u3067\u3057\u305f\u3002"})
    lat, lon = geocode_address(info["address"])
    if lat is None:
        return jsonify({"error": "geocode_failed", "extracted": info,
                        "filename": filename, "message": "\u30b8\u30aa\u30b3\u30fc\u30c7\u30a3\u30f3\u30b0\u306b\u5931\u6557\u3057\u307e\u3057\u305f\u3002"})
    prop_id = f"prop_{int(time.time() * 1000)}"
    new_prop = {"id": prop_id, "name": info["name"], "address": info["address"],
                "lat": lat, "lon": lon, "filename": filename,
                "details": info["details"], "memo": ""}
    supabase.table("properties").insert({
        "id": prop_id,
        "workspace_id": ws_id,
        "name": info["name"],
        "address": info["address"],
        "lat": lat,
        "lon": lon,
        "filename": filename,
        "details": info["details"],
        "memo": "",
        "color": "blue",
    }).execute()
    bump_change()
    return jsonify({"status": "ok", "property": new_prop})


@app.route("/api/properties/manual", methods=["POST"])
def add_property_manual():
    ws_id = get_active_ws_id()
    data = request.json
    name = data.get("name", "").strip()
    address = data.get("address", "").strip()
    details = data.get("details", {})
    if not name or not address:
        return jsonify({"error": "missing_fields", "message": "\u7269\u4ef6\u540d\u3068\u4f4f\u6240\u306f\u5fc5\u9808\u3067\u3059"}), 400
    lat, lon = geocode_address(address)
    if lat is None:
        return jsonify({"error": "geocode_failed", "message": "\u4f4f\u6240\u304b\u3089\u306e\u4f4d\u7f6e\u7279\u5b9a\u306b\u5931\u6557\u3057\u307e\u3057\u305f\u3002\u4f4f\u6240\u3092\u78ba\u8a8d\u3057\u3066\u304f\u3060\u3055\u3044\u3002"})
    prop_id = f"prop_{int(time.time() * 1000)}"
    new_prop = {"id": prop_id, "name": name, "address": address,
                "lat": lat, "lon": lon, "filename": "",
                "details": details, "memo": ""}
    supabase.table("properties").insert({
        "id": prop_id,
        "workspace_id": ws_id,
        "name": name,
        "address": address,
        "lat": lat,
        "lon": lon,
        "filename": "",
        "details": details,
        "memo": "",
        "color": "blue",
    }).execute()
    bump_change()
    return jsonify({"status": "ok", "property": new_prop})


@app.route("/api/properties/<prop_id>/details", methods=["PUT"])
def update_details(prop_id):
    details = request.json.get("details", {})
    resp = supabase.table("properties").update({"details": details}).eq("id", prop_id).execute()
    if not resp.data:
        return jsonify({"error": "not found"}), 404
    bump_change()
    return jsonify({"status": "ok"})


@app.route("/api/properties/<prop_id>", methods=["DELETE"])
def delete_property(prop_id):
    supabase.table("properties").delete().eq("id", prop_id).execute()
    bump_change()
    return jsonify({"status": "ok"})


@app.route("/api/properties/<prop_id>/move", methods=["PUT"])
def move_property(prop_id):
    """Move a property to a different workspace."""
    target_ws_id = request.json.get("targetWs")
    if not target_ws_id:
        return jsonify({"error": "targetWs required"}), 400
    resp = supabase.table("properties").select("*").eq("id", prop_id).execute()
    if not resp.data:
        return jsonify({"error": "not found"}), 404
    supabase.table("properties").update({"workspace_id": target_ws_id}).eq("id", prop_id).execute()
    bump_change()
    return jsonify({"status": "ok"})


# --- Station geocoding ---

MAJOR_STATIONS = {"\u6e0b\u8c37", "\u65b0\u5bbf", "\u6c60\u888b", "\u6771\u4eac", "\u54c1\u5ddd", "\u4e0a\u91ce", "\u6a2a\u6d5c", "\u5927\u5bae", "\u5343\u8449", "\u7acb\u5ddd", "\u753a\u7530", "\u5409\u7965\u5bfa", "\u5317\u5343\u4f4f", "\u5927\u624b\u753a", "\u79cb\u8449\u539f"}

@app.route("/api/geocode-station")
def geocode_station():
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    search_name = name if name.endswith("\u99c5") else name + "\u99c5"
    query = urllib.parse.urlencode({
        "q": search_name, "format": "json", "limit": 1, "countrycodes": "jp",
    })
    url = f"https://nominatim.openstreetmap.org/search?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "PropertyMapApp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                base_name = search_name.replace("\u99c5", "")
                radius = 180 if base_name in MAJOR_STATIONS else 120
                return jsonify({"status": "ok", "lat": lat, "lon": lon, "r": radius, "name": search_name})
    except Exception as e:
        print(f"Station geocoding failed: {e}")
    return jsonify({"error": "not_found", "message": f"\u300c{search_name}\u300d\u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093\u3067\u3057\u305f"})


# --- PDF serving ---

@app.route("/pdf/<path:filename>")
def serve_pdf(filename):
    resp = send_from_directory(PDF_DIR, filename, mimetype="application/pdf")
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@app.route("/pdf-images/<path:filename>")
def serve_pdf_as_images(filename):
    import fitz
    from flask import Response
    filepath = os.path.join(PDF_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "not found"}), 404
    page_num = request.args.get("page", 0, type=int)
    doc = fitz.open(filepath)
    if page_num >= len(doc):
        doc.close()
        return jsonify({"error": "page not found"}), 404
    page = doc[page_num]
    pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
    img_bytes = pix.tobytes("png")
    total_pages = len(doc)
    doc.close()
    resp = Response(img_bytes, mimetype="image/png")
    resp.headers["Cache-Control"] = "public, max-age=86400"
    resp.headers["X-Total-Pages"] = str(total_pages)
    return resp


# ===================== Agents =====================

def load_agents():
    resp = supabase.table("agents").select("*").execute()
    rows = resp.data or []
    agents = []
    for r in rows:
        agents.append({
            "id": r["id"],
            "name": r.get("name", ""),
            "email": r.get("email", ""),
            "phone": r.get("phone", ""),
            "area": r.get("area", ""),
            "managerArea": r.get("manager_area", ""),
            "memo": r.get("memo", ""),
        })
    return agents


def save_agents(agents):
    """Full overwrite of agents table."""
    supabase.table("agents").delete().neq("id", "__never__").execute()
    for a in agents:
        supabase.table("agents").insert({
            "id": a["id"],
            "name": a.get("name", ""),
            "email": a.get("email", ""),
            "phone": a.get("phone", ""),
            "area": a.get("area", ""),
            "manager_area": a.get("managerArea", ""),
            "memo": a.get("memo", ""),
        }).execute()
    bump_change()


@app.route("/api/agents")
def get_agents():
    return jsonify(load_agents())


@app.route("/api/agents", methods=["POST"])
def create_agent():
    data = request.json
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    if not name or not email:
        return jsonify({"error": "missing_fields", "message": "\u540d\u524d\u3068\u30e1\u30fc\u30eb\u30a2\u30c9\u30ec\u30b9\u306f\u5fc5\u9808\u3067\u3059"}), 400
    agent = {
        "id": f"agent_{int(time.time() * 1000)}",
        "name": name,
        "email": email,
        "phone": data.get("phone", "").strip(),
        "area": data.get("area", ""),
        "managerArea": data.get("managerArea", ""),
        "memo": data.get("memo", "").strip(),
    }
    supabase.table("agents").insert({
        "id": agent["id"],
        "name": agent["name"],
        "email": agent["email"],
        "phone": agent["phone"],
        "area": agent["area"],
        "manager_area": agent["managerArea"],
        "memo": agent["memo"],
    }).execute()
    bump_change()
    return jsonify({"status": "ok", "agent": agent})


@app.route("/api/agents/<agent_id>", methods=["PUT"])
def update_agent(agent_id):
    data = request.json
    update_data = {}
    for key in ["name", "email", "phone", "area", "memo"]:
        if key in data:
            update_data[key] = data[key].strip() if isinstance(data[key], str) else data[key]
    if "managerArea" in data:
        update_data["manager_area"] = data["managerArea"].strip() if isinstance(data["managerArea"], str) else data["managerArea"]
    resp = supabase.table("agents").update(update_data).eq("id", agent_id).execute()
    if not resp.data:
        return jsonify({"error": "not found"}), 404
    # Return agent in frontend format
    row = resp.data[0]
    agent = {
        "id": row["id"],
        "name": row.get("name", ""),
        "email": row.get("email", ""),
        "phone": row.get("phone", ""),
        "area": row.get("area", ""),
        "managerArea": row.get("manager_area", ""),
        "memo": row.get("memo", ""),
    }
    bump_change()
    return jsonify({"status": "ok", "agent": agent})


@app.route("/api/agents/<agent_id>", methods=["DELETE"])
def delete_agent(agent_id):
    supabase.table("agents").delete().eq("id", agent_id).execute()
    bump_change()
    return jsonify({"status": "ok"})


@app.route("/api/agents/<agent_id>/properties")
def get_agent_properties(agent_id):
    resp = supabase.table("agents").select("*").eq("id", agent_id).execute()
    if not resp.data:
        return jsonify({"error": "not found"}), 404
    agent = resp.data[0]
    area = agent.get("area", "") or ""
    manager_area = agent.get("manager_area", "") or ""
    combined = set()
    if area:
        combined.update(x.strip() for x in area.split(",") if x.strip())
    if manager_area:
        combined.update(x.strip() for x in manager_area.split(",") if x.strip())
    ws_ids = list(combined)
    all_props = []
    ws_data = load_workspaces()
    for ws_id in ws_ids:
        props = load_properties(ws_id)
        ws_name = next((w["name"] for w in ws_data["workspaces"] if w["id"] == ws_id), ws_id)
        for p in props:
            p["_wsName"] = ws_name
        all_props.extend(props)
    return jsonify(all_props)


# ===================== Schedules =====================

def load_schedules():
    resp = supabase.table("schedules").select("*").execute()
    rows = resp.data or []
    schedules = []
    for r in rows:
        schedules.append({
            "id": r["id"],
            "title": r.get("title", ""),
            "agentId": r.get("agent_id", ""),
            "propertyId": r.get("property_id", ""),
            "type": r.get("type", "\u305d\u306e\u4ed6"),
            "date": r.get("date", ""),
            "startTime": r.get("start_time", "10:00"),
            "endTime": r.get("end_time", "11:00"),
            "memo": r.get("memo", ""),
        })
    return schedules


@app.route("/api/schedules")
def get_schedules():
    month = request.args.get("month", "")
    if month:
        # Filter by month prefix using Supabase like
        resp = supabase.table("schedules").select("*").like("date", f"{month}%").execute()
    else:
        resp = supabase.table("schedules").select("*").execute()
    rows = resp.data or []
    schedules = []
    for r in rows:
        schedules.append({
            "id": r["id"],
            "title": r.get("title", ""),
            "agentId": r.get("agent_id", ""),
            "propertyId": r.get("property_id", ""),
            "type": r.get("type", "\u305d\u306e\u4ed6"),
            "date": r.get("date", ""),
            "startTime": r.get("start_time", "10:00"),
            "endTime": r.get("end_time", "11:00"),
            "memo": r.get("memo", ""),
        })
    return jsonify(schedules)


@app.route("/api/schedules", methods=["POST"])
def create_schedule():
    data = request.json
    title = data.get("title", "").strip()
    date = data.get("date", "").strip()
    if not title or not date:
        return jsonify({"error": "missing_fields", "message": "\u30bf\u30a4\u30c8\u30eb\u3068\u65e5\u4ed8\u306f\u5fc5\u9808\u3067\u3059"}), 400
    sch = {
        "id": f"sch_{int(time.time() * 1000)}",
        "title": title,
        "agentId": data.get("agentId", ""),
        "propertyId": data.get("propertyId", ""),
        "type": data.get("type", "\u305d\u306e\u4ed6"),
        "date": date,
        "startTime": data.get("startTime", "10:00"),
        "endTime": data.get("endTime", "11:00"),
        "memo": data.get("memo", ""),
    }
    supabase.table("schedules").insert({
        "id": sch["id"],
        "title": sch["title"],
        "agent_id": sch["agentId"],
        "property_id": sch["propertyId"],
        "type": sch["type"],
        "date": sch["date"],
        "start_time": sch["startTime"],
        "end_time": sch["endTime"],
        "memo": sch["memo"],
    }).execute()
    bump_change()
    return jsonify({"status": "ok", "schedule": sch})


@app.route("/api/schedules/<sch_id>", methods=["PUT"])
def update_schedule(sch_id):
    data = request.json
    update_data = {}
    field_map = {
        "title": "title",
        "agentId": "agent_id",
        "propertyId": "property_id",
        "type": "type",
        "date": "date",
        "startTime": "start_time",
        "endTime": "end_time",
        "memo": "memo",
    }
    for frontend_key, db_key in field_map.items():
        if frontend_key in data:
            val = data[frontend_key]
            update_data[db_key] = val.strip() if isinstance(val, str) else val
    resp = supabase.table("schedules").update(update_data).eq("id", sch_id).execute()
    if not resp.data:
        return jsonify({"error": "not found"}), 404
    row = resp.data[0]
    schedule = {
        "id": row["id"],
        "title": row.get("title", ""),
        "agentId": row.get("agent_id", ""),
        "propertyId": row.get("property_id", ""),
        "type": row.get("type", ""),
        "date": row.get("date", ""),
        "startTime": row.get("start_time", ""),
        "endTime": row.get("end_time", ""),
        "memo": row.get("memo", ""),
    }
    bump_change()
    return jsonify({"status": "ok", "schedule": schedule})


@app.route("/api/schedules/<sch_id>", methods=["DELETE"])
def delete_schedule(sch_id):
    supabase.table("schedules").delete().eq("id", sch_id).execute()
    bump_change()
    return jsonify({"status": "ok"})


# ===================== Main =====================

if __name__ == "__main__":
    import argparse
    import subprocess
    import threading

    parser = argparse.ArgumentParser(description="\u7269\u4ef6\u30de\u30c3\u30d7\u30b5\u30fc\u30d0\u30fc")
    parser.add_argument("--public", action="store_true")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    if args.public:
        def start_tunnel():
            import sys
            print("\n  \u30c8\u30f3\u30cd\u30eb\u63a5\u7d9a\u4e2d...", flush=True)
            cf_path = "/tmp/cloudflared"
            proc = subprocess.Popen(
                [cf_path, "tunnel", "--url", f"http://localhost:{args.port}"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL)
            for line in proc.stdout:
                text = line.decode("utf-8", errors="replace")
                urls = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", text)
                if urls:
                    msg = (f"\n{'='*60}\n"
                           f"  \u5916\u90e8\u516c\u958bURL: {urls[0]}\n"
                           f"  \u3053\u306eURL\u3092\u30b3\u30d4\u30fc\u3057\u3066\u5171\u6709\u3057\u3066\u304f\u3060\u3055\u3044\n"
                           f"  \u78ba\u8a8d\u30da\u30fc\u30b8\u306a\u3057\u30fb\u8ab0\u3067\u3082\u5373\u30a2\u30af\u30bb\u30b9\u53ef\u80fd\n"
                           f"{'='*60}\n")
                    sys.stdout.write(msg); sys.stdout.flush(); break
        threading.Thread(target=start_tunnel, daemon=True).start()

    host = "0.0.0.0" if args.public else "127.0.0.1"
    app.run(host=host, port=args.port, debug=not args.public)
