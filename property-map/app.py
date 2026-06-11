import os
import json
import re
import ssl
import urllib.request
import urllib.parse
import time
import uuid
from flask import (Flask, render_template, request, jsonify,
                   send_from_directory, Response, redirect, session)

def _load_dotenv(path):
    """依存なしの簡易.envローダー。

    このアプリでは .env を秘密情報の正とみなし、シェル由来の環境変数より優先する
    （~/.zshrc 等に残った古いダミーキーが勝ってしまう事故を防ぐ）。
    """
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and val:
                os.environ[key] = val


_load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


def _ensure_secret_key(env_path):
    """セッション署名キー。なければ生成して.envに永続化（再起動でセッションが切れないように）。"""
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    import secrets
    key = secrets.token_hex(32)
    with open(env_path, "a", encoding="utf-8") as f:
        f.write(f"\nSECRET_KEY={key}\n")
    os.environ["SECRET_KEY"] = key
    return key


app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# データ置き場。本番では永続ディスク（例: /var/data）を PROPERTY_DATA_DIR で指定する
DATA_DIR = os.environ.get("PROPERTY_DATA_DIR") or os.path.join(BASE_DIR, "data")
app.secret_key = _ensure_secret_key(os.path.join(BASE_DIR, ".env"))
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 14  # 14日

# 本番（リバースプロキシ配下）: https判定とSecure cookieを有効化
if os.environ.get("RENDER") or os.environ.get("TRUST_PROXY"):
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config["SESSION_COOKIE_SECURE"] = True

import auth  # noqa: E402  (認証・権限レイヤ)
PDF_DIR = os.path.join(DATA_DIR, "pdfs")
PROPERTIES_FILE = os.path.join(DATA_DIR, "properties.json")

# --- マイソク結合ツール用 ---
COMPILE_DIR = os.path.join(DATA_DIR, "compile")
COMPILE_UPLOAD_DIR = os.path.join(COMPILE_DIR, "uploads")
COMPILE_TEMPLATES_FILE = os.path.join(COMPILE_DIR, "templates.json")

# --- 構造化抽出 (Phase1: OCR→構造化パイプライン) ---
EXTRACT_IMG_DIR = os.path.join(DATA_DIR, "extracted_images")

# --- マッチング・一斉提案 (Phase1) ---
CUSTOMERS_FILE = os.path.join(DATA_DIR, "customers.json")
PROPOSALS_FILE = os.path.join(DATA_DIR, "proposals.json")

# --- 物件DB（マイデータ/共有データ・公開範囲）(Phase1.5) ---
BUKKEN_FILE = os.path.join(DATA_DIR, "bukken.json")

# --- 顧客マイページ・閲覧ログ (Phase2) ---
MYPAGE_FILE = os.path.join(DATA_DIR, "mypage.json")
ACTIVITY_FILE = os.path.join(DATA_DIR, "activity.json")

# --- 成約登録・チャット (Phase3) ---
DEALS_FILE = os.path.join(DATA_DIR, "deals.json")
MESSAGES_FILE = os.path.join(DATA_DIR, "messages.json")

os.makedirs(PDF_DIR, exist_ok=True)
os.makedirs(COMPILE_UPLOAD_DIR, exist_ok=True)
os.makedirs(EXTRACT_IMG_DIR, exist_ok=True)


def _bootstrap_admin():
    """初回起動（空のデータディスク）時に初期オーガナイザーと本部店舗を作成する。

    本番デプロイ直後でも ADMIN_EMAIL 環境変数のアカウントでログインできるようにする。
    既にユーザーが1人でもいれば何もしない。
    """
    admin = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    if not admin or auth.load_users():
        return
    if not auth.load_stores():
        auth.save_stores([{"id": "hq", "name": "本部",
                           "created_at": time.strftime("%Y-%m-%d")}])
    auth.save_users([{"email": admin, "name": "オーガナイザー",
                      "role": "ogn", "store_id": "hq", "active": True}])
    print(f"[bootstrap] 初期オーガナイザーを作成しました: {admin}")


_bootstrap_admin()

# 旧ツール（物件マップ・マイソク結合）も本番公開時はログイン必須にする。
# /extracted-images は顧客マイページの物件写真で使うため対象外。
_GATED_PAGES = ("/", "/compile")
_GATED_PREFIXES = ("/api/properties", "/api/upload", "/api/compile", "/pdf/", "/pdf-images/")


@app.before_request
def _require_login_for_legacy_tools():
    p = request.path
    if p not in _GATED_PAGES and not p.startswith(_GATED_PREFIXES):
        return None
    if auth.current_user():
        return None
    if p.startswith("/api/"):
        return jsonify({"error": "login required"}), 401
    return redirect(f"/login?next={urllib.parse.quote(p)}")


