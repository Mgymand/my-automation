"""ドメイン定義: 物件ステータス・工程・統一フォーマット・タスクテンプレート。

すべてのエリア・すべての物件で同じフォーマット（PROPERTY_TEMPLATE）で保存し、
個別具体的な内容は memo / reports / docs に記載する方針。
"""
from __future__ import annotations

import copy

import store

# --- 物件ステータス（パイプライン順） ---
STATUSES = [
    {"key": "desk",    "label": "机上候補", "color": "#64748b"},
    {"key": "viewing", "label": "内見予定", "color": "#0ea5e9"},
    {"key": "survey",  "label": "現調予定", "color": "#8b5cf6"},
    {"key": "opening", "label": "開業予定", "color": "#f59e0b"},
    {"key": "opened",  "label": "開業済み", "color": "#16a34a"},
    {"key": "dropped", "label": "見送り",   "color": "#9ca3af"},
]
STATUS_KEYS = [s["key"] for s in STATUSES]
STATUS_LABEL = {s["key"]: s["label"] for s in STATUSES}

# --- 工程（フェーズ） ---
PHASES = [
    {"key": "acquire",  "label": "不動産仕入れ",   "icon": "🏢"},
    {"key": "legal",    "label": "法規制確認",     "icon": "📐"},
    {"key": "permit",   "label": "役所申請",       "icon": "🏛️"},
    {"key": "hiring",   "label": "介護事業者採用", "icon": "🧑‍⚕️"},
    {"key": "leads",    "label": "入居者獲得",     "icon": "📣"},
    {"key": "interior", "label": "内装工事",       "icon": "🔨"},
    {"key": "open",     "label": "開業準備",       "icon": "🎉"},
]
PHASE_KEYS = [p["key"] for p in PHASES]

# --- 工程ごとの標準タスク（物件作成時に自動生成。offset_days は基準日からの日数目安） ---
TASK_TEMPLATE = {
    "acquire": [
        "物件資料（マイソク・図面）取得", "賃料・条件の初期評価", "内見実施・内見報告",
        "現地調査（周辺環境・競合・導線）", "オーナー/元付と条件交渉", "稟議書作成・承認",
        "収支シミュレーション作成", "賃貸借契約締結",
    ],
    "legal": [
        "用途地域・建ぺい率/容積率の確認", "建築基準法（用途変更の要否）確認",
        "消防法（スプリンクラー・自火報）確認", "バリアフリー法・条例確認",
        "有料老人ホーム設置運営指導指針との適合確認", "検査済証・既存不適格の確認",
    ],
    "permit": [
        "都道府県への事前相談", "有料老人ホーム設置届 提出",
        "特定施設入居者生活介護 指定申請（該当時）", "消防署への届出・検査", "保健所への届出",
        "介護保険事業者指定（訪問介護等）",
    ],
    "hiring": [
        "施設長候補の選定", "介護事業者（訪問介護・看護）との提携", "採用計画・求人票作成",
        "求人媒体・紹介会社への掲載", "面接・採用決定", "研修計画・入社手続き",
    ],
    "leads": [
        "チラシ・パンフレット作成", "近隣ケアマネ事業所リスト作成・訪問",
        "病院（地域連携室・MSW）への訪問・チラシ配布", "紹介会社（端末）への物件登録",
        "内覧会・説明会の開催", "入居申込・契約",
    ],
    "interior": [
        "設計・レイアウト確定", "見積取得・業者選定", "工事契約", "着工",
        "中間検査", "竣工検査・引渡し",
    ],
    "open": [
        "什器・備品の調達", "運営マニュアル整備", "開業前の行政検査",
        "開業日の確定・告知", "開業",
    ],
}

# --- 施設（POI）種別 ---
POI_TYPES = [
    {"key": "city_hall",  "label": "市区町村役所", "color": "#2563eb"},
    {"key": "pref_office", "label": "県庁・都庁",  "color": "#7c3aed"},
    {"key": "hospital",   "label": "病院",         "color": "#dc2626"},
    {"key": "clinic",     "label": "クリニック",   "color": "#f97316"},
    {"key": "care",       "label": "介護施設（他社）", "color": "#059669"},
    {"key": "caremanager", "label": "居宅介護支援（ケアマネ）", "color": "#0d9488"},
    {"key": "station",    "label": "駅",           "color": "#334155"},
    {"key": "other",      "label": "その他",       "color": "#6b7280"},
]
POI_TYPE_KEYS = [p["key"] for p in POI_TYPES]

