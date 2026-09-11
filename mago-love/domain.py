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
        "有料老人ホーム設置運営指導指針との適合確認", "検査済証・建築計画概要書の確認（建築課）",
        "ハザードマップ判定（洪水・土砂・津波）と避難確保計画の要否", "指定道路調書・接道の確認（道路課）",
        "埋蔵文化財包蔵地の照会（教育委員会）", "上下水道台帳・インフラの確認",
    ],
    "permit": [
        "都道府県への事前相談", "有料老人ホーム設置届 提出",
        "特定施設入居者生活介護 指定申請（該当時）", "消防署への届出・検査", "保健所への届出",
        "介護保険事業者指定（訪問介護等）",
    ],
    "hiring": [
        "施設長候補の選定", "介護事業者（訪問介護・看護）との提携", "採用計画・求人票作成",
        "ジョブメドレー等の求人媒体に掲載", "人材紹介会社・ハローワークへ依頼", "面接・採用決定", "研修計画・入社手続き",
    ],
    "leads": [
        "チラシ・パンフレット作成", "近隣の居宅介護支援事業所（ケアマネ）リスト作成",
        "居宅介護支援事業所へ訪問・斡旋依頼", "病院（地域連携室・MSW）への訪問・チラシ配布",
        "紹介会社（端末）への物件登録", "内覧会・説明会の開催", "入居申込・契約",
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
DOC_TYPES = ["稟議書", "収支計画", "マイソク・図面", "謄本・公図", "ハザードマップ・調査資料", "道路関係",
             "建物関係", "インフラ関係", "賃貸事例", "買付証明", "契約書", "決済書類", "申請書類",
             "見積書", "内見報告", "現調報告", "チラシ", "その他"]

# 物件フォルダの標準構成（既存ドライブ「春日部（シェアハウス）」の構成を踏襲）
DRIVE_FOLDERS = ["謄本・公図", "道路関係", "建物関係", "インフラ関係", "賃貸事例",
                 "購入/買付", "購入/契約", "購入/決済", "売却/契約", "売却/決済", "稟議・収支", "申請・届出"]

# 工程ごとの外部リンク（採用媒体・斡旋先・行政）
PHASE_LINKS = {
    "acquire": [("不動産情報ライブラリ（地価・取引価格）", "https://www.reinfolib.mlit.go.jp/"),
                ("登記情報提供サービス", "https://www1.touki.or.jp/")],
    "legal": [("重ねるハザードマップ", "https://disaportal.gsi.go.jp/"),
              ("国土数値情報（用途地域）", "https://nlftp.mlit.go.jp/ksj/")],
    "permit": [("厚労省 有料老人ホーム", "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/hukushi_kaigo/kaigo_koureisha/yuryou/index.html")],
    "hiring": [("ジョブメドレー（求人掲載）", "https://job-medley.com/"),
               ("Indeed", "https://jp.indeed.com/"), ("ハローワーク求人", "https://www.hellowork.mhlw.go.jp/")],
    "leads": [("介護サービス情報公表システム（居宅介護支援事業所検索）", "https://www.kaigokensaku.mhlw.go.jp/")],
    "interior": [], "open": [],
}

# 営業先（入居者獲得）のステータス
OUTREACH_STATUSES = [
    {"key": "todo", "label": "未訪問"}, {"key": "flyer", "label": "チラシ配布済"},
    {"key": "visited", "label": "訪問済"}, {"key": "requested", "label": "斡旋依頼済"},
    {"key": "referral", "label": "紹介あり"}, {"key": "ng", "label": "見込みなし"},
]

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
        "transaction_type": "賃貸",  # 賃貸 / 売買
        "price_yen": None,          # 売買価格
        "land_price_sqm": None,     # 公示地価（円/㎡）近傍標準地
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
    "survey": {},                   # 自動調査結果（標高・地盤・ハザード）
    "outreach": [],                 # 営業先 [{id, name, type, poi_id, status, date, memo}]
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


# --- パートナーキャラクター（育成ゲーム要素） ---
# 画像は管理者が設定画面からアップロード（data/characters/<id>.png）。未設定時は絵文字アバター。
CHARACTERS = [
    {"id": "ruka", "post": "map", "name": "ルカ", "species": "オオカミ", "emoji": "🐺", "color": "#64748b",
     "role": "物件ハンター", "phases": ["acquire", "interior"],
     "personality": "行動派で決断が早い。良い物件の匂いを嗅ぎ分ける。",
     "lines": {
         "greet": ["おはよ！今日はどの街を攻める？", "いい物件は足で探すもんだよ。行こ！", "内見の準備できてる？図面持った？"],
         "idle": ["坪単価が安くて、ケアマネ事業所が近い。それが狙い目。", "机上候補が溜まってきたら、まず内見予定に上げよう。", "ハザードマップ判定はワンクリックでできるよ。"],
         "praise": ["やるじゃん！その調子！", "ナイス！次いこ次！", "完璧。オレも見習わないと。"],
         "warn": ["期限切れのタスクがあるよ。先に片付けよ？", "内見日が近いよ。忘れてない？"],
     }},
    {"id": "haruto", "post": "board", "name": "ハルト施設長", "species": "ウサギ", "emoji": "🐰", "color": "#1e40af",
     "role": "施設長・申請担当", "phases": ["legal", "permit", "open"],
     "personality": "冷静で几帳面。法規制と役所手続きに強い。",
     "lines": {
         "greet": ["おはようございます。今日の予定を確認しましょう。", "書類の準備は計画的に。焦らず一つずつ。", "本日もよろしくお願いします。"],
         "idle": ["有料老人ホームは設置届が必要です。都道府県への事前相談を早めに。", "浸水想定区域なら避難確保計画が義務になります。", "検査済証の有無は必ず建築課で確認しましょう。"],
         "praise": ["素晴らしい。着実に進んでいますね。", "完了ですね。次の工程へ進みましょう。", "見事です。開業が近づいてきました。"],
         "warn": ["期限を過ぎたタスクがあります。優先して対応しましょう。", "申請の期限に注意してください。"],
     }},
    {"id": "kotaro", "post": "journal", "name": "コタロウ", "species": "クマ", "emoji": "🐻", "color": "#16a34a",
     "role": "介護スタッフ・採用担当", "phases": ["hiring"],
     "personality": "素直で人懐っこい。現場と採用のことなら任せて。",
     "lines": {
         "greet": ["おはようございます！今日もがんばりましょう！", "スタッフさんの採用、進んでますか？", "元気に行きましょう！"],
         "idle": ["ジョブメドレーに求人を出すと応募が来やすいですよ。", "施設長候補は早めに決めると開業がスムーズです。", "訪問介護・訪問看護との提携も忘れずに！"],
         "praise": ["わあ、すごいです！", "やりましたね！ぼくもうれしいです！", "その調子です！"],
         "warn": ["期限が過ぎているタスクがあります…一緒に片付けましょう！", "採用の締切、近いですよ！"],
     }},
    {"id": "momo", "post": "pois", "name": "モモ", "species": "イヌ", "emoji": "🐶", "color": "#e0475b",
     "role": "入居者獲得・営業担当", "phases": ["leads"],
     "personality": "明るく社交的。ケアマネさんや病院との関係づくりが得意。",
     "lines": {
         "greet": ["おはよう〜！今日はどこのケアマネさんに会いに行く？", "チラシ持った？行ってらっしゃい！", "笑顔が一番の営業ツールだよ♪"],
         "idle": ["居宅介護支援事業所からの斡旋が入居の近道！", "病院の地域連携室にも顔を出しておこうね。", "営業先リストは物件の「営業先」タブから作れるよ。"],
         "praise": ["すご〜い！さすが！", "やったね！お祝いしよ！", "その調子♪ 入居者さん増えそう！"],
         "warn": ["期限切れのタスクがあるみたい…先に片付けよ？", "内覧会の準備、間に合う？"],
     }},
]
CHARACTER_IDS = [c["id"] for c in CHARACTERS]

# 経験値（履歴アクションごと）とレベル閾値
XP_RULES = {"created": 20, "status": 50, "task_done": 10, "report": 30, "doc_add": 5, "outreach": 15, "survey": 15}
LEVEL_TITLES = [(1, "見習い出店担当"), (3, "出店プランナー"), (6, "エリア開拓者"), (10, "エリアマネージャー"),
                (15, "出店の達人"), (20, "孫LOVEマスター")]


def level_for_xp(xp: int) -> dict:
    """XP → レベル（必要XPは 100, 150, 200, ... と漸増）。"""
    level, need, acc = 1, 100, 0
    while xp >= acc + need and level < 50:
        acc += need
        level += 1
        need += 50
    title = LEVEL_TITLES[0][1]
    for lv, t in LEVEL_TITLES:
        if level >= lv:
            title = t
    return {"level": level, "xp": xp, "xp_in_level": xp - acc, "xp_next": need, "title": title}

# --- キャラクターの表情バリエーション（元画像1枚から画像生成AIで作る） ---
EXPRESSIONS = [
    {"key": "normal",    "label": "通常",     "prompt": "neutral friendly expression, standing naturally"},
    {"key": "happy",     "label": "笑顔",     "prompt": "big happy smile, eyes closed with joy, one hand raised in a cheerful wave"},
    {"key": "cheer",     "label": "応援",     "prompt": "excited cheering pose with both fists raised, sparkling eyes, very energetic"},
    {"key": "surprised", "label": "驚き",     "prompt": "surprised expression, wide eyes, mouth open, hands slightly raised"},
    {"key": "thinking",  "label": "考え中",   "prompt": "thoughtful expression, one hand on chin, looking slightly upward"},
    {"key": "worried",   "label": "心配",     "prompt": "worried and apologetic expression, eyebrows raised, hands clasped in front"},
    {"key": "sleepy",    "label": "眠い",     "prompt": "sleepy expression, yawning, rubbing one eye, relaxed posture"},
    # ポーズ（ギルドホールの中で座る・歩くために使う。横向き・左向きで生成）
    {"key": "sit",       "label": "座る",     "pose": True,
     "prompt": "sitting on a simple wooden chair seen from the side, body facing left, relaxed posture, hands resting on lap, gentle smile, full body including the chair"},
    {"key": "walk",      "label": "歩く",     "pose": True,
     "prompt": "walking pose mid-stride seen from the side, body facing left, one arm swinging naturally, looking ahead with a light smile, full body"},
]
EXPRESSION_KEYS = [e["key"] for e in EXPRESSIONS]

# --- ギルドの部屋（ハブ画面）から移動できる場所。x/y は CSS 描画ホールでの配置（%）。
#     photo: 実写風ホール画像（16:9 の参考画像）上で光るピンの位置、stand: キャラが立つ足元 [x%, y%, 身長%]、pose: 到着時のポーズ、npc: 持ち場の仲間が立つ位置 ---
SCENES = [
    {"id": "hall",     "view": "dashboard", "label": "ギルドホール",  "icon": "🏰", "x": 50, "y": 50,
     "photo": {"x": 50, "y": 50}, "stand": [43, 78, 30], "pose": "sit",
     "tagline": "出店クエストの本部", "mood": "warm",
     "prompt": "A grand fantasy guild hall interior at golden hour, wide angle, empty (no people), warm candlelight and sunbeams through tall windows, wooden beams, a large map table in the center-left, a quest notice board on the right wall, bookshelves, a brass clock, crates near the door, soft depth of field, painterly anime background art style (like a high-quality JRPG cutscene), 16:9, no text"},
    {"id": "map",      "view": "map",       "label": "ワールドマップ", "icon": "🗺️", "x": 18, "y": 70,
     "photo": {"x": 26, "y": 57}, "stand": [43, 78, 30], "npc": [35, 80, 30], "pose": "sit",
     "tagline": "地図の机 ・ 物件と街を見渡す", "mood": "cool",
     "prompt": "A cartographer's room in a fantasy guild, an enormous parchment map spread on an oak table with compasses, magnifying glass and brass instruments, moonlight and blue-teal magical glow, empty (no people), painterly anime background art, 16:9, no text"},
    {"id": "board",    "view": "board",     "label": "クエスト掲示板", "icon": "📜", "x": 38, "y": 44,
     "photo": {"x": 90, "y": 36}, "stand": [87, 67, 31], "npc": [79, 66, 30],
     "tagline": "掲示板 ・ 案件の進み具合", "mood": "amber",
     "prompt": "A wooden quest notice board in a fantasy guild hall covered with parchment scrolls, wax seals and pinned notes, warm amber lantern light, empty (no people), painterly anime background art, 16:9, no text"},
    {"id": "list",     "view": "list",      "label": "物件図鑑",       "icon": "📖", "x": 10, "y": 52,
     "photo": {"x": 27, "y": 39}, "stand": [30, 64, 26],
     "tagline": "書庫 ・ すべての物件の記録", "mood": "green",
     "prompt": "A cozy fantasy library alcove with tall bookshelves, leather-bound tomes, an open illustrated encyclopedia on a lectern, green-gold lamplight, dust motes, empty (no people), painterly anime background art, 16:9, no text"},
    {"id": "schedule", "view": "schedule",  "label": "冒険の暦",       "icon": "🕰️", "x": 64, "y": 18,
     "photo": {"x": 71, "y": 13}, "stand": [58, 60, 23],
     "tagline": "大時計 ・ 予定と期限", "mood": "violet",
     "prompt": "A fantasy clock tower interior with a giant brass astronomical clock, gears, hanging calendars and star charts, night sky through the window, violet and indigo tones, empty (no people), painterly anime background art, 16:9, no text"},
    {"id": "import",   "view": "import",    "label": "素材の搬入",     "icon": "📦", "x": 68, "y": 68,
     "photo": {"x": 80, "y": 61}, "stand": [80, 71, 32],
     "tagline": "倉庫 ・ 資料を持ち込む", "mood": "brown",
     "prompt": "A fantasy guild storeroom with wooden crates, rolled blueprints, scrolls and a delivery cart, warm brown tones, lantern light, empty (no people), painterly anime background art, 16:9, no text"},
    {"id": "pois",     "view": "pois",      "label": "街の施設",       "icon": "🏥", "x": 38, "y": 70,
     "photo": {"x": 67, "y": 42}, "stand": [67, 58, 20], "npc": [72, 59, 20],
     "tagline": "街へ出る ・ 病院・役所・事業所", "mood": "sunset",
     "prompt": "A charming fantasy town street at sunset seen from the guild entrance, a clinic with a red cross sign, a town hall with a clock, small shops, warm orange light, empty (no people), painterly anime background art, 16:9, no text"},
    {"id": "stats",    "view": "stats",     "label": "領地の統計",     "icon": "📈", "x": 46, "y": 18,
     "photo": {"x": 5, "y": 55}, "stand": [10, 76, 34],
     "tagline": "観測所 ・ 街の人口と需要", "mood": "indigo",
     "prompt": "A fantasy observatory room with a brass telescope, glowing star charts, floating holographic graphs and population maps, deep indigo and cyan light, empty (no people), painterly anime background art, 16:9, no text"},
    {"id": "journal",  "view": "journal",   "label": "ギルド日誌",     "icon": "📯", "x": 56, "y": 70,
     "photo": {"x": 12, "y": 42}, "stand": [11, 69, 28], "npc": [20, 71, 29],
     "tagline": "受付の台帳 ・ 進捗と最近の動き", "mood": "warm",
     "prompt": "A fantasy guild receptionist's desk with an open ledger, quill, candle, wax seals and stacked letters, warm golden light, empty (no people), painterly anime background art, 16:9, no text"},
    {"id": "settings", "view": "settings",  "label": "ギルド設定",     "icon": "⚙️", "x": 64, "y": 44,
     "photo": {"x": 48, "y": 40}, "stand": [50, 59, 22],
     "tagline": "受付 ・ 仲間と連携の設定", "mood": "stone",
     "prompt": "A fantasy guild reception desk with a brass bell, ledgers, a key rack and a stone wall with hanging crests, neutral gray-gold tones, empty (no people), painterly anime background art, 16:9, no text"},
]
SCENE_IDS = [s["id"] for s in SCENES]

# UI 素材スロット（管理者がアップロード or 生成）
UI_ASSETS = [
    {"id": "dialog_frame", "label": "セリフ枠（会話ボックス）", "size": "1024×512 / PNG 透過推奨",
     "prompt": "A fantasy RPG dialogue box frame, ornate gold filigree border with rounded corners on a dark navy semi-transparent panel, empty inside, symmetrical, clean edges, game UI asset, transparent background, 2:1, no text"},
    {"id": "button", "label": "ボタン素材", "size": "512×160 / PNG 透過推奨",
     "prompt": "A fantasy RPG UI button, rounded rectangle, rose-pink to crimson gradient with gold trim and a subtle inner glow, empty (no text), game UI asset, transparent background, 3:1"},
    {"id": "logo", "label": "ロゴ・紋章", "size": "1024×1024 / PNG 透過",
     "prompt": "A guild emblem for a caring senior-home company named 孫LOVE: a warm heart with a small house and a sprout, gold and rose-pink metallic, fantasy RPG crest style, centered, transparent background, no text"},
]
UI_ASSET_IDS = [a["id"] for a in UI_ASSETS]