def load_customers():
    if not os.path.exists(CUSTOMERS_FILE):
        return []
    with open(CUSTOMERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_proposals():
    if not os.path.exists(PROPOSALS_FILE):
        return []
    with open(PROPOSALS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_proposals(items):
    with open(PROPOSALS_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def property_key(prop):
    """提案重複判定用の物件キー。物件番号優先、なければ建物名+住所。"""
    return prop.get("property_number") or f"{prop.get('building_name','')}|{prop.get('address','')}"

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


@app.route("/api/extract", methods=["POST"])
@auth.require_role("store")
def extract_structured():
    """PDFをアップロードし、構造化レコード（複数物件対応）＋画像＋緯度経度を返す。

    Phase1パイプライン: テキスト/画像抽出 → LLM(or ヒューリスティック)構造化 → ジオコーディング。
    既存の /api/upload（地図ピン登録）とは独立。こちらは抽出結果の確認・取込用。
    """
    import extractor

    if "pdf" not in request.files:
        return jsonify({"error": "no file"}), 400
    file = request.files["pdf"]
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "not a PDF"}), 400

    safe = re.sub(r"[^\w\.\-]+", "_", file.filename)
    filepath = os.path.join(PDF_DIR, safe)
    file.save(filepath)

    records = extractor.process(filepath, image_dir=EXTRACT_IMG_DIR)

    for rec in records:
        rec["_images"] = [os.path.basename(p) for p in rec.get("_images", [])]
        if rec.get("address"):
            lat, lon = geocode_address(rec["address"])
            rec["lat"], rec["lon"] = lat, lon
        else:
            rec["lat"], rec["lon"] = None, None

    return jsonify({
        "filename": file.filename,
        "count": len(records),
        "mode": "LLM" if os.environ.get("ANTHROPIC_API_KEY") else "heuristic",
        "properties": records,
    })


@app.route("/extracted-images/<path:filename>")
def serve_extracted_image(filename):
    resp = send_from_directory(EXTRACT_IMG_DIR, filename)
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@app.route("/api/customers")
@auth.require_role("store")
def get_customers():
    return jsonify(_scoped_customers(request.args.get("store_id")))


@app.route("/api/customers", methods=["POST"])
@auth.require_role("store")
def add_customer():
    """顧客登録。加盟店は自店の顧客として登録される。"""
    user = auth.current_user()
    body = request.json or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "顧客名が必要です"}), 400
    customers = load_customers()
    store_id = body.get("store_id") if user["role"] in ("admin", "ogn") else None
    rec = {
        "id": f"cust_{uuid.uuid4().hex[:8]}",
        "name": name,
        "contact": body.get("contact") or "",
        "email": body.get("email") or "",
        "tags": body.get("tags") or [],
        "criteria": body.get("criteria") or {},
        "note": body.get("note") or "",
        "store_id": store_id or user.get("store_id"),
    }
    customers.append(rec)
    with open(CUSTOMERS_FILE, "w", encoding="utf-8") as f:
        json.dump(customers, f, ensure_ascii=False, indent=2)
    return jsonify({"ok": True, "customer": rec})


def _scoped_customers(requested_store=None):
    """セッションのロールに応じて顧客を絞り込む（加盟店=自店のみ）。"""
    sid = auth.scope_store_id(requested_store)
    customers = load_customers()
    if sid:
        customers = [c for c in customers if c.get("store_id") == sid]
    return customers


@app.route("/api/match", methods=["POST"])
@auth.require_role("store")
def match_property():
    """物件レコードに対し、提案候補の顧客をスコア順で返す。

    Body: {"property": {<構造化済み物件レコード>}, "min_score": 40}
    提案済みの顧客には already_proposed フラグを付与（提案漏れ/重複の判断材料）。
    顧客はログインユーザーの店舗スコープ内のみ。
    """
    import matching

    body = request.json or {}
    prop = body.get("property") or {}
    min_score = float(body.get("min_score", 40))
    if not prop:
        return jsonify({"error": "property required"}), 400

    key = property_key(prop)
    proposed_ids = {p["customer_id"] for p in load_proposals() if p.get("property_key") == key}
    customers = _scoped_customers(body.get("store_id"))
    ranked = matching.rank_customers(prop, customers, proposed_ids, min_score)
    return jsonify({"property_key": key, "candidates": ranked})


@app.route("/api/propose", methods=["POST"])
@auth.require_role("store")
def propose():
    """選択顧客へ一斉提案。提案文面を生成し、履歴に記録（提案漏れ防止）。

    Body: {"property": {...}, "customer_ids": ["cust_001", ...]}
    提案できる顧客はログインユーザーの店舗スコープ内のみ（改ざん防止）。
    """
    import matching

    body = request.json or {}
    prop = body.get("property") or {}
    customer_ids = body.get("customer_ids") or []
    if not prop or not customer_ids:
        return jsonify({"error": "property and customer_ids required"}), 400

    customers = {c["id"]: c for c in _scoped_customers(body.get("store_id"))}
    key = property_key(prop)
    proposals = load_proposals()
    already = {p["customer_id"] for p in proposals if p.get("property_key") == key}

    results = []
    for cid in customer_ids:
        cust = customers.get(cid)
        if not cust:
            continue
        if cid in already:
            results.append({"customer_id": cid, "status": "skipped_already_proposed"})
            continue
        text = matching.generate_proposal_text(prop, cust)
        me = auth.current_user() or {}
        record = {
            "id": f"prop_{int(time.time() * 1000)}_{cid}",
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "property_key": key,
            "property_name": f"{prop.get('building_name','')} {prop.get('room','')}".strip(),
            "customer_id": cid,
            "customer_name": cust.get("name", ""),
            "store_id": me.get("store_id"),
            "user_email": me.get("email"),
            "user_name": me.get("name"),
            "text": text,
            # マイページ掲載用スナップショット（Phase2）
            "prop": prop,
            "images": body.get("images") or [],
        }
        proposals.append(record)
        results.append({"customer_id": cid, "status": "proposed",
                        "customer_name": cust.get("name", ""), "text": text})

    save_proposals(proposals)
    proposed_now = sum(1 for r in results if r["status"] == "proposed")
    return jsonify({"property_key": key, "proposed": proposed_now, "results": results})


@app.route("/api/proposals")
@auth.require_role("store")
def get_proposals():
    """提案履歴（店舗スコープ）。物件キーで絞り込み可（?property_key=...）。"""
    items = load_proposals()
    sid = auth.scope_store_id(request.args.get("store_id"))
    if sid:
        items = [p for p in items if p.get("store_id") == sid]
    key = request.args.get("property_key")
    if key:
        items = [p for p in items if p.get("property_key") == key]
    return jsonify(items)


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


@app.route("/pdf-images/<path:filename>")
def serve_pdf_as_images(filename):
    """PDFの各ページをPNG画像に変換して返す（スマホ対応）."""
    import fitz
    from flask import Response
    import io

    filepath = os.path.join(PDF_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "not found"}), 404

    page_num = request.args.get("page", 0, type=int)

    doc = fitz.open(filepath)
    if page_num >= len(doc):
        doc.close()
        return jsonify({"error": "page not found"}), 404

    page = doc[page_num]
    # 2x zoom for readability
    mat = fitz.Matrix(2.0, 2.0)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    total_pages = len(doc)
    doc.close()

    resp = Response(img_bytes, mimetype="image/png")
    resp.headers["Cache-Control"] = "public, max-age=86400"
    resp.headers["X-Total-Pages"] = str(total_pages)
    return resp


