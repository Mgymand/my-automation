"""模倣優先モード: 既存の FANZA アフィ投稿で成果が出ている「型」を、できるだけ忠実に再現する。

再現するもの（表現ではなく形式・方法。誰の著作物でもない部分）:
  行構成・各行の役割・数字の種類と位置・業界の定型句・記号/絵文字の使い方・ハッシュタグ・CTA 位置・
  リンクの置き場所（本文 / リプ欄）・メディア種別・投稿時刻・テーマ
再現しないもの:
  1 つのアカウントにしか無い言い回し（その人の表現）、他者の画像・動画（素材は DMM 公式のみ）、アカウント名・キャラクター

仕組み（すべて決定論的。LLM は ⟦FREE⟧ の穴埋めにだけ任意で使う）:
  1. 調査投稿の数字・作品名・女優名・ジャンル・日付・主張（半額 / 本日まで 等）をスロットに置き換えて「骨格」を作る
  2. 骨格に文字として残すのは、業界の定型句と「3 アカウント以上が使っている語句」だけ。それ以外は ⟦FREE⟧
  3. 同じ骨格の投稿を束ね、成果（外れ値スコア）× 再現性（使っているアカウント数）で採点する
  4. 自分の商品の事実だけで骨格を埋める。事実が無いスロット（期限・順位・尺 等）や満たせない主張がある骨格は使わない
  5. 元投稿と似すぎる結果（類似度 0.6 以上）は使わない
  6. 骨格ごとに Pattern（SK_…）を登録し、自分の成果で Thompson Sampling が勝ち骨格へ寄せる
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .compliance import find_ng_words
from .db import Database, dumps, loads, utcnow
from .llm import LLMRouter, LLMUnavailable
from .patterns import add_pattern
from .research import ACTRESS_RE, GENRE_WORDS
from .similarity import jaccard

MAX_SOURCE_SIMILARITY = 0.6          # 元投稿との類似度がこれ以上なら使わない（コピー防止）
MIN_COMMON_AUTHORS = 3               # この数以上のアカウントが使う語句は「業界の定型句」として残す
TZ = ZoneInfo("Asia/Tokyo")

# 誰のものでもない定型句（ジャンル全体で使われる言い回し・機能語）。骨格にそのまま残す
CONVENTIONS = {
    "セール", "セール中", "セール速報", "期間限定", "今だけ", "まで", "迄", "配信", "配信開始", "配信中", "新作", "新着", "本日配信",
    "詳細", "詳細は", "リプ欄", "リプ欄から", "リプ欄へ", "リプ欄に", "こちら", "こちらから", "チェック", "サンプル", "サンプル動画",
    "出演", "レビュー", "評価", "平均", "人気", "おすすめ", "今日の1本", "今夜の1本", "今日の一本", "今夜の一本", "値下げ", "値下がり",
    "価格", "通常", "定価", "現在", "OFF", "off", "オフ", "円", "位", "件", "本", "選", "作品", "ランキング", "本日の", "本日",
    "まとめ", "安い順", "FANZA", "ファンザ", "動画", "単体", "さん", "ちゃん", "はこちら", "今すぐ", "続きは", "続き", "無料", "サンプル画像", "ベスト", "総集編", "シリーズ", "最新作", "第", "弾", "広告", "PR",
    "で買える", "買える", "は", "が", "の", "に", "を", "も", "で", "と", "から", "より", "中", "込み", "税込",
}
GENERIC_TAGS = {"FANZA", "ファンザ", "PR", "広告", "セール", "FANZAセール", "新作", "AV", "AV女優"}
# 事実で裏付けが要る主張（満たせない商品には使わない）
CLAIMS = {
    "半額": "half", "50%OFF以上": "half", "期間限定": "limited", "今だけ": "limited", "セール中": "limited", "キャンペーン中": "limited",
    "本日まで": "today_end", "今日まで": "today_end", "本日終了": "today_end", "今日終了": "today_end", "本日配信": "new", "配信開始": "new",
    "新作": "new", "新着": "new", "無料で立ち読み": "tachiyomi", "無料立ち読み": "tachiyomi", "立ち読み": "tachiyomi",
    "無料で試し読み": "tachiyomi", "試し読み": "tachiyomi", "最安": "never", "最安値": "never", "過去最安": "never", "史上最安": "never", "独占": "never", "限定公開": "never",
}
HARD = {"PRICE", "LIST_PRICE", "DISC", "END_DATE", "END_TIME", "REL_DATE", "RANK", "RAVG", "RCOUNT", "DURATION", "COUNT", "NUM", "TIME", "TITLE"}
SOFT = {"ACTRESS", "GENRE"}
SLOT = re.compile(r"⟦([A-Z_]+)(?::([^⟧]*))?⟧")
DELIMS = re.compile(r"([。、，,！!？?\s｜|／/・…↓👇→⇒➡:：〜~（）()\[\]【】「」『』★☆♪✨🔥💥⚡️☀-➿\U0001F300-\U0001FAFF]+)")
NUM = r"(\d{1,3}(?:,\d{3})+|\d+)"

SKELETON_SCHEMA = """
CREATE TABLE IF NOT EXISTS skeletons (
  pattern_id TEXT PRIMARY KEY, skeleton TEXT NOT NULL, category TEXT, n_posts INTEGER, n_authors INTEGER,
  perf REAL, reproducibility REAL, fidelity REAL DEFAULT 1, score REAL, media_type TEXT, image_count INTEGER DEFAULT 1, link_in TEXT, hours_jst TEXT, avg_length INTEGER,
  example_ids TEXT, source TEXT, updated_at TEXT NOT NULL
);
"""

# 2026-09 の公開調査（docs/ACCOUNT_RESEARCH.md §7）で観測した型。調査データが無い間の初期値で、実データの骨格に順次置き換わる
SEED_SKELETONS = [   # (骨格, 型, 観測アカウント数, メディア, 画像枚数, 出所)
    ("⟦DISC⟧｜⟦PRICE⟧\n⟦TITLE⟧\n⟦GENRE⟧／⟦ACTRESS⟧\n⟦END_DATE⟧ ⟦END_TIME⟧まで\n詳細はリプ欄", "セール速報型", 6, "image", 1, "observed:2026-09"),
    ("⟦DISC⟧｜⟦PRICE⟧\n⟦TITLE⟧\n⟦GENRE⟧／⟦ACTRESS⟧\n詳細はリプ欄", "セール速報型", 6, "image", 1, "observed:2026-09"),
    ("⟦LIST_PRICE⟧→⟦PRICE⟧\n⟦TITLE⟧\n⟦GENRE⟧\nリプ欄から", "激安・価格訴求型", 4, "image", 1, "observed:2026-09"),
    ("⟦ACTRESS⟧\n⟦TITLE⟧\n⟦PRICE⟧｜⟦GENRE⟧\nリプ欄から", "女優訴求型", 3, "image", 1, "observed:2026-09"),
    ("⟦REL_DATE⟧ ⟦CLAIM:配信開始⟧\n⟦TITLE⟧\n⟦ACTRESS⟧｜⟦GENRE⟧\n⟦PRICE⟧", "新作訴求型", 4, "image", 1, "observed:2026-09"),
    ("レビュー⟦RCOUNT⟧・平均⟦RAVG⟧\n⟦TITLE⟧\n⟦GENRE⟧", "掘り出し物型", 2, "image", 1, "observed:2026-09"),
    ("⟦TITLE⟧\nサンプル動画👇", "動画主導型", 2, "video", 1, "observed:2026-09"),
    ("⟦TITLE⟧｜⟦GENRE⟧｜⟦PRICE⟧", "短文型", 2, "image", 1, "observed:2026-09"),
    # 運営者の観測（2026-11）: 購入前に無料で見られる立ち読み / サンプル画像を複数枚添えて購買を促す投稿が多い
    ("⟦TITLE⟧\n⟦CLAIM:無料で立ち読み⟧\n⟦PRICE⟧\n続きはリプ欄", "立ち読み画像型", 3, "image", 4, "observed:2026-11"),
    ("⟦TITLE⟧\n⟦ACTRESS⟧｜⟦GENRE⟧\n⟦PRICE⟧\n続きはリプ欄", "サンプル画像型", 3, "image", 4, "observed:2026-11"),
]


def ensure_schema(db: Database) -> None:
    db.conn.executescript(SKELETON_SCHEMA)
    cols = {r["name"] for r in db.q("PRAGMA table_info(skeletons)")}
    if "fidelity" not in cols:
        db.exec("ALTER TABLE skeletons ADD COLUMN fidelity REAL DEFAULT 1")
    if "image_count" not in cols:
        db.exec("ALTER TABLE skeletons ADD COLUMN image_count INTEGER DEFAULT 1")


# ---------------------------------------------------------------- 骨格の抽出
def _slotify(line: str, known_titles: list[str], known_actresses: list[str]) -> str:
    s = re.sub(r"(今日|今夜|本日)の\s*1\s*本", r"\1の一本", line)      # 数字を含む定型句は数字スロットにしない
    for name in sorted(known_actresses, key=len, reverse=True):
        if len(name) >= 2 and name in s:
            s = s.replace(name, "⟦ACTRESS⟧")
    for t in sorted(known_titles, key=len, reverse=True):
        if len(t) >= 8 and t in s:
            s = s.replace(t, "⟦TITLE⟧")
    s = re.sub(r"「[^「」]{2,}」", "「⟦TITLE⟧」", s)
    s = re.sub(r"『[^『』]{2,}』", "『⟦TITLE⟧』", s)
    s = re.sub(NUM + r"\s*円\s*(?:→|⇒|->|➡️?)\s*" + NUM + r"\s*円", "⟦LIST_PRICE⟧→⟦PRICE⟧", s)
    s = re.sub(NUM + r"\s*円", "⟦PRICE⟧", s)
    s = re.sub(r"\d{1,2}\s*[%％]\s*(?:OFF|off|Off|オフ)?", "⟦DISC⟧", s)
    deadline = bool(re.search(r"まで|迄|締切|終了|〆", s))
    s = re.sub(r"\d{1,2}\s*/\s*\d{1,2}|\d{1,2}月\d{1,2}日", "⟦END_DATE⟧" if deadline else "⟦REL_DATE⟧", s)
    s = re.sub(r"\d{1,2}:\d{2}", "⟦END_TIME⟧" if deadline else "⟦TIME⟧", s)
    s = re.sub(r"\d{1,3}\s*位", "⟦RANK⟧", s)
    s = re.sub(r"(平均|★|☆)\s*\d\.\d", r"\1⟦RAVG⟧", s)
    s = re.sub(r"\d{1,5}\s*件", "⟦RCOUNT⟧", s)
    s = re.sub(r"\d+\s*(?:分|時間)", "⟦DURATION⟧", s)
    s = re.sub(r"\d+\s*(?:本|作品|選)", "⟦COUNT⟧", s)
    s = re.sub(r"\d+", "⟦NUM⟧", s)
    s = ACTRESS_RE.sub(lambda m: "⟦ACTRESS⟧" + m.group(0)[len(m.group(1)):], s)
    for phrase in sorted(CLAIMS, key=len, reverse=True):
        s = s.replace(phrase, f"⟦CLAIM:{phrase}⟧")
    for g in sorted(GENRE_WORDS, key=len, reverse=True):
        s = s.replace(g, "⟦GENRE⟧")
    return re.sub(r"(⟦GENRE⟧)(?:\s*⟦GENRE⟧)+", r"\1", s)


def _chunks(slotted: str) -> list[tuple[str, str]]:
    """('slot'|'delim'|'text', 値) の列に分解。"""
    out: list[tuple[str, str]] = []
    pos = 0
    for m in SLOT.finditer(slotted):
        out += _split_literal(slotted[pos:m.start()])
        out.append(("slot", m.group(0)))
        pos = m.end()
    out += _split_literal(slotted[pos:])
    return out


def _split_literal(s: str) -> list[tuple[str, str]]:
    return [("delim" if DELIMS.fullmatch(p) else "text", p) for p in DELIMS.split(s) if p]


def prepare(text: str, known_titles: list[str] | None = None, known_actresses: list[str] | None = None) -> dict:
    """投稿を行ごとにスロット化（定型句判定の前段）。"""
    body = text or ""
    link_in = "body" if re.search(r"https?://", body) else "reply"
    body = re.sub(r"https?://\S+", "", body)
    body = re.sub(r"【PR】|［PR］|\[PR\]|（PR）|\(PR\)|#PR\b|＃PR\b", "⟦PR⟧", body)

    def tag(m):
        t = m.group(1)
        if t in GENERIC_TAGS:
            return "#" + t
        return "#⟦GENRE⟧" if t in GENRE_WORDS else ""
    body = re.sub(r"[#＃](\S+)", tag, body)
    lines = [_slotify(ln.strip(), known_titles or [], known_actresses or []) for ln in body.split("\n")]
    return {"lines": [ln for ln in lines if ln.strip()], "link_in": link_in}


PARTICLES = set("はがのにをもでとへや")


def _segment(chunk: str, keep: set[str]) -> list[tuple[str, str]]:
    """定型句（2 文字以上）を最長一致で拾い、残りを FREE にする。"""
    if chunk.startswith("#") or chunk in keep:
        return [("keep", chunk)]
    out: list[tuple[str, str]] = []
    i, buf = 0, ""
    longest = max((len(k) for k in keep), default=0)
    while i < len(chunk):
        hit = next((chunk[i:i + n] for n in range(min(longest, len(chunk) - i), 1, -1) if chunk[i:i + n] in keep), None)
        if hit:
            if buf:
                out.append(("free", buf)); buf = ""
            out.append(("keep", hit)); i += len(hit)
        else:
            buf += chunk[i]; i += 1
    if buf:
        out.append(("free", buf))
    return out


def _line_tokens(ln: str, keep: set[str]) -> list[tuple[str, str]]:
    toks: list[tuple[str, str]] = []
    for kind, val in _chunks(ln):
        toks += _segment(val, keep) if kind == "text" else [("keep", val)]
    return toks


CTA_WORDS = re.compile(r"リプ欄|詳細|こちら|チェック|まで|迄|↓|👇|プロフ|固定")


def _title_line(lines: list[str], keep: set[str]) -> int | None:
    """作品名が既知でも括弧付きでもない投稿で、作品名の行を推定する。
    価格・割引・期限・レビュー・主張・CTA を含まず、記号を除いて 10 字以上ある最も長い行（作品名は 1 行に置かれることが多い）。"""
    if any("⟦TITLE⟧" in ln for ln in lines):
        return None
    best, best_len = None, 0
    for i, ln in enumerate(lines):
        if re.search(r"⟦(PRICE|LIST_PRICE|DISC|END_DATE|END_TIME|REL_DATE|RAVG|RCOUNT|RANK|COUNT|CLAIM:[^⟧]*)⟧", ln) or CTA_WORDS.search(ln):
            continue
        n = len(DELIMS.sub("", SLOT.sub("xx", ln)))
        if n >= 10 and n > best_len:
            best, best_len = i, n
    return best


def skeletonize(prepared: dict, common: set[str]) -> str:
    keep = {c for c in CONVENTIONS | common if len(c) >= 2}
    title_i = _title_line(prepared["lines"], keep)
    out_lines = []
    for li, ln in enumerate(prepared["lines"]):
        if li == title_i:
            out_lines.append("⟦TITLE⟧")
            continue
        toks = _line_tokens(ln, keep)
        # 1 文字の助詞が FREE に挟まれているだけなら FREE に吸収（「⟦FREE⟧の⟦FREE⟧」のような断片を作らない）
        merged: list[list] = []
        for kind, val in toks:
            if kind == "free" and merged and merged[-1][0] == "free":
                merged[-1][1] += val
            elif kind == "keep" and val in PARTICLES and merged and merged[-1][0] == "free":
                merged[-1][1] += val
            else:
                merged.append([kind, val])
        line = "".join(f"⟦FREE:{len(v)}⟧" if k == "free" else v for k, v in merged)
        out_lines.append(re.sub(r"⟦FREE:(\d+)⟧((?:[はがのにをもでとへや])?)⟦FREE:(\d+)⟧", lambda m: f"⟦FREE:{int(m.group(1)) + int(m.group(3)) + len(m.group(2))}⟧", line).strip())
    return "\n".join(x for x in out_lines if x)


def literal_chunks(prepared: dict) -> set[str]:
    return {v for ln in prepared["lines"] for k, v in _chunks(ln) if k == "text" and len(v) >= 2}


COMMERCIAL = {"TITLE", "ACTRESS", "PRICE", "LIST_PRICE", "DISC", "RAVG", "RCOUNT", "REL_DATE", "END_DATE"}


def has_fact_slot(skeleton: str) -> bool:
    """商品を特定できる / 買う理由になる事実スロットを 1 つ以上含むか（ジャンルだけの骨格は再現しても商品紹介にならない）。"""
    return any(m.group(1) in COMMERCIAL for m in SLOT.finditer(skeleton))


def fidelity(skeleton: str, original_len: int) -> float:
    """元投稿のうち再現できる割合（= 1 − 固有表現の文字数 / 全文字数）。固有表現頼みで伸びた投稿ほど低い。"""
    free = sum(int(x) for x in re.findall(r"⟦FREE:(\d+)⟧", skeleton))
    return round(max(0.0, 1 - free / max(original_len, 1)), 3)


# ---------------------------------------------------------------- 骨格の集計と登録
def rebuild(db: Database, limit: int = 400) -> dict:
    ensure_schema(db)
    titles = [r["title"] for r in db.q("SELECT title FROM products WHERE title IS NOT NULL LIMIT 2000")]
    actresses = sorted({a for r in db.q("SELECT actresses FROM products") for a in loads(r["actresses"], [])})
    rows = [dict(r) for r in db.q("SELECT * FROM research_posts WHERE views>0 AND text IS NOT NULL ORDER BY outlier_score DESC LIMIT ?", (limit,))]
    prepared = [(r, prepare(r["text"], titles, actresses)) for r in rows]
    authors_by_chunk: dict[str, set[str]] = {}
    for r, p in prepared:
        who = r.get("author_username") or r.get("author_id") or r["x_post_id"]
        for c in literal_chunks(p):
            authors_by_chunk.setdefault(c, set()).add(str(who))
    common = {c for c, a in authors_by_chunk.items() if len(a) >= MIN_COMMON_AUTHORS}
    groups: dict[str, dict] = {}
    max_out = max((float(r["outlier_score"] or 0) for r in rows), default=0) or 1.0
    for r, p in prepared:
        sk = skeletonize(p, common)
        if not sk or not has_fact_slot(sk):
            continue
        g = groups.setdefault(sk, {"posts": [], "authors": set(), "link": [], "media": [], "hours": [], "len": [], "fid": []})
        g["fid"].append(fidelity(sk, len(re.sub(r"https?://\S+", "", r["text"]).strip())))
        g["posts"].append(r)
        g["authors"].add(str(r.get("author_username") or r.get("author_id") or r["x_post_id"]))
        g["link"].append(p["link_in"])
        f = loads(r.get("features"), {})
        g["media"].append("video" if f.get("has_video") else ("image" if f.get("image_count") or f.get("media_types") else "none"))
        g.setdefault("imgs", []).append(int(f.get("image_count") or 0))
        g["len"].append(int(f.get("length") or len(r["text"])))
        try:
            g["hours"].append(datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00")).astimezone(TZ).hour)
        except (TypeError, ValueError):
            pass
    n = 0
    for sk, g in groups.items():
        perf = sum(float(r["outlier_score"] or 0) for r in g["posts"]) / len(g["posts"]) / max_out
        repro = min(1.0, (len(g["authors"]) + 0.25 * (len(g["posts"]) - len(g["authors"]))) / MIN_COMMON_AUTHORS)
        cat = max({r["category"] for r in g["posts"]}, key=lambda c: sum(1 for r in g["posts"] if r["category"] == c))
        fid = sum(g["fid"]) / len(g["fid"])
        if fid < 0.4:          # 半分以上が固有表現の投稿は「型」では再現できない（偶然要因・表現力で伸びたもの）
            continue
        _store(db, sk, cat, len(g["posts"]), len(g["authors"]), perf, repro, _mode(g["media"]), _mode(g["link"]),
               sorted(set(g["hours"])), int(sum(g["len"]) / len(g["len"])), [r["x_post_id"] for r in g["posts"][:5]], "research", fid,
               image_count=max(1, min(4, sorted(g["imgs"])[len(g["imgs"]) // 2])))
        n += 1
    seeds = ensure_seeds(db)
    db.set_setting("replicate_rebuilt_at", utcnow())
    return {"research_posts": len(rows), "skeletons": n, "seeds": seeds, "common_phrases": len(common)}


def ensure_seeds(db: Database) -> int:
    ensure_schema(db)
    n = 0
    for sk, cat, authors, media_type, images, src in SEED_SKELETONS:
        if not db.one("SELECT 1 FROM skeletons WHERE skeleton=?", (sk,)):
            _store(db, sk, cat, authors, authors, 0.35, min(1.0, authors / MIN_COMMON_AUTHORS), media_type, "reply", [21, 22, 20], 70, [], src,
                   image_count=images)
            n += 1
    return n


def _mode(xs: list[str]) -> str:
    return max(set(xs), key=xs.count) if xs else "image"


def _store(db: Database, sk: str, cat: str, n_posts: int, n_authors: int, perf: float, repro: float, media_type: str, link_in: str,
           hours: list[int], avg_len: int, example_ids: list[str], source: str, fid: float = 1.0, image_count: int = 1) -> str:
    """スコア = 成果（外れ値スコアの相対値）×（0.5 + 0.5 × 再現性）× 忠実度。"""
    pid = "SK_" + hashlib.sha1(sk.encode("utf-8")).hexdigest()[:8]
    score = round(perf * (0.5 + 0.5 * repro) * fid, 4)
    db.exec("""INSERT INTO skeletons(pattern_id,skeleton,category,n_posts,n_authors,perf,reproducibility,fidelity,score,media_type,link_in,hours_jst,
               avg_length,example_ids,source,updated_at,image_count) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(pattern_id) DO UPDATE SET n_posts=excluded.n_posts, n_authors=excluded.n_authors, perf=excluded.perf,
               reproducibility=excluded.reproducibility, fidelity=excluded.fidelity, score=excluded.score, media_type=excluded.media_type,
               link_in=excluded.link_in, hours_jst=excluded.hours_jst, avg_length=excluded.avg_length, example_ids=excluded.example_ids,
               updated_at=excluded.updated_at, image_count=excluded.image_count""",
            (pid, sk, cat, n_posts, n_authors, round(perf, 4), round(repro, 3), fid, score, media_type, link_in, dumps(hours), avg_len,
             dumps(example_ids), source, utcnow(), int(image_count)))
    lines = sk.split("\n")
    add_pattern(db, {"pattern_id": pid, "pattern_name": f"再現: {cat}（{n_authors} アカウント）", "category": cat, "hook": lines[0],
                     "body_structure": " / ".join(lines), "cta_structure": lines[-1], "media_type": media_type, "ideal_length": avg_len,
                     "ideal_hours": hours or [21, 22]}, source=f"replicate:{source}", confidence=round(0.2 + 0.6 * score, 3))
    db.exec("UPDATE patterns SET trend_score=?, confidence=MAX(confidence, ?), media_type=?, updated_at=? WHERE pattern_id=?",
            (round(perf, 4), round(0.2 + 0.6 * score, 3), media_type, utcnow(), pid))
    return pid


def top_skeletons(db: Database, limit: int = 20) -> list[dict]:
    ensure_schema(db)
    return [dict(r) for r in db.q("SELECT * FROM skeletons ORDER BY score DESC, n_authors DESC LIMIT ?", (limit,))]


# ---------------------------------------------------------------- 骨格を自分の事実で埋める
def _campaign_end(p: dict) -> datetime | None:
    camps = p.get("campaign") or []
    if isinstance(camps, str):
        camps = loads(camps, [])
    ends = []
    for c in camps:
        v = (c or {}).get("date_end") if isinstance(c, dict) else None
        if v:
            try:
                ends.append(datetime.fromisoformat(str(v).replace(" ", "T")).replace(tzinfo=TZ))
            except ValueError:
                pass
    return min(ends) if ends else None


def _facts(p: dict, now: datetime) -> dict:
    price, lst = p.get("price"), p.get("list_price")
    disc = float(p.get("discount_rate") or 0)
    end = _campaign_end(p)
    rel = str(p.get("release_date") or "")[:10]
    try:
        rel_d = datetime.fromisoformat(rel).date() if rel else None
    except ValueError:
        rel_d = None
    genres = [g for g in (p.get("genres") or []) if g and not find_ng_words(g)]
    imgs = p.get("sample_image_urls") or []
    imgs = loads(imgs, []) if isinstance(imgs, str) else imgs
    # 「立ち読み」と言えるのは、無料立ち読みがある商品（API の tachiyomi）か、同人・電子書籍でサンプルページが 2 枚以上ある商品だけ
    tachiyomi = bool(p.get("tachiyomi_url")) or (str(p.get("service") or "") in ("doujin", "ebook") and len(imgs) >= 2)
    return {
        "PRICE": f"{int(price):,}円" if price else None,
        "LIST_PRICE": f"{int(lst):,}円" if (lst and price and lst > price) else None,
        "DISC": f"{int(round(disc * 100))}%OFF" if disc >= 0.05 else None,
        "END_DATE": f"{end.month}/{end.day}" if end and end > now else None,
        "END_TIME": f"{end.hour}:{end.minute:02d}" if end and end > now else None,
        "REL_DATE": f"{rel_d.month}/{rel_d.day}" if rel_d else None,
        "RAVG": f"{float(p['review_avg']):.1f}" if p.get("review_avg") and int(p.get("review_count") or 0) >= 5 else None,
        "RCOUNT": f"{int(p['review_count'])}件" if int(p.get("review_count") or 0) >= 5 else None,
        "TITLE": p.get("title"), "ACTRESS": list(p.get("actresses") or []), "GENRE": genres,
        "_claims": {"half": disc >= 0.5, "limited": bool(end and end > now) or disc >= 0.05,
                    "today_end": bool(end and now < end and end.date() == now.date()),
                    "new": bool(rel_d and timedelta(0) <= (now.date() - rel_d) <= timedelta(days=7)), "tachiyomi": tachiyomi, "never": False},
    }


@dataclass
class Rendered:
    text: str | None
    missing: list[str]
    template_with_free: str = ""          # FREE を残したままのテンプレート（LLM 穴埋め用）


FREE_TOK = re.compile(r"[はがのにをもでとへや]?⟦FREE:(\d+)⟧[はがのにをもでとへや]?")


def render(skeleton: str, p: dict, now: datetime | None = None, max_len: int = 140) -> Rendered:
    """骨格を商品の事実で埋める。事実が無いハードスロット・裏付けの無い主張があれば None（その商品には使わない）。
    ⟦FREE:n⟧（元投稿の固有表現）は文字として再現しない。行の半分以上が FREE の行は落とす（1 行目だけはジャンルの一言に置換）。"""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    f = _facts(p, now)
    missing: list[str] = []
    counters = {"ACTRESS": 0, "GENRE": 0}

    def sub(m):
        name, arg = m.group(1), m.group(2)
        if name == "PR":
            return "【PR】"
        if name == "FREE":
            return m.group(0)
        if name == "CLAIM":
            if f["_claims"].get(CLAIMS.get(arg or "", "never")):
                return arg
            missing.append(f"主張「{arg}」の裏付けなし")
            return ""
        if name in SOFT:
            i = counters[name]
            counters[name] += 1
            return f[name][i] if i < len(f[name]) else "⟦DROP⟧"
        v = f.get(name)
        if not v:
            missing.append(name)
            return ""
        return v

    out_lines, tmpl_lines = [], []
    for li, line in enumerate(skeleton.split("\n")):
        whole = re.fullmatch(r"\s*⟦(ACTRESS|GENRE)⟧\s*", line)
        filled = SLOT.sub(sub, line)
        if whole and "⟦DROP⟧" in filled:            # 1 行まるごとが出演者 / ジャンルの型（女優訴求など）で、その事実が無い
            missing.append(whole.group(1))
        filled = re.sub(r"([／/｜|・、])?\s*⟦DROP⟧\s*([／/｜|・、])?", lambda m: m.group(1) if (m.group(1) and m.group(2)) else "", filled)
        filled = re.sub(r"^[／/｜|・、\s]+|[／/｜|・、\s]+$", "", filled)
        free_n = sum(int(x) for x in re.findall(r"⟦FREE:(\d+)⟧", filled))
        kept = FREE_TOK.sub("", filled)
        kept_n = len(re.sub(r"[\s。、！!？?…・｜|／/]", "", kept))
        if not kept_n or (free_n and free_n > kept_n):
            if li == 0 and free_n and f["GENRE"]:
                out_lines.append(f"{f['GENRE'][0]}の一本。")
                tmpl_lines.append(filled)
            continue
        kept = re.sub(r"([。、！!？?])[。、！!？?\s]*\1", r"\1", kept)
        out_lines.append(re.sub(r"^[。、！!？?\s]+", "", kept).strip())
        tmpl_lines.append(filled)
    if missing:
        return Rendered(None, missing)
    text = "\n".join(x for x in out_lines if x)
    if "【PR】" not in text:
        text += "【PR】" if text.endswith(("。", "！", "!")) else "\n【PR】"
    if len(text) > max_len and f["TITLE"] and f["TITLE"] in text:
        over = len(text) - max_len
        text = text.replace(f["TITLE"], f["TITLE"][: max(12, len(f["TITLE"]) - over - 1)] + "…")
    return Rendered(text, [], "\n".join(tmpl_lines))


def fill_free_with_llm(llm: LLMRouter, rendered: Rendered, p: dict) -> str | None:
    """⟦FREE⟧（元投稿の固有表現だった部分）を、商品の事実だけを使った短い句で埋める。骨格の他の部分は 1 文字も変えさせない。"""
    if "⟦FREE:" not in rendered.template_with_free:
        return None
    facts = {k: p.get(k) for k in ("title", "price", "list_price", "discount_rate", "release_date", "review_count", "review_avg")}
    facts.update(genres=(p.get("genres") or [])[:4], actresses=(p.get("actresses") or [])[:2])
    try:
        res = llm.call("sonnet", "日本語 SNS の短文ライター。⟦FREE:n⟧ の部分だけを、与えた商品データから言える n 字程度の自然な句に置き換える。"
                       "新しい事実・評価・場面描写・露骨な表現は書かない。⟦FREE:n⟧ 以外の文字は一切変えない。JSON のみ。",
                       f"テンプレート:\n{rendered.template_with_free}\n\n商品データ:\n{dumps(facts)}",
                       schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False},
                       max_tokens=400, ref=f"replica_free:{p.get('content_id')}")
        text = ((res.parsed or {}).get("text") or "").strip()
    except LLMUnavailable:
        return None
    pos = 0
    for part in [x.strip() for x in re.split(r"⟦FREE:\d+⟧", rendered.template_with_free.replace("⟦DROP⟧", "")) if x.strip()]:
        i = text.find(part, pos)
        if i < 0:
            return None
        pos = i + len(part)
    if "⟦" in text or find_ng_words(text):
        return None
    return text if "【PR】" in text else text + "\n【PR】"


def candidates_for(db: Database, llm: LLMRouter | None, p: dict, recent_texts: list[str], k: int = 3,
                   now: datetime | None = None) -> list[dict]:
    """この商品に使える骨格を成果順に最大 k 個、事実で埋めて返す。"""
    ensure_seeds(db)
    out: list[dict] = []
    pool = top_skeletons(db, 40)
    for distinct in (True, False):                      # 1 巡目は型（カテゴリ）を散らし、2 巡目で残り枠を埋める
        for sk in pool:
            if len(out) >= k:
                return out
            if any(o["pattern_id"] == sk["pattern_id"] for o in out) or (distinct and any(o["category"] == sk["category"] for o in out)):
                continue
            c = _fill(db, llm, sk, p, now)
            if c:
                out.append(c)
    return out


def _fill(db: Database, llm: LLMRouter | None, sk: dict, p: dict, now: datetime | None) -> dict | None:
    r = render(sk["skeleton"], p, now)
    if not r.text:
        return None
    text = r.text
    if llm is not None and getattr(llm, "enabled", False):
        text = fill_free_with_llm(llm, r, p) or text
    ids = loads(sk["example_ids"], [])
    sources = [x["text"] for x in db.q(f"SELECT text FROM research_posts WHERE x_post_id IN ({','.join('?' * len(ids))})", tuple(ids))] if ids else []
    src_sim = max((jaccard(text, s) for s in sources), default=0.0)
    if src_sim >= MAX_SOURCE_SIMILARITY:
        return None
    return {"pattern_id": sk["pattern_id"], "text": text, "skeleton": sk["skeleton"], "category": sk["category"],
            "link_in": sk["link_in"], "media_type": sk["media_type"], "n_authors": sk["n_authors"], "score": sk["score"],
            "source_similarity": round(src_sim, 3), "source": sk["source"]}


def skeleton_for_pattern(db: Database, pattern_id: str) -> dict | None:
    ensure_schema(db)
    r = db.one("SELECT * FROM skeletons WHERE pattern_id=?", (pattern_id,))
    return dict(r) if r else None


def describe(sk: dict) -> str:
    who = f"{sk['n_authors']} アカウント・{sk['n_posts']} 投稿" if sk["source"] == "research" else "2026-09 の公開調査で観測した型"
    link = "本文末" if sk["link_in"] == "body" else "リプ欄"
    media_s = "動画" if sk["media_type"] == "video" else (f"画像 {sk.get('image_count') or 1} 枚" if sk["media_type"] == "image" else "なし")
    who = "運営者の観測（2026-11）" if sk["source"] == "observed:2026-11" else who
    return f"再現元の型: {sk['category']}（{who}、成果スコア {sk['score']:.2f}）。リンクの置き場所: {link}。メディア: {media_s}"