# --- 書類種別 ---
DOC_TYPES = ["稟議書", "収支計画", "マイソク・図面", "契約書", "内見報告", "現調報告",
             "申請書類", "見積書", "チラシ", "その他"]

# --- 物件の統一フォーマット ---
PROPERTY_TEMPLATE = {
    "id": None,
    "name": "",
    "status": "desk",
    "priority": "B",          # A/B/C
    "assignee": "",
    "region": "関東",
    "pref": "",
    "city": "",
    "ward": "",
    "address": "",
    "lat": None,
    "lon": None,
    "source": {"type": "manual", "filename": "", "url": "", "text": ""},
    "spec": {
        "property_type": "",        # 一棟貸/区分/土地/既存施設転用 等
        "structure": "",            # RC造 等
        "built_ym": "",             # YYYY-MM
        "floors": "",               # 地上3階
        "site_area_sqm": None,
        "floor_area_sqm": None,
        "floor_area_tsubo": None,
        "rooms_planned": None,      # 想定居室数
        "rent_yen": None,           # 月額賃料
        "management_fee_yen": None,
        "deposit": "",
        "key_money": "",
        "contract_type": "",        # 普通借家/定期借家
        "contract_years": "",
        "availability": "",
        "zoning": "",               # 用途地域
        "building_coverage": "",    # 建ぺい率
        "floor_area_ratio": "",     # 容積率
        "fire_zone": "",            # 防火地域
        "road_access": "",
        "parking": "",
        "elevator": "",
        "sprinkler": "",
        "stations": [],             # [{line, station, walk_min}]
        "source_company": "",
        "contact": "",
        "property_number": "",
    },
    "finance": {
        "capex_yen": None,          # 初期投資
        "monthly_rent_yen": None,
        "target_occupancy": None,   # %
        "monthly_revenue_yen": None,
        "monthly_profit_yen": None,
        "payback_months": None,
    },
    "schedule": {
        "viewing_date": "",
        "survey_date": "",
        "approval_date": "",        # 稟議承認
        "contract_date": "",
        "construction_start": "",
        "construction_end": "",
        "opening_date": "",
    },
    "drive": {"folder_url": "", "folder_id": ""},
    "docs": [],                     # [{id, type, title, url, drive_id, updated_at}]
    "tasks": [],                    # [{id, phase, title, done, due, assignee, done_at}]
    "reports": [],                  # [{id, type, date, author, summary, pros, cons, rating, url}]
    "tags": [],
    "memo": "",
    "history": [],                  # [{at, by, action, detail}]
    "created_at": "",
    "updated_at": "",
}


def new_property(payload: dict, by: str) -> dict:
    p = copy.deepcopy(PROPERTY_TEMPLATE)
    merge_property(p, payload)
    p["id"] = store.new_id("prop")
    p["created_at"] = p["updated_at"] = store.now_iso()
    if not p["tasks"]:
        p["tasks"] = default_tasks()
    p["history"] = [{"at": p["created_at"], "by": by, "action": "created", "detail": "物件を登録"}]
    return p


def merge_property(target: dict, payload: dict) -> None:
    """統一フォーマット内のキーだけを取り込む（未知キーは無視して形を守る）。"""
    for k, v in (payload or {}).items():
        if k not in PROPERTY_TEMPLATE or k in ("id", "created_at", "history"):
            continue
        if isinstance(PROPERTY_TEMPLATE[k], dict) and isinstance(v, dict):
            for kk, vv in v.items():
                if kk in PROPERTY_TEMPLATE[k] or k == "spec":
                    target[k][kk] = vv
        else:
            target[k] = v
    if target.get("status") not in STATUS_KEYS:
        target["status"] = "desk"


def default_tasks() -> list[dict]:
    tasks = []
    for phase in PHASE_KEYS:
        for title in TASK_TEMPLATE[phase]:
            tasks.append({"id": store.new_id("task"), "phase": phase, "title": title,
                          "done": False, "due": "", "assignee": "", "done_at": ""})
    return tasks