# =============================================================
# マイソク結合ツール
# =============================================================

def _load_compile_templates():
    if not os.path.exists(COMPILE_TEMPLATES_FILE):
        # Bootstrap with a sensible default for at-home format
        # Rectangles in normalized coords (0-1 relative to page width/height)
        defaults = {
            "at-home (デフォルト)": {
                "name": "at-home (デフォルト)",
                "description": "at-home フォーマットの管理会社・宅建免許番号の領域",
                "rects": [
                    # bottom band: from ~85% down to bottom edge, full width
                    {"x": 0.0, "y": 0.86, "w": 1.0, "h": 0.14}
                ],
            }
        }
        with open(COMPILE_TEMPLATES_FILE, "w", encoding="utf-8") as f:
            json.dump(defaults, f, ensure_ascii=False, indent=2)
        return defaults
    with open(COMPILE_TEMPLATES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_compile_templates(t):
    with open(COMPILE_TEMPLATES_FILE, "w", encoding="utf-8") as f:
        json.dump(t, f, ensure_ascii=False, indent=2)


@app.route("/compile")
def compile_page():
    return render_template("compile.html")


@app.route("/propose")
@auth.require_role("store")
def propose_page():
    return render_template("propose.html", user=auth.current_user())


# ===========================================================================
# 認証 (Phase1.5): Googleログイン + 開発用ログイン
# ===========================================================================

@app.route("/login")
def login_page():
    user = auth.current_user()
    if user:
        return redirect(auth.ROLE_HOME.get(user["role"], "/portal"))
    dev_users = [] if auth.google_enabled() else [
        {"email": u["email"], "name": u.get("name", ""), "role": u.get("role", "store")}
        for u in auth.load_users() if u.get("active", True)
    ]
    return render_template("login.html",
                           google_client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
                           dev_users=dev_users)


@app.route("/api/login/google", methods=["POST"])
def login_google():
    credential = (request.json or {}).get("credential", "")
    try:
        info = auth.verify_google_token(credential)
    except ValueError as e:
        return jsonify({"error": f"Google認証に失敗しました: {e}"}), 401
    user = auth.find_user(info["email"])
    if not user:
        return jsonify({"error": f"{info['email']} は未登録です。オーガナイザーに招待を依頼してください。"}), 403
    auth.login_user(user)
    session.permanent = True
    return jsonify({"ok": True, "home": auth.ROLE_HOME[user["role"]]})


@app.route("/api/login/dev", methods=["POST"])
def login_dev():
    """開発用ログイン。GOOGLE_CLIENT_ID 設定後は自動的に無効化される。"""
    if auth.google_enabled():
        return jsonify({"error": "Googleログインが有効なため開発用ログインは使えません"}), 403
    email = (request.json or {}).get("email", "")
    user = auth.find_user(email)
    if not user:
        return jsonify({"error": "未登録ユーザーです"}), 403
    auth.login_user(user)
    session.permanent = True
    return jsonify({"ok": True, "home": auth.ROLE_HOME[user["role"]]})


@app.route("/logout")
def logout():
    auth.logout_user()
    return redirect("/login")


@app.route("/api/me")
def api_me():
    user = auth.current_user()
    if not user:
        return jsonify({"error": "not logged in"}), 401
    stores = {s["id"]: s["name"] for s in auth.load_stores()}
    return jsonify({**user,
                    "store_name": stores.get(user.get("store_id"), ""),
                    "role_label": auth.ROLE_LABEL.get(user["role"], ""),
                    "google_enabled": auth.google_enabled()})


# ===========================================================================
# 物件DB (Phase1.5): マイデータ/共有データ・公開範囲設定（Facilo p41相当）
# ===========================================================================

def load_bukken():
    if not os.path.exists(BUKKEN_FILE):
        return []
    with open(BUKKEN_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_bukken(items):
    with open(BUKKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def _visible_bukken(user, items, store_filter=None):
    """閲覧可能な物件: 自店の全物件 + 他店の全社公開(visibility=all)。admin/ogn は全件。"""
    role = user["role"]
    if role in ("admin", "ogn"):
        return [b for b in items if not store_filter or b.get("store_id") == store_filter]
    sid = user.get("store_id")
    return [b for b in items
            if b.get("store_id") == sid or b.get("visibility") == "all"]


def _can_edit_bukken(user, b):
    if user["role"] in ("admin", "ogn"):
        return True
    return b.get("store_id") == user.get("store_id")


def _bukken_stats():
    """物件キー別の提案数・閲覧数・反応数（Facilo p48 物件ログ相当）。"""
    stats = {}

    def bump(key, field, n=1):
        if not key:
            return
        s = stats.setdefault(key, {"proposals": 0, "views": 0, "favs": 0, "requests": 0})
        s[field] = max(0, s[field] + n)

    for p in load_proposals():
        bump(p.get("property_key"), "proposals")
    for e in load_activity():
        key = e.get("property_key")
        if e.get("type") == "view_property":
            bump(key, "views")
        elif e.get("type") == "react":
            a = e.get("action", "")
            if a == "fav":
                bump(key, "favs")
            elif a == "un_fav":
                bump(key, "favs", -1)
            elif a in ("doc_request", "ca_request"):
                bump(key, "requests")
    return stats


@app.route("/api/bukken")
@auth.require_role("store")
def bukken_list():
    user = auth.current_user()
    items = _visible_bukken(user, load_bukken(), request.args.get("store_id"))
    tab = request.args.get("tab")  # my=自店 / shared=他店の共有
    sid = user.get("store_id")
    if tab == "my":
        items = [b for b in items if b.get("store_id") == sid]
    elif tab == "shared":
        items = [b for b in items if b.get("store_id") != sid]
    stats = _bukken_stats()
    empty = {"proposals": 0, "views": 0, "favs": 0, "requests": 0}
    for b in items:
        b["stats"] = stats.get(property_key(b.get("prop") or {}), empty)
    sort = request.args.get("sort", "new")  # new / proposals / views / favs
    if sort in ("proposals", "views", "favs"):
        items = sorted(items, key=lambda b: b["stats"][sort], reverse=True)
    else:
        items = sorted(items, key=lambda b: b.get("created_at", ""), reverse=True)
    return jsonify(items)


@app.route("/api/bukken", methods=["POST"])
@auth.require_role("store")
def bukken_create():
    user = auth.current_user()
    body = request.json or {}
    prop = body.get("prop") or {}
    if not prop:
        return jsonify({"error": "prop required"}), 400
    items = load_bukken()
    rec = {
        "id": f"bk_{uuid.uuid4().hex[:10]}",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "store_id": user.get("store_id"),
        "owner_email": user["email"],
        "owner_name": user.get("name", ""),
        "visibility": body.get("visibility") or "store",  # store=自店のみ / all=全社共有
        "tags": body.get("tags") or [],
        "memo": body.get("memo") or "",
        "prop": prop,
        "lat": body.get("lat"),
        "lon": body.get("lon"),
        "images": body.get("images") or [],
    }
    items.append(rec)
    save_bukken(items)
    return jsonify({"ok": True, "bukken": rec})


@app.route("/api/bukken/<bid>", methods=["GET", "PUT", "DELETE"])
@auth.require_role("store")
def bukken_detail(bid):
    user = auth.current_user()
    items = load_bukken()
    b = next((x for x in items if x["id"] == bid), None)
    if not b or (request.method == "GET" and b not in _visible_bukken(user, items)):
        return jsonify({"error": "not found"}), 404
    if request.method == "GET":
        return jsonify(b)
    if not _can_edit_bukken(user, b):
        return jsonify({"error": "permission denied"}), 403
    if request.method == "DELETE":
        items.remove(b)
        save_bukken(items)
        return jsonify({"ok": True})
    body = request.json or {}
    for key in ("visibility", "tags", "memo", "prop", "lat", "lon"):
        if key in body:
            b[key] = body[key]
    save_bukken(items)
    return jsonify({"ok": True, "bukken": b})


# ===========================================================================
# ポータル3画面 (Phase1.5)
# ===========================================================================

@app.route("/portal")
@auth.require_role("store")
def portal_page():
    return render_template("portal.html", user=auth.current_user())


@app.route("/admin")
@auth.require_role("admin")
def admin_page():
    return render_template("admin.html", user=auth.current_user())


@app.route("/ogn")
@auth.require_role("ogn")
def ogn_page():
    return render_template("ogn.html", user=auth.current_user())


@app.route("/api/admin/summary")
@auth.require_role("admin")
def admin_summary():
    """マネージャーダッシュボード用の集計（Facilo p28相当）。"""
    stores = auth.load_stores()
    users = auth.load_users()
    bukken = load_bukken()
    customers = load_customers()
    proposals = load_proposals()
    deals = load_deals()

    by_store = []
    for s in stores:
        sid = s["id"]
        by_store.append({
            "store_id": sid,
            "store_name": s["name"],
            "users": sum(1 for u in users if u.get("store_id") == sid and u.get("active", True)),
            "bukken": sum(1 for b in bukken if b.get("store_id") == sid),
            "customers": sum(1 for c in customers if c.get("store_id") == sid),
            "proposals": sum(1 for p in proposals if p.get("store_id") == sid),
            "deals": sum(1 for d in deals if d.get("store_id") == sid),
        })
    by_user = []
    for u in users:
        if not u.get("active", True):
            continue
        em = u["email"]
        by_user.append({
            "email": em,
            "name": u.get("name", ""),
            "role": u.get("role"),
            "store_id": u.get("store_id"),
            "bukken": sum(1 for b in bukken if b.get("owner_email") == em),
            "proposals": sum(1 for p in proposals if p.get("user_email") == em),
            "deals": sum(1 for d in deals if d.get("user_email") == em),
        })
    recent = sorted(proposals, key=lambda p: p.get("ts", ""), reverse=True)[:15]
    return jsonify({
        "totals": {"stores": len(stores), "users": len(by_user),
                   "bukken": len(bukken), "customers": len(customers),
                   "proposals": len(proposals), "deals": len(deals)},
        "by_store": by_store,
        "by_user": by_user,
        "recent_proposals": recent,
    })


# ===========================================================================
# オーガナイズ画面API (Phase1.5): ユーザー・加盟店管理（ogn専用）
# ===========================================================================

@app.route("/api/ogn/users", methods=["GET", "POST"])
@auth.require_role("ogn")
def ogn_users():
    users = auth.load_users()
    if request.method == "GET":
        return jsonify(users)
    body = request.json or {}
    email = (body.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return jsonify({"error": "メールアドレスが不正です"}), 400
    if any(u["email"].lower() == email for u in users):
        return jsonify({"error": "既に登録済みのメールです"}), 400
    role = body.get("role") or "store"
    if role not in auth.ROLE_LEVEL:
        return jsonify({"error": "不正なロールです"}), 400
    users.append({
        "email": email,
        "name": body.get("name") or email,
        "role": role,
        "store_id": body.get("store_id") or None,
        "active": True,
    })
    auth.save_users(users)
    return jsonify({"ok": True})


@app.route("/api/ogn/users/<path:email>", methods=["PUT", "DELETE"])
@auth.require_role("ogn")
def ogn_user_detail(email):
    users = auth.load_users()
    u = next((x for x in users if x["email"].lower() == email.lower()), None)
    if not u:
        return jsonify({"error": "not found"}), 404
    me = auth.current_user()
    if request.method == "DELETE":
        if u["email"].lower() == me["email"].lower():
            return jsonify({"error": "自分自身は無効化できません"}), 400
        u["active"] = False
        auth.save_users(users)
        return jsonify({"ok": True})
    body = request.json or {}
    if "role" in body:
        if body["role"] not in auth.ROLE_LEVEL:
            return jsonify({"error": "不正なロールです"}), 400
        if u["email"].lower() == me["email"].lower() and body["role"] != "ogn":
            return jsonify({"error": "自分自身のオーガナイズ権限は外せません"}), 400
        u["role"] = body["role"]
    for key in ("name", "store_id"):
        if key in body:
            u[key] = body[key]
    if "active" in body:
        u["active"] = bool(body["active"])
    auth.save_users(users)
    return jsonify({"ok": True, "user": u})


@app.route("/api/ogn/stores", methods=["GET", "POST"])
def ogn_stores():
    # GETは全ロール（店舗名の解決に使う）、POSTはognのみ
    if request.method == "GET":
        if not auth.current_user():
            return jsonify({"error": "login required"}), 401
        return jsonify(auth.load_stores())
    user = auth.current_user()
    if not user or auth.user_level(user) < auth.ROLE_LEVEL["ogn"]:
        return jsonify({"error": "permission denied"}), 403
    body = request.json or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "店舗名が必要です"}), 400
    stores = auth.load_stores()
    sid = body.get("id") or f"store_{uuid.uuid4().hex[:6]}"
    if any(s["id"] == sid for s in stores):
        return jsonify({"error": "IDが重複しています"}), 400
    stores.append({"id": sid, "name": name, "created_at": time.strftime("%Y-%m-%d")})
    auth.save_stores(stores)
    return jsonify({"ok": True, "stores": stores})


# ===========================================================================
# 顧客マイページ・閲覧ログ (Phase2)
#   - 顧客ごとにトークンURLを発行。初回アクセス時にGoogleログインでバインド、
#     以降はセッションで再ログイン不要（確定済み設計: Googleログイン必須・初回のみ）。
#   - 営業/管理側はスタッフセッションでプレビュー閲覧可能（ログには残らない）。
# ===========================================================================

def load_mypages():
    if not os.path.exists(MYPAGE_FILE):
        return []
    with open(MYPAGE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_mypages(items):
    with open(MYPAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def load_activity():
    if not os.path.exists(ACTIVITY_FILE):
        return []
    with open(ACTIVITY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def log_activity(mp, type_, **kw):
    items = load_activity()
    items.append({
        "id": f"act_{uuid.uuid4().hex[:10]}",
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "token": mp["token"],
        "customer_id": mp["customer_id"],
        "store_id": mp.get("store_id"),
        "type": type_,
        **kw,
    })
    with open(ACTIVITY_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def _find_mypage(token):
    return next((m for m in load_mypages() if m["token"] == token), None)


def _mypage_session_ok(mp):
    """顧客本人（バインド済みセッション）かを判定。"""
    return session.get(f"mypage_{mp['token']}") == mp.get("bound_email") and mp.get("bound_email")


def _mypage_staff_preview(mp):
    """営業/管理のスタッフセッションならプレビュー閲覧を許可（自店スコープ）。"""
    user = auth.current_user()
    if not user:
        return False
    if user["role"] in ("admin", "ogn"):
        return True
    return user.get("store_id") == mp.get("store_id")


@app.route("/api/mypage/issue", methods=["POST"])
@auth.require_role("store")
def mypage_issue():
    """顧客のマイページURLを発行（既存があれば再利用）。"""
    cid = (request.json or {}).get("customer_id", "")
    cust = next((c for c in _scoped_customers() if c["id"] == cid), None)
    if not cust:
        return jsonify({"error": "スコープ内に該当顧客がいません"}), 404
    pages = load_mypages()
    mp = next((m for m in pages if m["customer_id"] == cid), None)
    if not mp:
        mp = {
            "token": uuid.uuid4().hex,
            "customer_id": cid,
            "customer_name": cust.get("name", ""),
            "store_id": cust.get("store_id"),
            "bound_email": None,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        pages.append(mp)
        save_mypages(pages)
    return jsonify({"ok": True, "url": f"/mypage/{mp['token']}", "mypage": mp})


@app.route("/mypage/<token>")
def mypage_page(token):
    mp = _find_mypage(token)
    if not mp:
        return "ページが見つかりません", 404
    return render_template("mypage.html",
                           token=token,
                           customer_name=mp.get("customer_name", ""),
                           google_client_id=os.environ.get("GOOGLE_CLIENT_ID", ""))


@app.route("/api/mypage/<token>/login", methods=["POST"])
def mypage_login(token):
    """初回: Googleアカウントをバインド。以降: 同一アカウントのみ許可。"""
    mp = _find_mypage(token)
    if not mp:
        return jsonify({"error": "invalid token"}), 404
    body = request.json or {}
    if auth.google_enabled():
        try:
            info = auth.verify_google_token(body.get("credential", ""))
        except ValueError as e:
            return jsonify({"error": f"Google認証に失敗しました: {e}"}), 401
        email = info["email"]
    else:
        email = (body.get("email") or "").strip().lower()  # 開発モード
        if not email:
            return jsonify({"error": "email required"}), 400
    if not mp.get("bound_email"):
        pages = load_mypages()
        m = next(x for x in pages if x["token"] == token)
        m["bound_email"] = email
        m["bound_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_mypages(pages)
        mp = m
        log_activity(mp, "bind", email=email)
    elif mp["bound_email"] != email:
        return jsonify({"error": "このマイページは別のアカウントに紐付いています。担当者にご連絡ください。"}), 403
    session[f"mypage_{token}"] = email
    session.permanent = True
    log_activity(mp, "login", email=email)
    return jsonify({"ok": True})


@app.route("/api/mypage/<token>/items")
def mypage_items(token):
    mp = _find_mypage(token)
    if not mp:
        return jsonify({"error": "invalid token"}), 404
    is_customer = _mypage_session_ok(mp)
    is_preview = not is_customer and _mypage_staff_preview(mp)
    if not is_customer and not is_preview:
        return jsonify({"error": "login required",
                        "bound": bool(mp.get("bound_email"))}), 401
    proposals = [p for p in load_proposals() if p.get("customer_id") == mp["customer_id"]]
    proposals.sort(key=lambda p: p.get("ts", ""), reverse=True)
    # 物件ごとの現在のリアクション状態
    reactions = {}
    for ev in load_activity():
        if ev.get("token") == token and ev.get("type") == "react":
            key = ev.get("property_key")
            reactions.setdefault(key, set())
            action = ev.get("action", "")
            if action.startswith("un_"):
                reactions[key].discard(action[3:])
            else:
                reactions[key].add(action)
    items = [{
        "property_key": p.get("property_key"),
        "property_name": p.get("property_name", ""),
        "ts": p.get("ts"),
        "prop": p.get("prop") or {},
        "images": p.get("images") or [],
        "text": p.get("text", ""),
        "reactions": sorted(reactions.get(p.get("property_key"), [])),
    } for p in proposals]
    if is_customer:
        log_activity(mp, "view", email=mp["bound_email"])
    return jsonify({"customer_name": mp.get("customer_name", ""),
                    "preview": is_preview, "items": items})


@app.route("/api/mypage/<token>/react", methods=["POST"])
def mypage_react(token):
    mp = _find_mypage(token)
    if not mp:
        return jsonify({"error": "invalid token"}), 404
    if not _mypage_session_ok(mp):
        return jsonify({"error": "login required"}), 401
    body = request.json or {}
    action = body.get("action", "")
    valid = {"fav", "un_fav", "trash", "un_trash", "doc_request", "ca_request"}
    if action not in valid or not body.get("property_key"):
        return jsonify({"error": "invalid action"}), 400
    log_activity(mp, "react", property_key=body["property_key"],
                 action=action, email=mp["bound_email"])
    return jsonify({"ok": True})


@app.route("/api/mypage/<token>/view", methods=["POST"])
def mypage_view(token):
    """物件詳細の閲覧ログ（どの物件をよく見ているかの把握用）。"""
    mp = _find_mypage(token)
    if not mp or not _mypage_session_ok(mp):
        return jsonify({"ok": False}), 401
    key = (request.json or {}).get("property_key")
    if key:
        log_activity(mp, "view_property", property_key=key, email=mp["bound_email"])
    return jsonify({"ok": True})


@app.route("/api/customers/<cid>/activity")
@auth.require_role("store")
def customer_activity(cid):
    """営業側の顧客ログ（Faciloの顧客ログ機能相当）。店舗スコープ適用。"""
    cust = next((c for c in _scoped_customers() if c["id"] == cid), None)
    if not cust:
        return jsonify({"error": "スコープ内に該当顧客がいません"}), 404
    mp = next((m for m in load_mypages() if m["customer_id"] == cid), None)
    events = [e for e in load_activity() if e.get("customer_id") == cid]
    events.sort(key=lambda e: e.get("ts", ""), reverse=True)
    summary = {
        "views": sum(1 for e in events if e["type"] in ("view", "view_property")),
        "favs": sum(1 for e in events if e["type"] == "react" and e.get("action") == "fav"),
        "doc_requests": sum(1 for e in events if e["type"] == "react" and e.get("action") == "doc_request"),
        "ca_requests": sum(1 for e in events if e["type"] == "react" and e.get("action") == "ca_request"),
    }
    deals = [d for d in load_deals() if d.get("customer_id") == cid]
    deals.sort(key=lambda d: d.get("deal_date", ""), reverse=True)
    return jsonify({
        "customer_name": cust.get("name", ""),
        "mypage_url": f"/mypage/{mp['token']}" if mp else None,
        "bound_email": mp.get("bound_email") if mp else None,
        "summary": summary,
        "events": events[:50],
        "deals": deals,
    })


# ===========================================================================
# 成約登録 (Phase3a): リピート顧客・過去案件の履歴管理（Facilo p27相当）
# ===========================================================================

def load_deals():
    if not os.path.exists(DEALS_FILE):
        return []
    with open(DEALS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_deals(items):
    with open(DEALS_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


@app.route("/api/deals", methods=["GET", "POST"])
@auth.require_role("store")
def deals():
    user = auth.current_user()
    if request.method == "GET":
        items = load_deals()
        sid = auth.scope_store_id(request.args.get("store_id"))
        if sid:
            items = [d for d in items if d.get("store_id") == sid]
        cid = request.args.get("customer_id")
        if cid:
            items = [d for d in items if d.get("customer_id") == cid]
        items.sort(key=lambda d: d.get("deal_date", ""), reverse=True)
        return jsonify(items)

    body = request.json or {}
    cid = body.get("customer_id", "")
    cust = next((c for c in _scoped_customers() if c["id"] == cid), None)
    if not cust:
        return jsonify({"error": "スコープ内に該当顧客がいません"}), 400
    if not (body.get("property_name") or "").strip():
        return jsonify({"error": "物件名が必要です"}), 400
    items = load_deals()
    rec = {
        "id": f"deal_{uuid.uuid4().hex[:10]}",
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "deal_date": body.get("deal_date") or time.strftime("%Y-%m-%d"),
        "store_id": user.get("store_id"),
        "user_email": user["email"],
        "user_name": user.get("name", ""),
        "customer_id": cid,
        "customer_name": cust.get("name", ""),
        "property_key": body.get("property_key") or "",
        "property_name": body.get("property_name").strip(),
        "price_yen": body.get("price_yen"),
        "fee_yen": body.get("fee_yen"),
        "memo": body.get("memo") or "",
    }
    items.append(rec)
    save_deals(items)
    return jsonify({"ok": True, "deal": rec})


@app.route("/api/deals/<did>", methods=["DELETE"])
@auth.require_role("store")
def delete_deal(did):
    user = auth.current_user()
    items = load_deals()
    d = next((x for x in items if x["id"] == did), None)
    if not d:
        return jsonify({"error": "not found"}), 404
    if user["role"] == "store" and d.get("store_id") != user.get("store_id"):
        return jsonify({"error": "permission denied"}), 403
    items.remove(d)
    save_deals(items)
    return jsonify({"ok": True})


# ===========================================================================
# 顧客チャット (Phase3c): マイページ⇄営業のメッセージ（Facilo p32の簡易版）
# ===========================================================================

def load_messages():
    if not os.path.exists(MESSAGES_FILE):
        return []
    with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_messages(items):
    with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def _append_message(cid, store_id, from_, sender_name, text):
    text = (text or "").strip()
    if not text:
        return None, ("メッセージが空です", 400)
    if len(text) > 2000:
        return None, ("メッセージが長すぎます（2000文字まで）", 400)
    items = load_messages()
    rec = {
        "id": f"msg_{uuid.uuid4().hex[:10]}",
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "customer_id": cid,
        "store_id": store_id,
        "from": from_,            # "customer" | "staff"
        "sender_name": sender_name,
        "text": text,
    }
    items.append(rec)
    save_messages(items)
    return rec, None


@app.route("/api/chat/<cid>", methods=["GET", "POST"])
@auth.require_role("store")
def staff_chat(cid):
    """営業側チャット。店舗スコープ適用。"""
    user = auth.current_user()
    cust = next((c for c in _scoped_customers() if c["id"] == cid), None)
    if not cust:
        return jsonify({"error": "スコープ内に該当顧客がいません"}), 404
    if request.method == "GET":
        msgs = [m for m in load_messages() if m.get("customer_id") == cid]
        return jsonify(msgs[-100:])
    rec, err = _append_message(cid, cust.get("store_id"), "staff",
                               user.get("name", user["email"]),
                               (request.json or {}).get("text"))
    if err:
        return jsonify({"error": err[0]}), err[1]
    return jsonify({"ok": True, "message": rec})


@app.route("/api/mypage/<token>/chat", methods=["GET", "POST"])
def mypage_chat(token):
    """顧客側チャット。送信は顧客本人のみ（スタッフプレビューは閲覧のみ）。"""
    mp = _find_mypage(token)
    if not mp:
        return jsonify({"error": "invalid token"}), 404
    is_customer = _mypage_session_ok(mp)
    if request.method == "GET":
        if not is_customer and not _mypage_staff_preview(mp):
            return jsonify({"error": "login required"}), 401
        msgs = [m for m in load_messages() if m.get("customer_id") == mp["customer_id"]]
        return jsonify(msgs[-100:])
    if not is_customer:
        return jsonify({"error": "login required"}), 401
    rec, err = _append_message(mp["customer_id"], mp.get("store_id"), "customer",
                               mp.get("customer_name", "顧客"),
                               (request.json or {}).get("text"))
    if err:
        return jsonify({"error": err[0]}), err[1]
    log_activity(mp, "chat", email=mp["bound_email"])
    return jsonify({"ok": True, "message": rec})


@app.route("/api/compile/upload", methods=["POST"])
def compile_upload():
    """Receive a PDF, store it under a session-scoped token, return preview info."""
    import compile_tool as ct
    if "pdf" not in request.files:
        return jsonify({"error": "no file"}), 400
    f = request.files["pdf"]
    if not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "not a PDF"}), 400

    token = uuid.uuid4().hex
    safe = re.sub(r"[^\w\.\-]+", "_", f.filename)
    save_path = os.path.join(COMPILE_UPLOAD_DIR, f"{token}__{safe}")
    f.save(save_path)

    # First-page metadata
    import fitz
    doc = fitz.open(save_path)
    pages = []
    for i in range(len(doc)):
        p = doc[i]
        pages.append({"width_pt": p.rect.width, "height_pt": p.rect.height})
    doc.close()

    # Try extract metadata for table
    info = ct.extract_for_table(save_path)

    return jsonify({
        "token": token,
        "filename": f.filename,
        "pages": pages,
        "extracted": info,
    })


@app.route("/api/compile/preview")
def compile_preview():
    """Return PNG preview of a page."""
    import compile_tool as ct
    token = request.args.get("token", "")
    page = int(request.args.get("page", 0))
    if not re.match(r"^[a-f0-9]{32}$", token):
        return jsonify({"error": "bad token"}), 400
    # Find matching file
    matches = [f for f in os.listdir(COMPILE_UPLOAD_DIR) if f.startswith(token + "__")]
    if not matches:
        return jsonify({"error": "not found"}), 404
    pdf_path = os.path.join(COMPILE_UPLOAD_DIR, matches[0])
    png, w_pt, h_pt, total = ct.render_page_png(pdf_path, page, dpi=110)
    resp = Response(png, mimetype="image/png")
    resp.headers["X-Page-Width-Pt"] = str(w_pt)
    resp.headers["X-Page-Height-Pt"] = str(h_pt)
    resp.headers["X-Total-Pages"] = str(total)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/api/compile/templates", methods=["GET"])
def compile_templates_list():
    return jsonify(_load_compile_templates())


@app.route("/api/compile/templates", methods=["POST"])
def compile_templates_save():
    body = request.json or {}
    name = (body.get("name") or "").strip()
    rects = body.get("rects") or []
    if not name:
        return jsonify({"error": "name required"}), 400
    # Validate rects: list of {x,y,w,h} normalized 0-1
    valid = []
    for r in rects:
        try:
            x, y, w, h = float(r["x"]), float(r["y"]), float(r["w"]), float(r["h"])
            if 0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1:
                valid.append({"x": x, "y": y, "w": w, "h": h})
        except (KeyError, TypeError, ValueError):
            continue
    if not valid:
        return jsonify({"error": "no valid rects"}), 400

    templates = _load_compile_templates()
    templates[name] = {
        "name": name,
        "description": body.get("description", ""),
        "rects": valid,
    }
    _save_compile_templates(templates)
    return jsonify({"status": "ok", "name": name})


@app.route("/api/compile/templates/<name>", methods=["DELETE"])
def compile_templates_delete(name):
    templates = _load_compile_templates()
    if name in templates:
        del templates[name]
        _save_compile_templates(templates)
        return jsonify({"status": "ok"})
    return jsonify({"error": "not found"}), 404


@app.route("/api/compile/generate", methods=["POST"])
def compile_generate():
    """Generate the merged PDF.

    Request body:
      {
        "items": [
          {
            "token": "...",
            "name": "...", "address": "...",
            "rent": "...", "area": "...", "year": "...", "station": "...",
            "lat": float|null, "lon": float|null,
            "rects_normalized": [{"x":0..1,"y":0..1,"w":0..1,"h":0..1}, ...]
              # applied to ALL pages of this PDF
          },
          ...
        ]
      }
    Returns: application/pdf bytes.
    """
    import compile_tool as ct
    import fitz
    body = request.json or {}
    items = body.get("items") or []
    if not items:
        return jsonify({"error": "no items"}), 400

    masked_blobs = []
    table_rows = []
    map_props = []

    for item in items:
        token = item.get("token", "")
        if not re.match(r"^[a-f0-9]{32}$", token):
            continue
        matches = [f for f in os.listdir(COMPILE_UPLOAD_DIR) if f.startswith(token + "__")]
        if not matches:
            continue
        pdf_path = os.path.join(COMPILE_UPLOAD_DIR, matches[0])

        # Build rects_per_page (apply same rects to all pages)
        doc = fitz.open(pdf_path)
        npages = len(doc)
        page_dims = [(doc[i].rect.width, doc[i].rect.height) for i in range(npages)]
        doc.close()

        norm_rects = item.get("rects_normalized") or []
        rects_per_page = {}
        for i, (pw, ph) in enumerate(page_dims):
            rects_per_page[i] = []
            for r in norm_rects:
                try:
                    x = float(r["x"]) * pw
                    y = float(r["y"]) * ph
                    w = float(r["w"]) * pw
                    h = float(r["h"]) * ph
                    if w > 0 and h > 0:
                        rects_per_page[i].append((x, y, w, h))
                except (KeyError, TypeError, ValueError):
                    continue

        masked = ct.mask_pdf(pdf_path, rects_per_page)
        masked_blobs.append(masked)

        # Table row
        table_rows.append({
            "name": item.get("name") or "",
            "address": item.get("address") or "",
            "rent": item.get("rent") or "",
            "area": item.get("area") or "",
            "year": item.get("year") or "",
            "station": item.get("station") or "",
            "deposit": item.get("deposit") or "",
            "keymoney": item.get("keymoney") or "",
            "facilities": item.get("facilities") or "",
            "interior": item.get("interior") or "",
            "available": item.get("available") or "",
        })

        # Map point
        lat = item.get("lat")
        lon = item.get("lon")
        if (lat is None or lon is None) and item.get("address"):
            lat, lon = ct.geocode(item["address"])
        if lat is not None and lon is not None:
            map_props.append({"name": item.get("name") or "", "lat": lat, "lon": lon})

    if not masked_blobs:
        return jsonify({"error": "no valid items"}), 400

    table_pdf = ct.make_table_pdf(table_rows)
    map_pdf = ct.make_map_pdf(map_props)

    final_pdf = ct.combine_pdfs(masked_blobs + [table_pdf, map_pdf])
    resp = Response(final_pdf, mimetype="application/pdf")
    resp.headers["Content-Disposition"] = 'attachment; filename="compiled.pdf"'
    return resp


@app.route("/api/compile/geocode", methods=["POST"])
def compile_geocode():
    """Helper: geocode an address from the compile UI."""
    import compile_tool as ct
    body = request.json or {}
    addr = (body.get("address") or "").strip()
    if not addr:
        return jsonify({"error": "address required"}), 400
    lat, lon = ct.geocode(addr)
    if lat is None:
        return jsonify({"error": "geocode failed"}), 400
    return jsonify({"lat": lat, "lon": lon})


@app.route("/api/compile/cleanup", methods=["POST"])
def compile_cleanup():
    """Delete uploaded temp files older than 1 hour, or by tokens."""
    body = request.json or {}
    tokens = body.get("tokens") or []
    deleted = 0
    if tokens:
        for f in os.listdir(COMPILE_UPLOAD_DIR):
            for t in tokens:
                if f.startswith(t + "__"):
                    try:
                        os.remove(os.path.join(COMPILE_UPLOAD_DIR, f))
                        deleted += 1
                    except OSError:
                        pass
    else:
        # Sweep stale files older than 1h
        cutoff = time.time() - 3600
        for f in os.listdir(COMPILE_UPLOAD_DIR):
            fp = os.path.join(COMPILE_UPLOAD_DIR, f)
            try:
                if os.path.getmtime(fp) < cutoff:
                    os.remove(fp)
                    deleted += 1
            except OSError:
                pass
    return jsonify({"status": "ok", "deleted": deleted})


if __name__ == "__main__":
    import argparse
    import subprocess
    import threading

    parser = argparse.ArgumentParser(description="物件マップサーバー")
    parser.add_argument("--public", action="store_true",
                        help="外部公開（アカウント・インストール不要）")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    if args.public:
        def start_tunnel():
            """SSH tunnel via serveo.net (no signup, no install)."""
            import sys
            print("\n  トンネル接続中...", flush=True)
            proc = subprocess.Popen(
                ["ssh", "-T",
                 "-o", "StrictHostKeyChecking=no",
                 "-o", "ServerAliveInterval=60",
                 "-R", f"80:localhost:{args.port}", "serveo.net"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
            )
            import re as _re
            for line in proc.stdout:
                text = line.decode("utf-8", errors="replace")
                # Strip ANSI escape codes
                clean = _re.sub(r"\x1b\[[0-9;]*m", "", text).strip()
                urls = _re.findall(r"https://\S+", clean)
                if urls:
                    url = urls[0]
                    msg = (f"\n{'='*60}\n"
                           f"  外部公開URL: {url}\n"
                           f"  このURLを共有するだけでアクセスできます\n"
                           f"  ログイン不要・誰でも閲覧/編集可能\n"
                           f"{'='*60}\n")
                    sys.stdout.write(msg)
                    sys.stdout.flush()
                    break

        tunnel_thread = threading.Thread(target=start_tunnel, daemon=True)
        tunnel_thread.start()

    host = "0.0.0.0" if args.public else "127.0.0.1"
    app.run(host=host, port=args.port, debug=not args.public)
