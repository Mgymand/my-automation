import os
import json
import re
import ssl
import urllib.request
import urllib.parse
import time
import shutil
from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "estateforce-secret-key-2026")

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
WORKSPACES_FILE = os.path.join(DATA_DIR, "workspaces.json")
WORKSPACES_DIR = os.path.join(DATA_DIR, "workspaces")
OLD_PROPERTIES_FILE = os.path.join(DATA_DIR, "properties.json")
AGENTS_FILE = os.path.join(DATA_DIR, "agents.json")
SCHEDULES_FILE = os.path.join(DATA_DIR, "schedules.json")

os.makedirs(PDF_DIR, exist_ok=True)
os.makedirs(WORKSPACES_DIR, exist_ok=True)

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# --- GitHub persistent storage ---

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "Mgymand/my-automation")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "claude/frosty-swartz")
GITHUB_DATA_PREFIX = "property-map/data/"


def _github_api(method, path, data=None):
    """Call GitHub API."""
    if not GITHUB_TOKEN:
        return None
    url = f"https://api.github.com{path}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "PropertyMapApp/1.0",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"GitHub API error ({method} {path}): {e}")
        return None


def sync_file_to_github(local_path):
    """Upload a local file to GitHub repo (non-blocking)."""
    if not GITHUB_TOKEN:
        return
    import threading, base64
    def _sync():
        try:
            # Relative path within data dir
            rel = os.path.relpath(local_path, DATA_DIR)
            gh_path = GITHUB_DATA_PREFIX + rel
            with open(local_path, "rb") as f:
                content = base64.b64encode(f.read()).decode("ascii")
            # Get current file SHA (needed for update)
            api_path = f"/repos/{GITHUB_REPO}/contents/{gh_path}?ref={GITHUB_BRANCH}"
            existing = _github_api("GET", api_path)
            sha = existing.get("sha") if existing else None
            # Create or update
            payload = {
                "message": f"Auto-sync: {rel}",
                "content": content,
                "branch": GITHUB_BRANCH,
            }
            if sha:
                payload["sha"] = sha
            _github_api("PUT", f"/repos/{GITHUB_REPO}/contents/{gh_path}", payload)
        except Exception as e:
            print(f"GitHub sync error: {e}")
    threading.Thread(target=_sync, daemon=True).start()


# --- Workspace helpers ---

_ws_cache = None
_ws_mtime = 0

DEFAULT_STATIONS = [
    {"name": "渋谷駅", "lat": 35.6580, "lon": 139.7016, "r": 180},
    {"name": "表参道駅", "lat": 35.6654, "lon": 139.7122, "r": 120},
    {"name": "明治神宮前駅", "lat": 35.6699, "lon": 139.7024, "r": 100},
]


def load_workspaces():
    global _ws_cache, _ws_mtime
    if not os.path.exists(WORKSPACES_FILE):
        _migrate_to_workspaces()
    mtime = os.path.getmtime(WORKSPACES_FILE)
    if _ws_cache is not None and mtime == _ws_mtime:
        return _ws_cache
    with open(WORKSPACES_FILE, "r", encoding="utf-8") as f:
        _ws_cache = json.load(f)
    _ws_mtime = mtime
    return _ws_cache


