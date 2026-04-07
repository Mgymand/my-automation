import os
import json
import re
import ssl
import urllib.request
import urllib.parse
import time
import shutil
from flask import Flask, render_template, request, jsonify, send_from_directory

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PDF_DIR = os.path.join(DATA_DIR, "pdfs")
WORKSPACES_FILE = os.path.join(DATA_DIR, "workspaces.json")
WORKSPACES_DIR = os.path.join(DATA_DIR, "workspaces")
OLD_PROPERTIES_FILE = os.path.join(DATA_DIR, "properties.json")

os.makedirs(PDF_DIR, exist_ok=True)
os.makedirs(WORKSPACES_DIR, exist_ok=True)

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

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


# --- Address / PDF helpers ---

def normalize_address(address):
    import unicodedata
    address = unicodedata.normalize("NFKC", address)
    chome_map = {"1": "一", "2": "二", "3": "三", "4": "四", "5": "五",
                 "6": "六", "7": "七", "8": "八", "9": "九", "10": "十"}
    def replace_chome(m):
        chome = chome_map.get(m.group(1), m.group(1))
        return f"{chome}丁目{m.group(2)}-{m.group(3)}"
    address = re.sub(r"(\d+)-(\d+)-(\d+)", replace_chome, address)
    return address


def geocode_address(address):
    normalized = normalize_address(address)
    query = urllib.parse.urlencode({"q": normalized})
    url = f"https://msearch.gsi.go.jp/address-search/AddressSearch?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "PropertyMapApp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data:
                coords = data[0]["geometry"]["coordinates"]
                return float(coords[1]), float(coords[0])
    except Exception as e:
        print(f"Geocoding failed for {address}: {e}")
    return None, None


def extract_property_info(pdf_path):
    import fitz
    doc = fitz.open(pdf_path)
    text = doc[0].get_text()
    doc.close()
    info = {"name": "", "address": "", "details": {}}
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if lines:
        info["name"] = lines[0]
    addr_match = re.search(r"所在地\s*[:：]\s*(.+)", text)
    if addr_match:
        info["address"] = addr_match.group(1).strip()
    else:
        addr_match = re.search(r"(東京都[^\n]+)", text)
        if addr_match:
            info["address"] = addr_match.group(1).strip()
    for pattern, key in [
        (r"賃料\s*(\S+)", "賃料"), (r"([\d.]+)\s*坪", "面積"),
        (r"構造\s*[:：]\s*(\S+)", "構造"), (r"竣工\s*[:：]\s*(\S+)", "竣工"),
    ]:
        m = re.search(pattern, text)
        if m:
            val = m.group(1)
            if key == "面積": val += " 坪"
            info["details"][key] = val
    station_matches = re.findall(r"((?:JR|東京メトロ|東急)[^\n]+\n\S+\n\d+分)", text)
    if station_matches:
        info["details"]["交通"] = "; ".join(" ".join(m.split()) for m in station_matches[:3])
    return info


# ===================== Routes =====================

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
