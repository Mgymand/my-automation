import os
import json
import re
import ssl
import urllib.request
import urllib.parse
import time
from flask import Flask, render_template, request, jsonify, send_from_directory

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PDF_DIR = os.path.join(DATA_DIR, "pdfs")
PROPERTIES_FILE = os.path.join(DATA_DIR, "properties.json")

os.makedirs(PDF_DIR, exist_ok=True)

# SSL context for geocoding
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# In-memory cache to avoid repeated disk reads
_properties_cache = None
_properties_mtime = 0


def load_properties():
    """Load properties with file-mtime caching."""
    global _properties_cache, _properties_mtime
    if not os.path.exists(PROPERTIES_FILE):
        return []
    mtime = os.path.getmtime(PROPERTIES_FILE)
    if _properties_cache is not None and mtime == _properties_mtime:
        return _properties_cache
    with open(PROPERTIES_FILE, "r", encoding="utf-8") as f:
        _properties_cache = json.load(f)
    _properties_mtime = mtime
    return _properties_cache


def save_properties(props):
    global _properties_cache, _properties_mtime
    with open(PROPERTIES_FILE, "w", encoding="utf-8") as f:
        json.dump(props, f, ensure_ascii=False, indent=2)
    _properties_cache = props
    _properties_mtime = os.path.getmtime(PROPERTIES_FILE)


def normalize_address(address):
    """Convert 渋谷区渋谷3-1-6 style to 渋谷区渋谷三丁目1-6 for GSI API."""
    import unicodedata
    # Normalize fullwidth digits to halfwidth
    address = unicodedata.normalize("NFKC", address)
    # Convert X-Y-Z pattern to X丁目Y-Z (Japanese address convention)
    chome_map = {"1": "一", "2": "二", "3": "三", "4": "四", "5": "五",
                 "6": "六", "7": "七", "8": "八", "9": "九", "10": "十"}
    import re as _re
    def replace_chome(m):
        chome = chome_map.get(m.group(1), m.group(1))
        return f"{chome}丁目{m.group(2)}-{m.group(3)}"
    address = _re.sub(r"(\d+)-(\d+)-(\d+)", replace_chome, address)
    return address


def geocode_address(address):
    """国土地理院 Geocoding API (番地レベル対応)."""
    normalized = normalize_address(address)
    query = urllib.parse.urlencode({"q": normalized})
    url = f"https://msearch.gsi.go.jp/address-search/AddressSearch?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "PropertyMapApp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data:
                coords = data[0]["geometry"]["coordinates"]
                return float(coords[1]), float(coords[0])  # [lon, lat] -> (lat, lon)
    except Exception as e:
        print(f"Geocoding failed for {address}: {e}")
    return None, None


def extract_property_info(pdf_path):
    """Extract property info from PDF using PyMuPDF (lazy import)."""
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
        (r"賃料\s*(\S+)", "賃料"),
        (r"([\d.]+)\s*坪", "面積"),
        (r"構造\s*[:：]\s*(\S+)", "構造"),
        (r"竣工\s*[:：]\s*(\S+)", "竣工"),
    ]:
        m = re.search(pattern, text)
        if m:
            val = m.group(1)
            if key == "面積":
                val += " 坪"
            info["details"][key] = val

    station_matches = re.findall(
        r"((?:JR|東京メトロ|東急)[^\n]+\n\S+\n\d+分)", text
    )
    if station_matches:
        info["details"]["交通"] = "; ".join(
            " ".join(m.split()) for m in station_matches[:3]
        )
    return info


# --- Routes ---

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/properties")
def get_properties():
    return jsonify(load_properties())


@app.route("/api/properties/<prop_id>/memo", methods=["PUT"])
def update_memo(prop_id):
    props = load_properties()
    for p in props:
        if p["id"] == prop_id:
            p["memo"] = request.json.get("memo", "")
            save_properties(props)
            return jsonify({"status": "ok"})
    return jsonify({"error": "not found"}), 404


@app.route("/api/properties/<prop_id>/color", methods=["PUT"])
def update_color(prop_id):
    color = request.json.get("color", "blue")
    if color not in ("blue", "red", "green"):
        color = "blue"
    props = load_properties()
    for p in props:
        if p["id"] == prop_id:
            p["color"] = color
            save_properties(props)
            return jsonify({"status": "ok"})
    return jsonify({"error": "not found"}), 404


@app.route("/api/upload", methods=["POST"])
def upload_pdf():
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
        return jsonify({
            "error": "address_not_found",
            "extracted": info,
            "filename": filename,
            "message": "住所を自動抽出できませんでした。手動で入力してください。"
        })

    lat, lon = geocode_address(info["address"])
    if lat is None:
        return jsonify({
            "error": "geocode_failed",
            "extracted": info,
            "filename": filename,
            "message": "ジオコーディングに失敗しました。住所を確認してください。"
        })

    props = load_properties()
    prop_id = f"prop_{int(time.time() * 1000)}"
    new_prop = {
        "id": prop_id,
        "name": info["name"],
        "address": info["address"],
        "lat": lat,
        "lon": lon,
        "filename": filename,
        "details": info["details"],
        "memo": "",
    }
    props.append(new_prop)
    save_properties(props)
    return jsonify({"status": "ok", "property": new_prop})


@app.route("/api/properties/<prop_id>/details", methods=["PUT"])
def update_details(prop_id):
    details = request.json.get("details", {})
    props = load_properties()
    for p in props:
        if p["id"] == prop_id:
            p["details"] = details
            save_properties(props)
            return jsonify({"status": "ok"})
    return jsonify({"error": "not found"}), 404


@app.route("/api/properties/<prop_id>", methods=["DELETE"])
def delete_property(prop_id):
    props = [p for p in load_properties() if p["id"] != prop_id]
    save_properties(props)
    return jsonify({"status": "ok"})


@app.route("/pdf/<path:filename>")
def serve_pdf(filename):
    resp = send_from_directory(PDF_DIR, filename, mimetype="application/pdf")
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


if __name__ == "__main__":
    app.run(debug=True, port=5000)
