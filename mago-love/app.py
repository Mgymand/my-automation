"""老人ホーム出店専用アプリ「孫LOVE」 バックエンド (Flask)

機能:
  - 物件パイプライン管理（机上候補→内見予定→現調予定→開業予定→開業済み）
  - 地図（国土地理院/OSM 無料タイル。ZENRIN・Google はキー設定で切替）
  - 関東→都道府県→市区町村のクローズ表示、役所・病院・介護施設などのPOI表示
  - PDF/テキスト/CSV 取込（統一フォーマット）、統計CSV取込
  - 工程タスク・スケジュール・内見/現調報告・書類（Googleドライブ連携）
  - Slack通知（Webhook）と日次ダイジェスト（外部cronから叩く）
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import ssl
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

from flask import (Flask, Response, jsonify, redirect, render_template, request,
                   send_from_directory, session)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv(path):
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and v:
                os.environ[k] = v


_load_dotenv(os.path.join(BASE_DIR, ".env"))

import store  # noqa: E402
import auth  # noqa: E402
import domain  # noqa: E402
import notify  # noqa: E402
import extract  # noqa: E402

app = Flask(__name__, static_folder="static", template_folder="templates")


def _secret_key() -> str:
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    p = os.path.join(store.DATA_DIR, ".secret_key")
    if os.path.exists(p):
        return open(p, encoding="utf-8").read().strip()
    import secrets
    key = secrets.token_hex(32)
    with open(p, "w", encoding="utf-8") as f:
        f.write(key)
    return key


app.secret_key = _secret_key()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 30
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024
if os.environ.get("RENDER") or os.environ.get("TRUST_PROXY"):
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config["SESSION_COOKIE_SECURE"] = True

auth.bootstrap_admin()

APP_NAME = "老人ホーム出店専用アプリ-孫LOVE-"
_SSL = ssl.create_default_context()
MUNI_FILE = os.path.join(BASE_DIR, "data", "kanto_municipalities.json")


# ---------------------------------------------------------------------------
# 共通ヘルパ
# ---------------------------------------------------------------------------

def me() -> dict:
    return auth.current_user() or {}


def load_props() -> list[dict]:
    return store.load("properties", [])


def save_props(items: list[dict]):
    store.save("properties", items)


def find_prop(pid: str) -> dict | None:
    return next((p for p in load_props() if p["id"] == pid), None)


def touch(p: dict, action: str, detail: str = ""):
    p["updated_at"] = store.now_iso()
    p.setdefault("history", []).append(
        {"at": p["updated_at"], "by": me().get("name", ""), "action": action, "detail": detail})
    p["history"] = p["history"][-200:]


def municipalities() -> list[dict]:
    if not os.path.exists(MUNI_FILE):
        return []
    with open(MUNI_FILE, encoding="utf-8") as f:
        return json.load(f)


def public_settings() -> dict:
    s = store.load("settings", {})
    return {
        "app_url": s.get("app_url", ""),
        "slack_configured": bool(notify.webhook_url()),
        "zenrin_tile_url": s.get("zenrin_tile_url", ""),
        "google_maps_api_key": s.get("google_maps_api_key", ""),
        "google_api_key": s.get("google_api_key", ""),
        "google_client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
        "drive_root_url": s.get("drive_root_url", ""),
        "default_center": s.get("default_center") or [35.75, 139.75],
        "default_zoom": s.get("default_zoom") or 9,
        "notify_on_create": s.get("notify_on_create", True),
        "notify_on_status": s.get("notify_on_status", True),
        "notify_on_report": s.get("notify_on_report", True),
        "notify_on_schedule": s.get("notify_on_schedule", True),
        "digest_days_ahead": s.get("digest_days_ahead", 7),
        "llm_enabled": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "google_login": auth.google_enabled(),
    }


def geocode(q: str):
    """国土地理院 ジオコーディング（無料）。(lat, lon) or (None, None)。"""
    q = extract.normalize(q)
    q = re.sub(r"(\d+)-(\d+)-(\d+)", lambda m: f"{m.group(1)}丁目{m.group(2)}-{m.group(3)}", q)
    url = "https://msearch.gsi.go.jp/address-search/AddressSearch?" + urllib.parse.urlencode({"q": q})
    req = urllib.request.Request(url, headers={"User-Agent": "MagoLove/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10, context=_SSL) as r:
            d = json.loads(r.read().decode())
        if d:
            lon, lat = d[0]["geometry"]["coordinates"]
            return float(lat), float(lon)
    except Exception as e:  # noqa: BLE001
        print(f"[geocode] {q}: {e}")
    return None, None


def _bad(msg: str, code: int = 400):
    return jsonify({"error": msg}), code


# ---------------------------------------------------------------------------
# ページ / 認証
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    if not auth.current_user():
        return redirect("/login")
    return render_template("app.html", app_name=APP_NAME, user=me(),
                           google_client_id=os.environ.get("GOOGLE_CLIENT_ID", ""))


@app.route("/login")
def login_page():
    if auth.current_user():
        return redirect("/")
    users = [] if auth.google_enabled() else auth.load_users()
    return render_template("login.html", app_name=APP_NAME,
                           google_client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
                           dev_users=[u for u in users if u.get("active", True)],
                           next=request.args.get("next", "/"))


@app.route("/api/login/google", methods=["POST"])
def login_google():
    cred = (request.json or {}).get("credential", "")
    try:
        info = auth.verify_google_token(cred)
    except ValueError as e:
        return _bad(str(e), 401)
    user = auth.find_user(info["email"])
    if not user:
        return _bad("このメールアドレスは招待されていません。管理者に登録を依頼してください。", 403)
    if info.get("name") and not user.get("name"):
        user["name"] = info["name"]
    auth.login_user(user)
    return jsonify({"ok": True})


@app.route("/api/login/dev", methods=["POST"])
def login_dev():
    if auth.google_enabled():
        return _bad("dev login disabled", 403)
    user = auth.find_user((request.json or {}).get("email", ""))
    if not user:
        return _bad("user not found", 404)
    auth.login_user(user)
    return jsonify({"ok": True})


@app.route("/logout")
def logout():
    auth.logout_user()
    return redirect("/login")


@app.route("/api/bootstrap")
@auth.require_role("viewer")
def bootstrap():
    return jsonify({
        "app_name": APP_NAME,
        "me": me(),
        "settings": public_settings(),
        "statuses": domain.STATUSES,
        "phases": domain.PHASES,
        "poi_types": domain.POI_TYPES,
        "doc_types": domain.DOC_TYPES,
        "municipalities": municipalities(),
        "users": [{"email": u["email"], "name": u.get("name", "")} for u in auth.load_users() if u.get("active", True)],
    })


# ---------------------------------------------------------------------------
# 物件
# ---------------------------------------------------------------------------

@app.route("/api/properties")
@auth.require_role("viewer")
def list_properties():
    items = load_props()
    q = request.args
    if q.get("pref"):
        items = [p for p in items if p.get("pref") == q["pref"]]
    if q.get("city"):
        items = [p for p in items if p.get("city") == q["city"]]
    if q.get("status"):
        items = [p for p in items if p.get("status") in q["status"].split(",")]
    light = []
    for p in items:
        c = {k: v for k, v in p.items() if k not in ("history", "source")}
        c["task_total"] = len(p.get("tasks", []))
        c["task_done"] = sum(1 for t in p.get("tasks", []) if t.get("done"))
        c["task_overdue"] = sum(1 for t in p.get("tasks", [])
                                if not t.get("done") and t.get("due") and t["due"] < store.today())
        light.append(c)
    return jsonify(light)


@app.route("/api/properties", methods=["POST"])
@auth.require_role("member")
def create_property():
    payload = request.json or {}
    if not payload.get("name") and not payload.get("address"):
        return _bad("物件名または住所は必須です")
    if payload.get("address") and not (payload.get("lat") and payload.get("lon")):
        lat, lon = geocode(payload["address"])
        payload["lat"], payload["lon"] = lat, lon
    if payload.get("address") and not payload.get("pref"):
        payload.update({k: v for k, v in extract.split_address(payload["address"]).items() if v})
    p = domain.new_property(payload, me().get("name", ""))
    items = load_props()
    items.append(p)
    save_props(items)
    notify.notify_property_created(p, me().get("name", ""))
    return jsonify(p), 201


@app.route("/api/properties/<pid>")
@auth.require_role("viewer")
def get_property(pid):
    p = find_prop(pid)
    return (jsonify(p) if p else _bad("not found", 404))


@app.route("/api/properties/<pid>", methods=["PUT"])
@auth.require_role("member")
def update_property(pid):
    items = load_props()
    p = next((x for x in items if x["id"] == pid), None)
    if not p:
        return _bad("not found", 404)
    payload = request.json or {}
    old_status = p["status"]
    old_sched = dict(p.get("schedule", {}))
    old_addr = p.get("address")
    domain.merge_property(p, payload)
    if payload.get("address") and payload["address"] != old_addr and not payload.get("lat"):
        p["lat"], p["lon"] = geocode(payload["address"])
        p.update({k: v for k, v in extract.split_address(payload["address"]).items() if v})
    if p["status"] != old_status:
        touch(p, "status", f"{domain.STATUS_LABEL[old_status]} → {domain.STATUS_LABEL[p['status']]}")
        notify.notify_status_changed(p, old_status, p["status"], me().get("name", ""), domain.STATUS_LABEL)
    else:
        touch(p, "update", ", ".join(k for k in payload.keys() if k in domain.PROPERTY_TEMPLATE))
    labels = {"viewing_date": "内見日", "survey_date": "現調日", "approval_date": "稟議承認",
              "contract_date": "契約日", "construction_start": "着工", "construction_end": "竣工",
              "opening_date": "開業日"}
    for k, lab in labels.items():
        if p["schedule"].get(k) and p["schedule"].get(k) != old_sched.get(k):
            notify.notify_schedule(p, lab, p["schedule"][k], me().get("name", ""))
    save_props(items)
    return jsonify(p)


@app.route("/api/properties/<pid>", methods=["DELETE"])
@auth.require_role("admin")
def delete_property(pid):
    items = load_props()
    new = [x for x in items if x["id"] != pid]
    if len(new) == len(items):
        return _bad("not found", 404)
    save_props(new)
    return jsonify({"ok": True})


@app.route("/api/properties/<pid>/geocode", methods=["POST"])
@auth.require_role("member")
def regeocode(pid):
    items = load_props()
    p = next((x for x in items if x["id"] == pid), None)
    if not p:
        return _bad("not found", 404)
    lat, lon = geocode(p.get("address", ""))
    if lat is None:
        return _bad("住所から座標を取得できませんでした")
    p["lat"], p["lon"] = lat, lon
    touch(p, "geocode", f"{lat:.5f},{lon:.5f}")
    save_props(items)
    return jsonify(p)


# --- タスク ---

@app.route("/api/properties/<pid>/tasks", methods=["POST"])
@auth.require_role("member")
def add_task(pid):
    items = load_props()
    p = next((x for x in items if x["id"] == pid), None)
    if not p:
        return _bad("not found", 404)
    d = request.json or {}
    if not d.get("title"):
        return _bad("title required")
    t = {"id": store.new_id("task"), "phase": d.get("phase") if d.get("phase") in domain.PHASE_KEYS else "acquire",
         "title": d["title"], "done": False, "due": d.get("due", ""), "assignee": d.get("assignee", ""), "done_at": ""}
    p["tasks"].append(t)
    touch(p, "task_add", t["title"])
    save_props(items)
    return jsonify(t), 201


@app.route("/api/properties/<pid>/tasks/<tid>", methods=["PUT", "DELETE"])
@auth.require_role("member")
def edit_task(pid, tid):
    items = load_props()
    p = next((x for x in items if x["id"] == pid), None)
    if not p:
        return _bad("not found", 404)
    t = next((x for x in p["tasks"] if x["id"] == tid), None)
    if not t:
        return _bad("task not found", 404)
    if request.method == "DELETE":
        p["tasks"].remove(t)
        touch(p, "task_delete", t["title"])
    else:
        d = request.json or {}
        for k in ("title", "due", "assignee", "phase"):
            if k in d:
                t[k] = d[k]
        if "done" in d:
            t["done"] = bool(d["done"])
            t["done_at"] = store.today() if t["done"] else ""
            touch(p, "task_done" if t["done"] else "task_undone", t["title"])
    save_props(items)
    return jsonify(p)


# --- 報告（内見・現調） ---

@app.route("/api/properties/<pid>/reports", methods=["POST"])
@auth.require_role("member")
def add_report(pid):
    items = load_props()
    p = next((x for x in items if x["id"] == pid), None)
    if not p:
        return _bad("not found", 404)
    d = request.json or {}
    r = {"id": store.new_id("rep"), "type": d.get("type", "viewing"), "date": d.get("date") or store.today(),
         "author": me().get("name", ""), "summary": d.get("summary", ""), "pros": d.get("pros", ""),
         "cons": d.get("cons", ""), "rating": int(d.get("rating") or 0), "url": d.get("url", ""),
         "next_action": d.get("next_action", ""), "created_at": store.now_iso()}
    p["reports"].insert(0, r)
    touch(p, "report", {"viewing": "内見報告", "survey": "現調報告"}.get(r["type"], "報告"))
    save_props(items)
    notify.notify_report(p, r, me().get("name", ""))
    return jsonify(p), 201


@app.route("/api/properties/<pid>/reports/<rid>", methods=["DELETE"])
@auth.require_role("member")
def delete_report(pid, rid):
    items = load_props()
    p = next((x for x in items if x["id"] == pid), None)
    if not p:
        return _bad("not found", 404)
    p["reports"] = [r for r in p["reports"] if r["id"] != rid]
    touch(p, "report_delete", rid)
    save_props(items)
    return jsonify(p)


# --- 書類（Googleドライブ リンク） ---

@app.route("/api/properties/<pid>/docs", methods=["POST"])
@auth.require_role("member")
def add_doc(pid):
    items = load_props()
    p = next((x for x in items if x["id"] == pid), None)
    if not p:
        return _bad("not found", 404)
    d = request.json or {}
    if not d.get("url") and not d.get("drive_id"):
        return _bad("url required")
    doc = {"id": store.new_id("doc"), "type": d.get("type") or "その他", "title": d.get("title") or d.get("url", ""),
           "url": d.get("url", ""), "drive_id": d.get("drive_id", ""), "mime": d.get("mime", ""),
           "updated_at": store.today(), "by": me().get("name", "")}
    p["docs"].insert(0, doc)
    touch(p, "doc_add", f"{doc['type']}: {doc['title']}")
    save_props(items)
    return jsonify(p), 201


@app.route("/api/properties/<pid>/docs/<did>", methods=["DELETE"])
@auth.require_role("member")
def delete_doc(pid, did):
    items = load_props()
    p = next((x for x in items if x["id"] == pid), None)
    if not p:
        return _bad("not found", 404)
    p["docs"] = [x for x in p["docs"] if x["id"] != did]
    touch(p, "doc_delete", did)
    save_props(items)
    return jsonify(p)


# ---------------------------------------------------------------------------
# 取込（PDF / テキスト / CSV）
# ---------------------------------------------------------------------------

def _safe_name(name: str) -> str:
    name = os.path.basename(name or "file.pdf")
    return re.sub(r"[^\w\-. ぁ-んァ-ヶ一-龠々ー]", "_", name)[:120]


@app.route("/api/import/pdf", methods=["POST"])
@auth.require_role("member")
def import_pdf():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".pdf"):
        return _bad("PDFファイルを選択してください")
    fname = f"{int(time.time())}_{_safe_name(f.filename)}"
    path = os.path.join(store.UPLOAD_DIR, fname)
    f.save(path)
    try:
        text = extract.pdf_text(path)
    except Exception as e:  # noqa: BLE001
        return _bad(f"PDFを読めませんでした: {e}")
    draft = extract.draft_from_text(text) if len(text.strip()) >= 30 else {"name": "", "spec": {}, "finance": {}}
    draft["source"] = {"type": "pdf", "filename": fname, "url": f"/uploads/{fname}", "text": text[:8000]}
    draft["scanned"] = len(text.strip()) < 30
    if draft.get("address"):
        draft["lat"], draft["lon"] = geocode(draft["address"])
    return jsonify(draft)


@app.route("/api/import/text", methods=["POST"])
@auth.require_role("member")
def import_text():
    text = (request.json or {}).get("text", "")
    if len(text.strip()) < 10:
        return _bad("テキストが短すぎます")
    draft = extract.draft_from_text(text)
    if draft.get("address"):
        draft["lat"], draft["lon"] = geocode(draft["address"])
    return jsonify(draft)


@app.route("/uploads/<path:filename>")
@auth.require_role("viewer")
def serve_upload(filename):
    return send_from_directory(store.UPLOAD_DIR, filename)


@app.route("/uploads/<path:filename>/preview.png")
@auth.require_role("viewer")
def preview_upload(filename):
    path = os.path.realpath(os.path.join(store.UPLOAD_DIR, filename))
    if not path.startswith(os.path.realpath(store.UPLOAD_DIR) + os.sep) or not os.path.exists(path):
        return _bad("not found", 404)
    try:
        png = extract.pdf_page_png(path, int(request.args.get("page", 0)))
    except Exception as e:  # noqa: BLE001
        return _bad(f"preview failed: {e}", 500)
    return Response(png, mimetype="image/png", headers={"Cache-Control": "private, max-age=3600"})


def _read_csv(file_storage) -> list[dict]:
    raw = file_storage.read()
    for enc in ("utf-8-sig", "cp932", "utf-8"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("文字コードを判別できません（UTF-8 または Shift_JIS）")
    return list(csv.DictReader(io.StringIO(text)))


# CSV列名のゆらぎ吸収（日本語ヘッダ → 内部キー）
_PROP_CSV_MAP = {
    "name": ["物件名", "名称", "建物名", "name"], "address": ["住所", "所在地", "address"],
    "status": ["ステータス", "status"], "assignee": ["担当", "担当者", "assignee"],
    "priority": ["優先度", "priority"], "lat": ["緯度", "lat"], "lon": ["経度", "lon", "lng"],
    "memo": ["メモ", "備考", "memo"], "rent_yen": ["賃料", "月額賃料", "rent"],
    "floor_area_sqm": ["面積", "延床面積", "床面積(㎡)", "floor_area_sqm"],
    "floor_area_tsubo": ["坪数", "面積(坪)"], "rooms_planned": ["居室数", "想定居室数"],
    "structure": ["構造"], "built_ym": ["竣工", "築年月"], "zoning": ["用途地域"],
    "opening_date": ["開業予定日", "開業日"], "folder_url": ["ドライブ", "Driveフォルダ", "drive"],
    "property_type": ["種別", "物件種別"], "source_company": ["元付", "情報提供会社"],
}


def _pick(row: dict, keys: list[str]):
    for k in keys:
        for rk, v in row.items():
            if rk and rk.strip().lower() == k.lower() and str(v).strip():
                return str(v).strip()
    return ""


@app.route("/api/import/csv/properties", methods=["POST"])
@auth.require_role("member")
def import_csv_properties():
    f = request.files.get("file")
    if not f:
        return _bad("CSVファイルを選択してください")
    try:
        rows = _read_csv(f)
    except ValueError as e:
        return _bad(str(e))
    items = load_props()
    label_to_key = {v: k for k, v in domain.STATUS_LABEL.items()}
    created = 0
    for row in rows:
        name, addr = _pick(row, _PROP_CSV_MAP["name"]), _pick(row, _PROP_CSV_MAP["address"])
        if not name and not addr:
            continue
        st = _pick(row, _PROP_CSV_MAP["status"])
        payload = {
            "name": name, "address": addr,
            "status": label_to_key.get(st, st if st in domain.STATUS_KEYS else "desk"),
            "assignee": _pick(row, _PROP_CSV_MAP["assignee"]),
            "priority": _pick(row, _PROP_CSV_MAP["priority"]) or "B",
            "memo": _pick(row, _PROP_CSV_MAP["memo"]),
            "spec": {k: _pick(row, _PROP_CSV_MAP[k]) for k in
                     ("structure", "built_ym", "zoning", "property_type", "source_company")},
            "schedule": {"opening_date": _pick(row, _PROP_CSV_MAP["opening_date"])},
            "drive": {"folder_url": _pick(row, _PROP_CSV_MAP["folder_url"])},
        }
        for k in ("rent_yen", "floor_area_sqm", "floor_area_tsubo", "rooms_planned"):
            v = _pick(row, _PROP_CSV_MAP[k])
            if v:
                payload["spec"][k] = extract._yen(v) if k == "rent_yen" else extract._num(v)
        lat, lon = _pick(row, _PROP_CSV_MAP["lat"]), _pick(row, _PROP_CSV_MAP["lon"])
        if lat and lon:
            payload["lat"], payload["lon"] = float(lat), float(lon)
        elif addr:
            payload["lat"], payload["lon"] = geocode(addr)
            time.sleep(0.15)
        if addr:
            payload.update({k: v for k, v in extract.split_address(addr).items() if v})
        payload["source"] = {"type": "csv", "filename": f.filename}
        items.append(domain.new_property(payload, me().get("name", "")))
        created += 1
    save_props(items)
    return jsonify({"created": created, "rows": len(rows)})


# ---------------------------------------------------------------------------
# POI（役所・病院・介護施設 等）
# ---------------------------------------------------------------------------

@app.route("/api/pois")
@auth.require_role("viewer")
def list_pois():
    items = store.load("pois", [])
    q = request.args
    if q.get("pref"):
        items = [x for x in items if x.get("pref") == q["pref"]]
    if q.get("city"):
        items = [x for x in items if x.get("city") == q["city"]]
    if q.get("type"):
        items = [x for x in items if x.get("type") in q["type"].split(",")]
    return jsonify(items)


@app.route("/api/pois", methods=["POST"])
@auth.require_role("member")
def add_poi():
    d = request.json or {}
    if not d.get("name"):
        return _bad("name required")
    if not (d.get("lat") and d.get("lon")) and d.get("address"):
        d["lat"], d["lon"] = geocode(d["address"])
    if d.get("address") and not d.get("pref"):
        d.update({k: v for k, v in extract.split_address(d["address"]).items() if v and k != "address"})
    poi = {"id": store.new_id("poi"), "type": d.get("type") if d.get("type") in domain.POI_TYPE_KEYS else "other",
           "name": d["name"], "address": d.get("address", ""), "pref": d.get("pref", ""), "city": d.get("city", ""),
           "lat": d.get("lat"), "lon": d.get("lon"), "tel": d.get("tel", ""), "url": d.get("url", ""),
           "memo": d.get("memo", ""), "capacity": d.get("capacity", ""), "created_at": store.now_iso()}
    items = store.load("pois", [])
    items.append(poi)
    store.save("pois", items)
    return jsonify(poi), 201


@app.route("/api/pois/<poi_id>", methods=["PUT", "DELETE"])
@auth.require_role("member")
def edit_poi(poi_id):
    items = store.load("pois", [])
    poi = next((x for x in items if x["id"] == poi_id), None)
    if not poi:
        return _bad("not found", 404)
    if request.method == "DELETE":
        items.remove(poi)
    else:
        for k, v in (request.json or {}).items():
            if k in poi and k != "id":
                poi[k] = v
    store.save("pois", items)
    return jsonify(poi if request.method == "PUT" else {"ok": True})


@app.route("/api/pois/import", methods=["POST"])
@auth.require_role("member")
def import_pois():
    """CSV取込（国土数値情報・厚労省の施設一覧・自作リストなど）。"""
    f = request.files.get("file")
    if not f:
        return _bad("CSVファイルを選択してください")
    default_type = request.form.get("type") or "other"
    try:
        rows = _read_csv(f)
    except ValueError as e:
        return _bad(str(e))
    cmap = {"name": ["名称", "施設名", "事業所名", "病院名", "name"], "address": ["住所", "所在地", "address"],
            "lat": ["緯度", "lat", "Y"], "lon": ["経度", "lon", "lng", "X"], "tel": ["電話", "電話番号", "tel"],
            "type": ["種別", "type"], "url": ["URL", "url"], "capacity": ["定員", "capacity"], "memo": ["備考", "memo"]}
    label_to_key = {p["label"]: p["key"] for p in domain.POI_TYPES}
    items = store.load("pois", [])
    created, geocoded = 0, 0
    for row in rows:
        name = _pick(row, cmap["name"])
        if not name:
            continue
        t = _pick(row, cmap["type"])
        t = label_to_key.get(t, t if t in domain.POI_TYPE_KEYS else default_type)
        addr = _pick(row, cmap["address"])
        lat, lon = _pick(row, cmap["lat"]), _pick(row, cmap["lon"])
        if lat and lon:
            lat, lon = float(lat), float(lon)
        elif addr and geocoded < 300:
            lat, lon = geocode(addr)
            geocoded += 1
            time.sleep(0.15)
        else:
            lat, lon = None, None
        poi = {"id": store.new_id("poi"), "type": t, "name": name, "address": addr, "lat": lat, "lon": lon,
               "tel": _pick(row, cmap["tel"]), "url": _pick(row, cmap["url"]),
               "capacity": _pick(row, cmap["capacity"]), "memo": _pick(row, cmap["memo"]),
               "created_at": store.now_iso()}
        poi.update({k: v for k, v in extract.split_address(addr).items() if v and k != "address"})
        items.append(poi)
        created += 1
    store.save("pois", items)
    return jsonify({"created": created, "rows": len(rows)})


_OSM_QUERIES = {
    "hospital": 'nwr["amenity"="hospital"]',
    "clinic": 'nwr["amenity"="clinic"]',
    "city_hall": 'nwr["amenity"="townhall"]',
    "care": 'nwr["amenity"="social_facility"]["social_facility"~"nursing_home|assisted_living|group_home"]',
    "station": 'node["railway"="station"]',
}


@app.route("/api/pois/fetch_osm", methods=["POST"])
@auth.require_role("member")
def fetch_osm():
    """OpenStreetMap (Overpass API・無料) から範囲内の施設を取り込む。"""
    d = request.json or {}
    try:
        s, w, n, e = [float(d[k]) for k in ("south", "west", "north", "east")]
    except (KeyError, ValueError):
        return _bad("bbox required")
    if (n - s) * (e - w) > 0.3:
        return _bad("範囲が広すぎます。地図をズームしてから取得してください。")
    types = [t for t in (d.get("types") or ["hospital", "city_hall", "care"]) if t in _OSM_QUERIES]
    body = "[out:json][timeout:25];(" + "".join(f'{_OSM_QUERIES[t]}({s},{w},{n},{e});' for t in types) + ");out center tags;"
    req = urllib.request.Request("https://overpass-api.de/api/interpreter",
                                 data=urllib.parse.urlencode({"data": body}).encode(),
                                 headers={"User-Agent": "MagoLove/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=40, context=_SSL) as r:
            res = json.loads(r.read().decode())
    except Exception as e:  # noqa: BLE001
        return _bad(f"Overpass API に接続できませんでした: {e}", 502)
    items = store.load("pois", [])
    existing = {(x.get("osm_id")) for x in items if x.get("osm_id")}
    created = 0
    for el in res.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        osm_id = f"{el['type']}/{el['id']}"
        if osm_id in existing:
            continue
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if not lat:
            continue
        am = tags.get("amenity")
        t = ("hospital" if am == "hospital" else "clinic" if am == "clinic" else "city_hall" if am == "townhall"
             else "care" if am == "social_facility" else "station" if tags.get("railway") == "station" else "other")
        addr = " ".join(x for x in [tags.get("addr:province", ""), tags.get("addr:city", ""),
                                    tags.get("addr:quarter", ""), tags.get("addr:neighbourhood", ""),
                                    tags.get("addr:block_number", ""), tags.get("addr:housenumber", "")] if x)
        poi = {"id": store.new_id("poi"), "type": t, "name": name, "address": addr, "lat": lat, "lon": lon,
               "tel": tags.get("phone", ""), "url": tags.get("website", ""), "memo": "OSM取込", "capacity": "",
               "osm_id": osm_id, "pref": tags.get("addr:province", ""), "city": tags.get("addr:city", ""),
               "created_at": store.now_iso()}
        if not poi["pref"]:
            poi.update({k: v for k, v in extract.split_address(addr).items() if v and k != "address"})
        items.append(poi)
        created += 1
    store.save("pois", items)
    return jsonify({"created": created, "found": len(res.get("elements", []))})


# ---------------------------------------------------------------------------
# 統計（人口など） CSV
# ---------------------------------------------------------------------------

@app.route("/api/stats")
@auth.require_role("viewer")
def list_stats():
    items = store.load("stats", [])
    q = request.args
    if q.get("pref"):
        items = [x for x in items if x.get("pref") == q["pref"]]
    if q.get("city"):
        items = [x for x in items if x.get("city") == q["city"]]
    return jsonify(items)


@app.route("/api/stats/import", methods=["POST"])
@auth.require_role("member")
def import_stats():
    """統計CSV取込。必須列: 都道府県, 市区町村。その他の列は指標として保存（e-Stat/自治体CSV想定）。"""
    f = request.files.get("file")
    if not f:
        return _bad("CSVファイルを選択してください")
    try:
        rows = _read_csv(f)
    except ValueError as e:
        return _bad(str(e))
    dataset = request.form.get("dataset") or f.filename
    items = [x for x in store.load("stats", []) if x.get("dataset") != dataset]
    created = 0
    for row in rows:
        pref = _pick(row, ["都道府県", "都道府県名", "pref"])
        city = _pick(row, ["市区町村", "市区町村名", "市町村", "city"])
        if not city:
            continue
        metrics = {}
        for k, v in row.items():
            if not k or k.strip() in ("都道府県", "都道府県名", "pref", "市区町村", "市区町村名", "市町村", "city"):
                continue
            v = (v or "").strip().replace(",", "")
            try:
                metrics[k.strip()] = float(v) if "." in v else int(v)
            except ValueError:
                if v:
                    metrics[k.strip()] = v
        items.append({"id": store.new_id("stat"), "dataset": dataset, "pref": pref, "city": city,
                      "metrics": metrics, "imported_at": store.today()})
        created += 1
    store.save("stats", items)
    return jsonify({"created": created, "dataset": dataset})


@app.route("/api/stats/datasets", methods=["GET"])
@auth.require_role("viewer")
def stats_datasets():
    items = store.load("stats", [])
    ds = {}
    for x in items:
        ds.setdefault(x["dataset"], 0)
        ds[x["dataset"]] += 1
    return jsonify([{"dataset": k, "rows": v} for k, v in ds.items()])


@app.route("/api/stats/datasets/<path:name>", methods=["DELETE"])
@auth.require_role("admin")
def delete_dataset(name):
    items = [x for x in store.load("stats", []) if x.get("dataset") != name]
    store.save("stats", items)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# スケジュール / ダッシュボード / ダイジェスト
# ---------------------------------------------------------------------------

_SCHED_LABEL = {"viewing_date": "内見", "survey_date": "現調", "approval_date": "稟議承認",
                "contract_date": "契約", "construction_start": "着工", "construction_end": "竣工",
                "opening_date": "開業"}


def schedule_events(props: list[dict]) -> list[dict]:
    ev = []
    for p in props:
        for k, lab in _SCHED_LABEL.items():
            d = (p.get("schedule") or {}).get(k)
            if d:
                ev.append({"date": d, "kind": "milestone", "key": k, "label": lab, "prop_id": p["id"],
                           "prop_name": p.get("name", ""), "status": p.get("status")})
        for t in p.get("tasks", []):
            if t.get("due"):
                ev.append({"date": t["due"], "kind": "task", "label": t["title"], "phase": t.get("phase"),
                           "done": t.get("done", False), "assignee": t.get("assignee", ""),
                           "prop_id": p["id"], "prop_name": p.get("name", ""), "task_id": t["id"]})
    ev.sort(key=lambda x: x["date"])
    return ev


@app.route("/api/schedule")
@auth.require_role("viewer")
def schedule():
    ev = schedule_events(load_props())
    fr, to = request.args.get("from"), request.args.get("to")
    if fr:
        ev = [e for e in ev if e["date"] >= fr]
    if to:
        ev = [e for e in ev if e["date"] <= to]
    return jsonify(ev)


@app.route("/api/dashboard")
@auth.require_role("viewer")
def dashboard():
    props = load_props()
    today = store.today()
    soon = (date.today() + timedelta(days=14)).isoformat()
    by_status = {k: 0 for k in domain.STATUS_KEYS}
    by_pref = {}
    for p in props:
        by_status[p.get("status", "desk")] = by_status.get(p.get("status", "desk"), 0) + 1
        by_pref[p.get("pref") or "未設定"] = by_pref.get(p.get("pref") or "未設定", 0) + 1
    ev = schedule_events(props)
    overdue = [e for e in ev if e["kind"] == "task" and not e["done"] and e["date"] < today]
    upcoming = [e for e in ev if today <= e["date"] <= soon and not (e["kind"] == "task" and e["done"])]
    recent = []
    for p in props:
        for h in p.get("history", [])[-5:]:
            recent.append({**h, "prop_id": p["id"], "prop_name": p.get("name", "")})
    recent.sort(key=lambda x: x["at"], reverse=True)
    openings = sorted([{"prop_id": p["id"], "name": p.get("name"), "date": p["schedule"].get("opening_date"),
                        "status": p["status"], "pref": p.get("pref"), "city": p.get("city")}
                       for p in props if p.get("schedule", {}).get("opening_date")], key=lambda x: x["date"])
    return jsonify({"by_status": by_status, "by_pref": by_pref, "total": len(props),
                    "overdue": overdue[:30], "upcoming": upcoming[:30], "recent": recent[:30],
                    "openings": openings[:20], "poi_count": len(store.load("pois", []))})


def run_digest() -> dict:
    props = load_props()
    today = store.today()
    days = int(store.load("settings", {}).get("digest_days_ahead", 7))
    soon = (date.today() + timedelta(days=days)).isoformat()
    two_weeks = (date.today() + timedelta(days=14)).isoformat()
    ev = schedule_events(props)
    overdue = [f"{e['prop_name']}: {e['label']}（期限 {e['date']}{' / ' + e['assignee'] if e.get('assignee') else ''}）"
               for e in ev if e["kind"] == "task" and not e["done"] and e["date"] < today]
    soon_l = [f"{e['prop_name']}: {e['label']}（{e['date']}{' / ' + e['assignee'] if e.get('assignee') else ''}）"
              for e in ev if e["kind"] == "task" and not e["done"] and today <= e["date"] <= soon]
    events = [f"{e['date']} {e['label']}: {e['prop_name']}" for e in ev
              if e["kind"] == "milestone" and today <= e["date"] <= two_weeks]
    sent = notify.digest(overdue, soon_l, events)
    return {"sent": sent, "overdue": len(overdue), "soon": len(soon_l), "events": len(events)}


@app.route("/api/cron/digest", methods=["GET", "POST"])
def cron_digest():
    """外部の無料cron（cron-job.org / GitHub Actions 等）から毎朝叩く。CRON_TOKEN で保護。"""
    token = os.environ.get("CRON_TOKEN") or store.load("settings", {}).get("cron_token", "")
    given = request.args.get("token") or request.headers.get("X-Cron-Token", "")
    if not token or given != token:
        if not auth.current_user() or auth.user_level(auth.current_user()) < 3:
            return _bad("unauthorized", 401)
    return jsonify(run_digest())


@app.route("/api/slack/test", methods=["POST"])
@auth.require_role("admin")
def slack_test():
    ok = notify.post(":white_check_mark: 孫LOVE からのテスト通知です。連携が完了しました。", sync=True)
    return jsonify({"ok": ok, "configured": bool(notify.webhook_url())})


@app.route("/api/slack/digest", methods=["POST"])
@auth.require_role("admin")
def slack_digest_now():
    return jsonify(run_digest())


# ---------------------------------------------------------------------------
# エクスポート（Googleスプレッドシート / Googleカレンダー）
# ---------------------------------------------------------------------------

@app.route("/api/export/properties.csv")
@auth.require_role("viewer")
def export_csv():
    props = load_props()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID", "物件名", "ステータス", "優先度", "担当", "都道府県", "市区町村", "住所", "緯度", "経度",
                "種別", "構造", "築年月", "延床(㎡)", "坪数", "居室数", "月額賃料", "用途地域",
                "内見日", "現調日", "契約日", "着工", "竣工", "開業予定日", "Driveフォルダ", "タスク完了/総数", "メモ"])
    for p in props:
        s, sc = p.get("spec", {}), p.get("schedule", {})
        w.writerow([p["id"], p.get("name"), domain.STATUS_LABEL.get(p.get("status"), ""), p.get("priority"),
                    p.get("assignee"), p.get("pref"), p.get("city"), p.get("address"), p.get("lat"), p.get("lon"),
                    s.get("property_type"), s.get("structure"), s.get("built_ym"), s.get("floor_area_sqm"),
                    s.get("floor_area_tsubo"), s.get("rooms_planned"), s.get("rent_yen"), s.get("zoning"),
                    sc.get("viewing_date"), sc.get("survey_date"), sc.get("contract_date"),
                    sc.get("construction_start"), sc.get("construction_end"), sc.get("opening_date"),
                    p.get("drive", {}).get("folder_url"),
                    f"{sum(1 for t in p.get('tasks', []) if t.get('done'))}/{len(p.get('tasks', []))}",
                    p.get("memo", "")])
    data = "﻿" + buf.getvalue()
    return Response(data, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=magolove_properties.csv"})


@app.route("/api/export/calendar.ics")
def export_ics():
    """Googleカレンダーに「URLで追加」できる iCal。ICS_TOKEN で保護（未設定時はログイン必須）。"""
    token = os.environ.get("ICS_TOKEN") or store.load("settings", {}).get("ics_token", "")
    if not (token and request.args.get("token") == token) and not auth.current_user():
        return _bad("unauthorized", 401)
    ev = schedule_events(load_props())
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//MagoLove//JP", "X-WR-CALNAME:孫LOVE 出店スケジュール"]
    for e in ev:
        if e["kind"] == "task" and e.get("done"):
            continue
        d = e["date"].replace("-", "")
        try:
            nxt = (datetime.strptime(e["date"], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y%m%d")
        except ValueError:
            continue
        uid = f"{e['prop_id']}-{e.get('task_id') or e.get('key')}@magolove"
        summary = f"[{e['prop_name']}] {e['label']}"
        lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTART;VALUE=DATE:{d}", f"DTEND;VALUE=DATE:{nxt}",
                  f"SUMMARY:{summary}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return Response("\r\n".join(lines), mimetype="text/calendar; charset=utf-8")


# ---------------------------------------------------------------------------
# 設定 / ユーザー（管理者）
# ---------------------------------------------------------------------------

_SETTING_KEYS = ("app_url", "slack_webhook_url", "zenrin_tile_url", "google_maps_api_key", "google_api_key",
                 "drive_root_url", "default_center", "default_zoom", "notify_on_create", "notify_on_status",
                 "notify_on_report", "notify_on_schedule", "digest_days_ahead", "cron_token", "ics_token")


@app.route("/api/settings", methods=["GET", "PUT"])
@auth.require_role("admin")
def settings_api():
    s = store.load("settings", {})
    if request.method == "PUT":
        for k, v in (request.json or {}).items():
            if k in _SETTING_KEYS:
                s[k] = v
        store.save("settings", s)
    masked = dict(s)
    if masked.get("slack_webhook_url"):
        masked["slack_webhook_url_masked"] = masked["slack_webhook_url"][:35] + "…"
    return jsonify(masked)


@app.route("/api/users", methods=["GET", "POST"])
@auth.require_role("admin")
def users_api():
    users = auth.load_users()
    if request.method == "POST":
        d = request.json or {}
        email = (d.get("email") or "").strip().lower()
        if not email or "@" not in email:
            return _bad("メールアドレスが不正です")
        if any(u["email"] == email for u in users):
            return _bad("既に登録済みです")
        users.append({"email": email, "name": d.get("name") or email.split("@")[0],
                      "role": d.get("role") if d.get("role") in auth.ROLE_LEVEL else "member",
                      "active": True, "created_at": store.now_iso()})
        auth.save_users(users)
    return jsonify(users)


@app.route("/api/users/<path:email>", methods=["PUT", "DELETE"])
@auth.require_role("admin")
def user_detail(email):
    users = auth.load_users()
    u = next((x for x in users if x["email"] == email.lower()), None)
    if not u:
        return _bad("not found", 404)
    if request.method == "DELETE":
        if u["email"] == me().get("email"):
            return _bad("自分自身は削除できません")
        users.remove(u)
    else:
        d = request.json or {}
        for k in ("name", "role", "active"):
            if k in d:
                u[k] = d[k]
    auth.save_users(users)
    return jsonify(users)


@app.route("/api/geocode")
@auth.require_role("viewer")
def api_geocode():
    lat, lon = geocode(request.args.get("q", ""))
    return jsonify({"lat": lat, "lon": lon})


@app.route("/healthz")
def healthz():
    return "ok"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
