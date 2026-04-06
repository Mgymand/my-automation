import os
import json
import re
import ssl
import urllib.request
import urllib.parse
import time
from flask import Flask, render_template, request, jsonify, send_from_directory
import fitz  # PyMuPDF

# SSL context for geocoding
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PDF_DIR = os.path.join(DATA_DIR, "pdfs")
PROPERTIES_FILE = os.path.join(DATA_DIR, "properties.json")

os.makedirs(PDF_DIR, exist_ok=True)


def load_properties():
    if os.path.exists(PROPERTIES_FILE):
        with open(PROPERTIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_properties(properties):
    with open(PROPERTIES_FILE, "w", encoding="utf-8") as f:
        json.dump(properties, f, ensure_ascii=False, indent=2)


def geocode_address(address):
    """Nominatim geocoding (free, no API key)."""
    query = urllib.parse.urlencode({"q": address, "format": "json", "limit": 1})
    url = f"https://nominatim.openstreetmap.org/search?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "PropertyMapApp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10, context=SSL_CTX) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print(f"Geocoding failed for {address}: {e}")
    return None, None


def extract_property_info(pdf_path):
    """Extract property info from PDF using PyMuPDF."""
    doc = fitz.open(pdf_path)
    text = doc[0].get_text()
    doc.close()

    info = {"name": "", "address": "", "details": {}}

    # Extract building name (first line usually)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if lines:
        info["name"] = lines[0]

    # Extract address
    addr_match = re.search(r"所在地\s*[:：]\s*(.+)", text)
    if addr_match:
        info["address"] = addr_match.group(1).strip()
    else:
        # Fallback: look for 東京都 pattern
        addr_match = re.search(r"(東京都[^\n]+)", text)
        if addr_match:
            info["address"] = addr_match.group(1).strip()

    # Extract rent
    rent_match = re.search(r"賃料\s*(\S+)", text)
    if rent_match:
        info["details"]["賃料"] = rent_match.group(1)

    # Extract area
    area_match = re.search(r"([\d.]+)\s*坪", text)
    if area_match:
        info["details"]["面積"] = area_match.group(1) + " 坪"

    # Extract structure
    struct_match = re.search(r"構造\s*[:：]\s*(\S+)", text)
    if struct_match:
        info["details"]["構造"] = struct_match.group(1)

    # Extract year
    year_match = re.search(r"竣工\s*[:：]\s*(\S+)", text)
    if year_match:
        info["details"]["竣工"] = year_match.group(1)

    # Extract station access
    station_matches = re.findall(r"((?:JR|東京メトロ|東急)[^\n]+\n\S+\n\d+分)", text)
    if station_matches:
        info["details"]["交通"] = "; ".join(
            " ".join(m.split()) for m in station_matches[:3]
        )

    # Extract floor
    floor_match = re.search(r"階数\s*\n?\s*(\S+)", text)
    if floor_match:
        info["details"]["階数"] = floor_match.group(1)

    return info


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/properties", methods=["GET"])
def get_properties():
    return jsonify(load_properties())


@app.route("/api/properties/<prop_id>/memo", methods=["PUT"])
def update_memo(prop_id):
    properties = load_properties()
    for prop in properties:
        if prop["id"] == prop_id:
            prop["memo"] = request.json.get("memo", "")
            save_properties(properties)
            return jsonify({"status": "ok"})
    return jsonify({"error": "not found"}), 404


@app.route("/api/upload", methods=["POST"])
def upload_pdf():
    if "pdf" not in request.files:
        return jsonify({"error": "no file"}), 400

    file = request.files["pdf"]
    if not file.filename.endswith(".pdf"):
        return jsonify({"error": "not a PDF"}), 400

    # Save file
    filename = file.filename
    filepath = os.path.join(PDF_DIR, filename)
    file.save(filepath)

    # Extract info
    info = extract_property_info(filepath)

    # If address provided manually, use it
    manual_address = request.form.get("address", "").strip()
    if manual_address:
        info["address"] = manual_address

    if not info["address"]:
        return jsonify({
            "error": "address_not_found",
            "extracted": info,
            "filename": filename,
            "message": "住所を自動抽出できませんでした。手動で入力してください。"
        }), 200

    # Geocode
    lat, lon = geocode_address(info["address"])
    if lat is None:
        return jsonify({
            "error": "geocode_failed",
            "extracted": info,
            "filename": filename,
            "message": "住所のジオコーディングに失敗しました。住所を確認してください。"
        }), 200

    # Create property
    properties = load_properties()
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
    properties.append(new_prop)
    save_properties(properties)

    return jsonify({"status": "ok", "property": new_prop})


@app.route("/api/properties/<prop_id>", methods=["DELETE"])
def delete_property(prop_id):
    properties = load_properties()
    properties = [p for p in properties if p["id"] != prop_id]
    save_properties(properties)
    return jsonify({"status": "ok"})


@app.route("/pdf/<path:filename>")
def serve_pdf(filename):
    return send_from_directory(
        PDF_DIR, filename, mimetype="application/pdf"
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