def save_workspaces(data):
    global _ws_cache, _ws_mtime
    with open(WORKSPACES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _ws_cache = data
    _ws_mtime = os.path.getmtime(WORKSPACES_FILE)
    sync_file_to_github(WORKSPACES_FILE)
    bump_change()


def _migrate_to_workspaces():
    """Migrate existing properties.json to workspace system."""
    ws_id = "ws_1"
    ws_dir = os.path.join(WORKSPACES_DIR, ws_id)
    os.makedirs(ws_dir, exist_ok=True)

    # Copy existing properties
    old_props = []
    if os.path.exists(OLD_PROPERTIES_FILE):
        with open(OLD_PROPERTIES_FILE, "r", encoding="utf-8") as f:
            old_props = json.load(f)

    with open(os.path.join(ws_dir, "properties.json"), "w", encoding="utf-8") as f:
        json.dump(old_props, f, ensure_ascii=False, indent=2)

    data = {
        "activeWorkspace": ws_id,
        "workspaces": [{
            "id": ws_id,
            "name": "新オフィス用",
            "stations": DEFAULT_STATIONS,
            "center": {"lat": 35.6595, "lon": 139.7005},
            "zoom": 16,
        }],
    }
    save_workspaces(data)


def get_active_ws_id():
    ws_id = request.args.get("ws")
    if ws_id:
        return ws_id
    return load_workspaces().get("activeWorkspace", "ws_1")


def get_ws_props_path(ws_id):
    return os.path.join(WORKSPACES_DIR, ws_id, "properties.json")


# --- Property helpers (workspace-aware) ---

_prop_cache = {}  # {ws_id: (mtime, data)}


def load_properties(ws_id=None):
    if ws_id is None:
        ws_id = get_active_ws_id()
    path = get_ws_props_path(ws_id)
    if not os.path.exists(path):
        return []
    mtime = os.path.getmtime(path)
    cached = _prop_cache.get(ws_id)
    if cached and cached[0] == mtime:
        return cached[1]
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _prop_cache[ws_id] = (mtime, data)
    return data


def save_properties(props, ws_id=None):
    if ws_id is None:
        ws_id = get_active_ws_id()
    path = get_ws_props_path(ws_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(props, f, ensure_ascii=False, indent=2)
    _prop_cache[ws_id] = (os.path.getmtime(path), props)
    sync_file_to_github(path)
    bump_change()


# --- Address / PDF helpers ---

def normalize_address(address):
    import unicodedata
    address = unicodedata.normalize("NFKC", address)
    # CJK部首・互換漢字 → 通常の漢字に置換
    CJK_RADICAL_MAP = {
        "\u2EC4": "西",  # ⻄ → 西
        "\u2F3B": "日",  # ⽇ → 日
        "\u2F64": "田",  # ⽥ → 田
        "\u2F8F": "草",  # ⾋ → 草 (actually 艸)
        "\u2ECD": "里",  # ⻍ → 里
        "\u2F97": "谷",  # ⾕ → 谷
        "\u2F72": "石",  # ⽯ → 石
        "\u2ECB": "辺",  # ⻋ → 辺
        "\u2ECC": "辻",  # ⻌ → 辻
    }
    for radical, kanji in CJK_RADICAL_MAP.items():
        address = address.replace(radical, kanji)
    # Remove extra spaces
    address = re.sub(r"\s+", "", address)
    chome_map = {"1": "一", "2": "二", "3": "三", "4": "四", "5": "五",
                 "6": "六", "7": "七", "8": "八", "9": "九", "10": "十"}
    def replace_chome(m):
        chome = chome_map.get(m.group(1), m.group(1))
        return f"{chome}丁目{m.group(2)}-{m.group(3)}"
    address = re.sub(r"(\d+)-(\d+)-(\d+)", replace_chome, address)
    # 「X丁目 Y番Z号」→「X丁目Y-Z」
    address = re.sub(r"(\d+)丁目\s*(\d+)番\s*(\d+)号?", lambda m: f"{chome_map.get(m.group(1), m.group(1))}丁目{m.group(2)}-{m.group(3)}", address)
    # 「X番Y号」(without 丁目) → 「X-Y」
    address = re.sub(r"(\d+)番\s*(\d+)号?", r"\1-\2", address)
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
    # Fallback: try with shorter address (up to 丁目 level)
    short = re.sub(r"(丁目).*", r"\1", normalized)
    if short != normalized:
        lat, lon = _gsi_geocode(short)
        if lat is not None:
            print(f"Geocoding partial match for: {address} -> {short}")
            return lat, lon
    print(f"Geocoding failed for: {address}")
    return None, None


def extract_property_info(pdf_path):
    """PDFから物件情報を網羅的に抽出。必須項目: 賃料, 共益費, 面積, 築年数, 備考."""
    import fitz
    import unicodedata
    from datetime import datetime

    doc = fitz.open(pdf_path)
    raw_text = doc[0].get_text()
    doc.close()
    # Normalize fullwidth chars
    text = unicodedata.normalize("NFKC", raw_text)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    info = {"name": "", "address": "", "details": {}}
    details = info["details"]
    remarks = []  # 備考に集約する情報

    # --- 物件名 (タイトル) ---
    # GT-works: first line is building name
    # Infosheet: building name is in 建物名 field
    m_bldg = re.search(r"建物名\s*\n?\s*(.+)", text)
    if m_bldg:
        info["name"] = m_bldg.group(1).strip()
    elif lines:
        # Skip non-name first lines (e.g. "専有面積")
        for l in lines[:5]:
            if not re.match(r"^(専有面積|築年月|引渡|貸店舗|貸事務所|\d)", l):
                info["name"] = l
                break

    # --- 住所 ---
    addr_match = re.search(r"所在地\s*[:：]\s*(.+)", text)
    if addr_match:
        info["address"] = addr_match.group(1).strip()
    else:
        for pat in [r"(東京都[^\n]+)", r"(神奈川県[^\n]+)", r"(埼玉県[^\n]+)",
                    r"(千葉県[^\n]+)", r"(大阪府[^\n]+)", r"(福岡県[^\n]+)"]:
            m = re.search(pat, text)
            if m:
                addr = m.group(1).strip()
                # Filter out license addresses
                if "知事免許" not in addr and "〒" not in addr:
                    info["address"] = addr
                    break

    # --- Detect format: GT-works vs infosheet ---
    is_gtworks = "【物件概要】" in text

    if is_gtworks:
        _extract_gtworks(text, lines, details, remarks)
    else:
        _extract_infosheet(text, lines, details, remarks)

    # --- 共通: 交通 ---
    station_parts = re.findall(
        r"((?:JR|東京メトロ|東急|京王|小田急|都営|西武|東武)[^\n]+)\n([^\n]+)\n(\d+分)",
        raw_text
    )
    if station_parts:
        details["交通"] = "; ".join(f"{l} {s} {t}" for l, s, t in station_parts[:4])
    else:
        # infosheet format: 東京メトロ丸ノ内線 新宿三丁目 徒歩1分
        m = re.search(r"((?:JR|東京メトロ|東急|京王|都営)\S+\s+\S+\s+徒歩\d+分)", text)
        if m:
            details["交通"] = m.group(1)

    # --- 管理会社・TEL・FAX ---
    # GT-works format: 株式会社GT-works ... TEL: xxx / FAX: xxx
    # Infosheet format: 株式会社xxx ... TEL: xxx / FAX: xxx
    company_match = re.search(r"(株式会社\S+|有限会社\S+)", text)
    if company_match:
        details["管理会社"] = company_match.group(1)
    tel_match = re.search(r"TEL[:：]?\s*([\d-]+)", text)
    if tel_match:
        details["TEL"] = tel_match.group(1)
    fax_match = re.search(r"FAX[:：]?\s*([\d-]+)", text)
    if fax_match:
        details["FAX"] = fax_match.group(1)

    # --- 備考 (最後に配置) ---
    if remarks:
        details["備考"] = " / ".join(remarks)

    # --- 必須項目のデフォルト ---
    for key in ["賃料", "共益費", "面積", "築年数", "敷金/保証金", "礼金", "管理会社", "TEL"]:
        if key not in details:
            details[key] = "-"

    return info


def _extract_gtworks(text, lines, details, remarks):
    """GT-works形式のPDF抽出."""
    from datetime import datetime

    # 賃料 (坪単価含む)
    rent_matches = re.findall(r"([\d,]+)\s*円\s*\n?\s*\(坪単価[:：]?([\d,]+)\s*円\)", text)
    if rent_matches:
        rents = [f"{r[0]}円 (@{r[1]}円)" for r in rent_matches]
        details["賃料"] = " / ".join(rents)
    else:
        m = re.search(r"賃料\s*\n?\s*([\d,]+)\s*円", text)
        if m:
            details["賃料"] = m.group(1) + "円"
        elif "無し" in text and re.search(r"賃料\s*\n", text):
            details["賃料"] = "非公開"

    # 共益費
    m = re.search(r"共益費\s*\n?\s*([\d,]+)\s*円", text)
    if m:
        details["共益費"] = m.group(1) + "円"
    elif re.search(r"共益費\s*\n?\s*込\b", text) or re.search(r"\n込\n", text):
        details["共益費"] = "賃料込み"
    elif re.search(r"共益費\s*\n?\s*無し", text) or re.search(r"共益費\s*\n?\s*なし", text):
        details["共益費"] = "なし"

    # 面積 (複数階対応)
    area_matches = re.findall(r"(\d+(?:\.\d+)?)\s*坪\s*\n?\s*\(([\d.]+)\s*m", text)
    if area_matches:
        areas = [f"{a[0]}坪 ({a[1]}m²)" for a in area_matches]
        details["面積"] = " / ".join(areas)

    # 竣工 → 築年数
    m = re.search(r"竣工\s*[:：]\s*(\d{4})[/年](\d{1,2})", text)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        age = datetime.now().year - year
        details["築年数"] = f"{age}年 ({year}/{month:02d})"

    # 構造・規模
    m = re.search(r"構造\s*[:：]\s*(\S+)", text)
    if m:
        structure = m.group(1)
        m2 = re.search(r"規模\s*[:：]\s*(\S+)", text)
        if m2:
            structure += f" {m2.group(1)}"
        details["構造"] = structure

    # 階数
    floor_matches = re.findall(r"^\s*(\d+)\s*$", text, re.MULTILINE)
    #階数は面積の前に出る数字
    m = re.search(r"入居日\n([\s\S]+?)所在地", text)
    if m:
        block = m.group(1)
        floors = re.findall(r"^(\d+)\n", block, re.MULTILINE)
        if floors:
            details["階数"] = "F / ".join(floors) + "F"

    # 預託金
    dep_matches = re.findall(r"(\d+ヶ月)", text)
    if dep_matches:
        # First occurrence before 賃料 line is usually 預託金
        details["預託金"] = dep_matches[0]

    # 契約期間
    contracts = re.findall(r"(定期借家[^\n]*|\d+年)", text)
    if contracts:
        details["契約"] = contracts[0].strip()

    # 入居日 (即, 相談, 2026/xx, xxxx/xx/xx)
    entry_matches = re.findall(r"(即|相談|\d{4}/\d{1,2}(?:/\d{1,2})?(?:以降|予定)?)", text)
    if entry_matches:
        details["入居日"] = entry_matches[-1]

    # EV, 警備, 空調, トイレ, 使用時間
    for label, key in [("EV", "EV"), ("警備", "警備"), ("空調", "空調"),
                       ("トイレ", "トイレ"), ("使用時間", "使用時間")]:
        m = re.search(rf"{label}\s*[:：]\s*(.+)", text)
        if m:
            remarks.append(f"{key}: {m.group(1).strip()}")

    # 床仕様
    bed_matches = re.findall(r"(OAフロアー|タイルカーペット|フリーアクセス|Pタイル)", text)
    if bed_matches:
        remarks.append(f"床: {bed_matches[0]}")

    # ネット/グロス
    ng = re.findall(r"(ネット面積|グロス面積)", text)
    if ng:
        remarks.append(ng[0])

    # 更新料・償却
    m = re.search(r"更新料\s*\n?\s*(\S+)", text)
    if m and m.group(1) not in ("-", "無し", "償却費"):
        remarks.append(f"更新料: {m.group(1)}")
    m = re.search(r"償却費?\s*\n?\s*(\S+)", text)
    if m and m.group(1) not in ("-", "無し", "礼金"):
        remarks.append(f"償却: {m.group(1)}")

    # 礼金 → details
    m = re.search(r"礼金\s*\n?\s*(\S+)", text)
    if m and m.group(1) not in ("-", "無し", "契約期間"):
        details["礼金"] = m.group(1)
    else:
        details["礼金"] = "なし"

    # 敷金/保証金 → details (預託金を使う)
    if "預託金" in details:
        details["敷金/保証金"] = details.pop("預託金")


def _extract_infosheet(text, lines, details, remarks):
    """infosheet形式のPDF抽出."""
    from datetime import datetime

    # 賃料
    m = re.search(r"賃料\s*([\d,.]+万?円)", text)
    if m:
        details["賃料"] = m.group(1)

    # 共益費 / 管理費
    m = re.search(r"共益費([\d,]+円/月|なし)", text)
    if m:
        details["共益費"] = m.group(1)
    else:
        m = re.search(r"管理費等\s*\n?\s*([\d,]+円/月|なし)", text)
        if m:
            details["共益費"] = m.group(1)
        else:
            m = re.search(r"([\d,]+)円/月\s*共益費", text)
            if m:
                details["共益費"] = m.group(1) + "円/月"

    # 面積
    m = re.search(r"面\s*積\s*\n?\s*([\d.]+)\s*m|面積\s*\n?\s*([\d.]+)m|([\d.]+)\s*m²|([\d.]+)\s*㎡", text)
    if m:
        sqm = next(g for g in m.groups() if g)
        tsubo = round(float(sqm) / 3.30579, 2)
        details["面積"] = f"{tsubo}坪 ({sqm}m²)"
    else:
        m = re.search(r"([\d.]+)\s*坪", text)
        if m:
            details["面積"] = m.group(1) + "坪"

    # 築年月 → 築年数
    m = re.search(r"築\s*年\s*月?\s*\n?\s*(\d{4})年(\d{1,2})月", text)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        age = datetime.now().year - year
        details["築年数"] = f"{age}年 ({year}/{month:02d})"

    # 構造
    m = re.search(r"構造[・･]?規模\s*\n?\s*(\S+\s+\S+)", text)
    if m:
        details["構造"] = m.group(1).strip()

    # 敷金・保証金 → details
    dep_parts = []
    for label in ["敷金", "保証金"]:
        m = re.search(rf"{label}\s+([\d.]+ヶ月|なし|[\d,]+万?円)", text)
        if m and m.group(1) != "なし":
            dep_parts.append(f"{label}{m.group(1)}")
    if dep_parts:
        details["敷金/保証金"] = " / ".join(dep_parts)

    # 礼金 → details
    m = re.search(r"礼金\s+([\d.]+ヶ月|なし|[\d,]+万?円)", text)
    if m and m.group(1) != "なし":
        details["礼金"] = m.group(1)
    else:
        details["礼金"] = "なし"

    # 契約期間
    m = re.search(r"契約期間\s*\n?\s*(\d+年|定期借家)", text)
    if m:
        details["契約"] = m.group(1)

    # 引渡時期
    m = re.search(r"引渡可能\s*\n?\s*時\s*期\s*\n?\s*(\S+)", text)
    if m:
        details["入居日"] = m.group(1)

    # 設備
    m = re.search(r"設\s*備\s*\n?\s*(.+?)(?:\n備\s*考|\n$)", text, re.DOTALL)
    if m:
        equip = m.group(1).strip().replace("\n", ", ")
        if equip and equip != "-":
            remarks.append(f"設備: {equip}")

    # 備考テキスト
    m = re.search(r"備\s*考\s*\n(.+?)(?:\nこの図面|\ninfosheet)", text, re.DOTALL)
    if m:
        biko = " ".join(m.group(1).split())
        if len(biko) > 200:
            biko = biko[:200] + "..."
        remarks.append(biko)

    # チェックポイント
    m = re.search(r"チェックポイント！\s*\n(.+?)(?:\n物)", text, re.DOTALL)
    if m:
        cp = m.group(1).strip().replace("\n", ", ")
        remarks.append(f"特徴: {cp}")


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
    return jsonify({"error": "invalid", "message": "IDまたはパスワードが正しくありません"}), 401


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
    ws_dir = os.path.join(WORKSPACES_DIR, ws_id)
    os.makedirs(ws_dir, exist_ok=True)
    with open(os.path.join(ws_dir, "properties.json"), "w") as f:
        json.dump([], f)
    new_ws = {
        "id": ws_id,
        "name": data.get("name", "新規ワークスペース"),
        "stations": data.get("stations", []),
        "center": data.get("center", {"lat": 35.6812, "lon": 139.7671}),
        "zoom": data.get("zoom", 14),
    }
    ws_data = load_workspaces()
    ws_data["workspaces"].append(new_ws)
    save_workspaces(ws_data)
    return jsonify({"status": "ok", "workspace": new_ws})


@app.route("/api/workspaces/<ws_id>", methods=["PUT"])
def update_workspace(ws_id):
    updates = request.json
    ws_data = load_workspaces()
    for ws in ws_data["workspaces"]:
        if ws["id"] == ws_id:
            if "name" in updates: ws["name"] = updates["name"]
            if "stations" in updates: ws["stations"] = updates["stations"]
            if "center" in updates: ws["center"] = updates["center"]
            if "zoom" in updates: ws["zoom"] = updates["zoom"]
            save_workspaces(ws_data)
            return jsonify({"status": "ok"})
    return jsonify({"error": "not found"}), 404


@app.route("/api/workspaces/<ws_id>", methods=["DELETE"])
def delete_workspace(ws_id):
    ws_data = load_workspaces()
    if len(ws_data["workspaces"]) <= 1:
        return jsonify({"error": "最後のワークスペースは削除できません"}), 400
    ws_data["workspaces"] = [w for w in ws_data["workspaces"] if w["id"] != ws_id]
    if ws_data["activeWorkspace"] == ws_id:
        ws_data["activeWorkspace"] = ws_data["workspaces"][0]["id"]
    # Remove directory
    ws_dir = os.path.join(WORKSPACES_DIR, ws_id)
    if os.path.exists(ws_dir):
        shutil.rmtree(ws_dir)
    save_workspaces(ws_data)
    return jsonify({"status": "ok", "activeWorkspace": ws_data["activeWorkspace"]})


@app.route("/api/workspaces/active", methods=["PUT"])
def set_active_workspace():
    ws_id = request.json.get("id")
    ws_data = load_workspaces()
    if not any(w["id"] == ws_id for w in ws_data["workspaces"]):
        return jsonify({"error": "not found"}), 404
    ws_data["activeWorkspace"] = ws_id
    save_workspaces(ws_data)
    return jsonify({"status": "ok"})


# --- Property API (workspace-aware) ---

@app.route("/api/properties")
def get_properties():
    return jsonify(load_properties(get_active_ws_id()))


@app.route("/api/properties/<prop_id>/memo", methods=["PUT"])
def update_memo(prop_id):
    ws_id = get_active_ws_id()
    props = load_properties(ws_id)
    for p in props:
        if p["id"] == prop_id:
            p["memo"] = request.json.get("memo", "")
            save_properties(props, ws_id)
            return jsonify({"status": "ok"})
    return jsonify({"error": "not found"}), 404


@app.route("/api/properties/<prop_id>/color", methods=["PUT"])
def update_color(prop_id):
    ws_id = get_active_ws_id()
    color = request.json.get("color", "blue")
    if color not in ("blue", "red", "green"):
        color = "blue"
    props = load_properties(ws_id)
    for p in props:
        if p["id"] == prop_id:
            p["color"] = color
            save_properties(props, ws_id)
            return jsonify({"status": "ok"})
    return jsonify({"error": "not found"}), 404


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
    sync_file_to_github(filepath)  # PDFもGitHubに永続化
    info = extract_property_info(filepath)
    manual_address = request.form.get("address", "").strip()
    if manual_address:
        info["address"] = manual_address
    if not info["address"]:
        return jsonify({"error": "address_not_found", "extracted": info,
                        "filename": filename, "message": "住所を自動抽出できませんでした。"})
    lat, lon = geocode_address(info["address"])
    if lat is None:
        return jsonify({"error": "geocode_failed", "extracted": info,
                        "filename": filename, "message": "ジオコーディングに失敗しました。"})
    props = load_properties(ws_id)
    prop_id = f"prop_{int(time.time() * 1000)}"
    new_prop = {"id": prop_id, "name": info["name"], "address": info["address"],
                "lat": lat, "lon": lon, "filename": filename,
                "details": info["details"], "memo": ""}
    props.append(new_prop)
    save_properties(props, ws_id)
    return jsonify({"status": "ok", "property": new_prop})


@app.route("/api/properties/manual", methods=["POST"])
def add_property_manual():
    ws_id = get_active_ws_id()
    data = request.json
    name = data.get("name", "").strip()
    address = data.get("address", "").strip()
    details = data.get("details", {})
    if not name or not address:
        return jsonify({"error": "missing_fields", "message": "物件名と住所は必須です"}), 400
    lat, lon = geocode_address(address)
    if lat is None:
        return jsonify({"error": "geocode_failed", "message": "住所からの位置特定に失敗しました。住所を確認してください。"})
    props = load_properties(ws_id)
    prop_id = f"prop_{int(time.time() * 1000)}"
    new_prop = {"id": prop_id, "name": name, "address": address,
                "lat": lat, "lon": lon, "filename": "",
                "details": details, "memo": ""}
    props.append(new_prop)
    save_properties(props, ws_id)
    return jsonify({"status": "ok", "property": new_prop})


@app.route("/api/properties/<prop_id>/details", methods=["PUT"])
def update_details(prop_id):
    ws_id = get_active_ws_id()
    details = request.json.get("details", {})
    props = load_properties(ws_id)
    for p in props:
        if p["id"] == prop_id:
            p["details"] = details
            save_properties(props, ws_id)
            return jsonify({"status": "ok"})
    return jsonify({"error": "not found"}), 404


@app.route("/api/properties/<prop_id>", methods=["DELETE"])
def delete_property(prop_id):
    ws_id = get_active_ws_id()
    props = [p for p in load_properties(ws_id) if p["id"] != prop_id]
    save_properties(props, ws_id)
    return jsonify({"status": "ok"})


@app.route("/api/properties/<prop_id>/move", methods=["PUT"])
def move_property(prop_id):
    """物件を別のワークスペースに移動."""
    ws_id = get_active_ws_id()
    target_ws_id = request.json.get("targetWs")
    if not target_ws_id:
        return jsonify({"error": "targetWs required"}), 400
    # Find and remove from source
    src_props = load_properties(ws_id)
    prop = None
    remaining = []
    for p in src_props:
        if p["id"] == prop_id:
            prop = p
        else:
            remaining.append(p)
    if not prop:
        return jsonify({"error": "not found"}), 404
    save_properties(remaining, ws_id)
    # Add to target
    dst_props = load_properties(target_ws_id)
    dst_props.append(prop)
    save_properties(dst_props, target_ws_id)
    return jsonify({"status": "ok"})


# --- Station geocoding ---

# Major terminal stations get larger radius
MAJOR_STATIONS = {"渋谷", "新宿", "池袋", "東京", "品川", "上野", "横浜", "大宮", "千葉", "立川", "町田", "吉祥寺", "北千住", "大手町", "秋葉原"}

@app.route("/api/geocode-station")
def geocode_station():
    """駅名 → 緯度経度を自動取得 (Nominatim)."""
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    # Ensure it ends with 駅
    search_name = name if name.endswith("駅") else name + "駅"
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
                # Auto radius based on station size
                base_name = search_name.replace("駅", "")
                radius = 180 if base_name in MAJOR_STATIONS else 120
                return jsonify({"status": "ok", "lat": lat, "lon": lon, "r": radius, "name": search_name})
    except Exception as e:
        print(f"Station geocoding failed: {e}")
    return jsonify({"error": "not_found", "message": f"「{search_name}」が見つかりませんでした"})


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

_agents_cache = None
_agents_mtime = 0


def load_agents():
    global _agents_cache, _agents_mtime
    if not os.path.exists(AGENTS_FILE):
        return []
    mtime = os.path.getmtime(AGENTS_FILE)
    if _agents_cache is not None and mtime == _agents_mtime:
        return _agents_cache
    with open(AGENTS_FILE, "r", encoding="utf-8") as f:
        _agents_cache = json.load(f)
    _agents_mtime = mtime
    return _agents_cache


def save_agents(agents):
    global _agents_cache, _agents_mtime
    with open(AGENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(agents, f, ensure_ascii=False, indent=2)
    _agents_cache = agents
    _agents_mtime = os.path.getmtime(AGENTS_FILE)
    sync_file_to_github(AGENTS_FILE)
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
        return jsonify({"error": "missing_fields", "message": "名前とメールアドレスは必須です"}), 400
    agents = load_agents()
    agent = {
        "id": f"agent_{int(time.time() * 1000)}",
        "name": name,
        "email": email,
        "phone": data.get("phone", "").strip(),
        "area": data.get("area", ""),
        "memo": data.get("memo", "").strip(),
    }
    agents.append(agent)
    save_agents(agents)
    return jsonify({"status": "ok", "agent": agent})


@app.route("/api/agents/<agent_id>", methods=["PUT"])
def update_agent(agent_id):
    data = request.json
    agents = load_agents()
    for a in agents:
        if a["id"] == agent_id:
            for key in ["name", "email", "phone", "area", "memo"]:
                if key in data:
                    a[key] = data[key].strip() if isinstance(data[key], str) else data[key]
            save_agents(agents)
            return jsonify({"status": "ok", "agent": a})
    return jsonify({"error": "not found"}), 404


@app.route("/api/agents/<agent_id>", methods=["DELETE"])
def delete_agent(agent_id):
    agents = [a for a in load_agents() if a["id"] != agent_id]
    save_agents(agents)
    return jsonify({"status": "ok"})


@app.route("/api/agents/<agent_id>/properties")
def get_agent_properties(agent_id):
    agents = load_agents()
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        return jsonify({"error": "not found"}), 404
    area = agent.get("area", "")
    ws_ids = [x.strip() for x in area.split(",") if x.strip()] if area else []
    all_props = []
    for ws_id in ws_ids:
        props = load_properties(ws_id)
        ws_data = load_workspaces()
        ws_name = next((w["name"] for w in ws_data["workspaces"] if w["id"] == ws_id), ws_id)
        for p in props:
            p["_wsName"] = ws_name
        all_props.extend(props)
    return jsonify(all_props)


# ===================== Schedules =====================

_schedules_cache = None
_schedules_mtime = 0


def load_schedules():
    global _schedules_cache, _schedules_mtime
    if not os.path.exists(SCHEDULES_FILE):
        return []
    mtime = os.path.getmtime(SCHEDULES_FILE)
    if _schedules_cache is not None and mtime == _schedules_mtime:
        return _schedules_cache
    with open(SCHEDULES_FILE, "r", encoding="utf-8") as f:
        _schedules_cache = json.load(f)
    _schedules_mtime = mtime
    return _schedules_cache


def save_schedules(schedules):
    global _schedules_cache, _schedules_mtime
    with open(SCHEDULES_FILE, "w", encoding="utf-8") as f:
        json.dump(schedules, f, ensure_ascii=False, indent=2)
    _schedules_cache = schedules
    _schedules_mtime = os.path.getmtime(SCHEDULES_FILE)
    sync_file_to_github(SCHEDULES_FILE)
    bump_change()


@app.route("/api/schedules")
def get_schedules():
    month = request.args.get("month", "")
    schedules = load_schedules()
    if month:
        schedules = [s for s in schedules if s["date"].startswith(month)]
    return jsonify(schedules)


@app.route("/api/schedules", methods=["POST"])
def create_schedule():
    data = request.json
    title = data.get("title", "").strip()
    date = data.get("date", "").strip()
    if not title or not date:
        return jsonify({"error": "missing_fields", "message": "タイトルと日付は必須です"}), 400
    schedules = load_schedules()
    sch = {
        "id": f"sch_{int(time.time() * 1000)}",
        "title": title,
        "agentId": data.get("agentId", ""),
        "propertyId": data.get("propertyId", ""),
        "type": data.get("type", "その他"),
        "date": date,
        "startTime": data.get("startTime", "10:00"),
        "endTime": data.get("endTime", "11:00"),
        "memo": data.get("memo", ""),
    }
    schedules.append(sch)
    save_schedules(schedules)
    return jsonify({"status": "ok", "schedule": sch})


@app.route("/api/schedules/<sch_id>", methods=["PUT"])
def update_schedule(sch_id):
    data = request.json
    schedules = load_schedules()
    for s in schedules:
        if s["id"] == sch_id:
            for key in ["title", "agentId", "propertyId", "type", "date", "startTime", "endTime", "memo"]:
                if key in data:
                    s[key] = data[key].strip() if isinstance(data[key], str) else data[key]
            save_schedules(schedules)
            return jsonify({"status": "ok", "schedule": s})
    return jsonify({"error": "not found"}), 404


@app.route("/api/schedules/<sch_id>", methods=["DELETE"])
def delete_schedule(sch_id):
    schedules = [s for s in load_schedules() if s["id"] != sch_id]
    save_schedules(schedules)
    return jsonify({"status": "ok"})


# ===================== Main =====================

if __name__ == "__main__":
    import argparse
    import subprocess
    import threading

    parser = argparse.ArgumentParser(description="物件マップサーバー")
    parser.add_argument("--public", action="store_true")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    if args.public:
        def start_tunnel():
            import sys
            print("\n  トンネル接続中...", flush=True)
            # Cloudflare Tunnel (確認ページなし・直接アクセス可能)
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
                           f"  外部公開URL: {urls[0]}\n"
                           f"  このURLをコピーして共有してください\n"
                           f"  確認ページなし・誰でも即アクセス可能\n"
                           f"{'='*60}\n")
                    sys.stdout.write(msg); sys.stdout.flush(); break
        threading.Thread(target=start_tunnel, daemon=True).start()

    host = "0.0.0.0" if args.public else "127.0.0.1"
    app.run(host=host, port=args.port, debug=not args.public)
