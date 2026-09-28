"""SQLite スキーマとアクセス層。deterministic な処理は全てここを経由する。

Phase 3: posts は「人間が投稿する投稿パッケージ」。planned → posted（人間が posted --url で登録）→ 指標・成果が紐付く。
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
  name TEXT PRIMARY KEY, theme TEXT NOT NULL, target_audience TEXT NOT NULL, content_strategy TEXT NOT NULL,
  x_user_id TEXT, x_username TEXT, followers INTEGER, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
  content_id TEXT PRIMARY KEY,
  site TEXT NOT NULL, service TEXT, floor TEXT, title TEXT NOT NULL, url TEXT, affiliate_url TEXT,
  image_url TEXT, sample_image_urls TEXT, sample_movie_url TEXT,
  price REAL, list_price REAL, discount_rate REAL, release_date TEXT,
  review_count INTEGER, review_avg REAL, actresses TEXT, genres TEXT, maker TEXT, series TEXT, campaign TEXT,
  rank_position INTEGER, is_adult INTEGER NOT NULL DEFAULT 1, payout_rate REAL,
  eav REAL, eav_components TEXT, raw TEXT, fetched_at TEXT NOT NULL, last_posted_at TEXT
);

CREATE TABLE IF NOT EXISTS patterns (
  pattern_id TEXT PRIMARY KEY,
  pattern_name TEXT NOT NULL, category TEXT NOT NULL,
  hook TEXT, body_structure TEXT, cta_structure TEXT, media_type TEXT,
  ideal_length INTEGER, ideal_hours TEXT, target_genre TEXT, target_actress_type TEXT,
  avg_views REAL DEFAULT 0, views_per_follower REAL DEFAULT 0, engagement_rate REAL DEFAULT 0,
  ctr REAL DEFAULT 0, epc REAL DEFAULT 0, conversions INTEGER DEFAULT 0, profit REAL DEFAULT 0,
  uses INTEGER DEFAULT 0, confidence REAL DEFAULT 0.2, trend_score REAL DEFAULT 0, last_seen TEXT,
  recent30_views REAL DEFAULT 0, recent30_ctr REAL DEFAULT 0, recent30_epc REAL DEFAULT 0, recent30_profit REAL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active', source TEXT, last_used_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id TEXT NOT NULL, source_pattern_id TEXT NOT NULL, angle TEXT NOT NULL,
  text TEXT NOT NULL, hook_type TEXT, similarity_score REAL DEFAULT 0, rewrite_count INTEGER DEFAULT 0,
  scores TEXT, status TEXT NOT NULL DEFAULT 'new', model TEXT, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS media_assets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id TEXT NOT NULL, source_url TEXT NOT NULL, source_type TEXT NOT NULL,   -- sample_image|sample_movie|package|ai_card
  rights_status TEXT NOT NULL,                                                      -- ok|needs_check|ng
  media_kind TEXT NOT NULL,                                                         -- image|video
  note TEXT, created_at TEXT NOT NULL,
  UNIQUE(product_id, source_url)
);

CREATE TABLE IF NOT EXISTS posts (
  post_id INTEGER PRIMARY KEY AUTOINCREMENT,
  day TEXT NOT NULL,                       -- JST の日付（パッケージの日）
  seq INTEGER NOT NULL,                    -- その日の POST 番号
  candidate_id INTEGER, account TEXT NOT NULL, product_id TEXT NOT NULL, pattern_id TEXT NOT NULL,
  genre TEXT, angle TEXT, priority TEXT, text TEXT NOT NULL,
  alternatives TEXT,                       -- JSON: 代替案 1〜2
  media_asset_id INTEGER, media_type TEXT, media_source TEXT,
  reason TEXT, similar_post_id TEXT, similar_reason TEXT, notes TEXT,
  scheduled_at TEXT NOT NULL, slot_hour INTEGER,
  predicted TEXT,                          -- JSON: views/ctr/cvr/revenue
  status TEXT NOT NULL DEFAULT 'planned',  -- planned|posted|skipped
  x_post_id TEXT, x_url TEXT, posted_at TEXT,
  actual_text TEXT, actual_post_time TEXT, actual_media TEXT,
  ai_cost_jpy REAL DEFAULT 0, api_cost_jpy REAL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_posts_day ON posts(day, seq);
CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);

CREATE TABLE IF NOT EXISTS post_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id INTEGER NOT NULL, captured_at TEXT NOT NULL, milestone_hours INTEGER,     -- 6/24/72/168 or NULL(手動)
  source TEXT NOT NULL DEFAULT 'x_api',                                                  -- x_api|csv|manual
  views INTEGER DEFAULT 0, likes INTEGER DEFAULT 0, reposts INTEGER DEFAULT 0, replies INTEGER DEFAULT 0,
  quotes INTEGER DEFAULT 0, bookmarks INTEGER DEFAULT 0, profile_visits INTEGER DEFAULT 0, url_clicks INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_post_metrics_post ON post_metrics(post_id, captured_at);

CREATE TABLE IF NOT EXISTS conversions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL, post_id INTEGER, product_id TEXT, revenue_jpy REAL NOT NULL, order_ref TEXT, channel TEXT,
  source TEXT NOT NULL, attribution TEXT, attribution_confidence TEXT, attribution_share REAL DEFAULT 1.0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS costs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL, kind TEXT NOT NULL, model TEXT, input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0,
  cache_read_tokens INTEGER DEFAULT 0, amount_jpy REAL NOT NULL, ref TEXT
);
CREATE INDEX IF NOT EXISTS idx_costs_ts ON costs(ts);

CREATE TABLE IF NOT EXISTS bandit_arms (
  dimension TEXT NOT NULL, arm TEXT NOT NULL, alpha REAL NOT NULL DEFAULT 1, beta REAL NOT NULL DEFAULT 1,
  n INTEGER NOT NULL DEFAULT 0, reward_sum REAL NOT NULL DEFAULT 0, updated_at TEXT NOT NULL, PRIMARY KEY(dimension, arm)
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, level TEXT NOT NULL, code TEXT NOT NULL, message TEXT NOT NULL, data TEXT
);

CREATE TABLE IF NOT EXISTS research_posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  x_post_id TEXT UNIQUE, author_id TEXT, author_username TEXT, author_followers INTEGER,
  text TEXT, created_at TEXT, captured_at TEXT NOT NULL, age_hours REAL,
  views INTEGER, likes INTEGER, reposts INTEGER, replies INTEGER, bookmarks INTEGER, quotes INTEGER,
  views_per_follower REAL, views_per_hour REAL, engagement_rate REAL, likes_per_1k_views REAL, reposts_per_1k_views REAL,
  outlier_score REAL,
  category TEXT, hook_type TEXT, features TEXT, source TEXT NOT NULL DEFAULT 'x_api'
);

CREATE TABLE IF NOT EXISTS daily_summary (
  day TEXT PRIMARY KEY, revenue_jpy REAL, profit_jpy REAL, views INTEGER, conversions INTEGER, ctr REAL, epc REAL,
  ai_cost_jpy REAL, api_cost_jpy REAL, best_post INTEGER, worst_post INTEGER, posts INTEGER, report_md TEXT, created_at TEXT NOT NULL
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)
        # Web UI（単一スレッドの HTTPServer）から同じ接続を使うため check_same_thread=False
        self.conn = sqlite3.connect(self.path, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def q(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, params).fetchone()

    def exec(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur

    def close(self) -> None:
        self.conn.close()

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: Any) -> None:
        self.exec(
            "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, str(value), utcnow()),
        )

    def log_event(self, level: str, code: str, message: str, data: dict | None = None) -> None:
        self.exec("INSERT INTO events(ts,level,code,message,data) VALUES(?,?,?,?,?)",
                  (utcnow(), level, code, message, json.dumps(data or {}, ensure_ascii=False)))

    def add_cost(self, kind: str, amount_jpy: float, model: str | None = None, input_tokens: int = 0,
                 output_tokens: int = 0, cache_read_tokens: int = 0, ref: str | None = None) -> None:
        self.exec(
            "INSERT INTO costs(ts,kind,model,input_tokens,output_tokens,cache_read_tokens,amount_jpy,ref) VALUES(?,?,?,?,?,?,?,?)",
            (utcnow(), kind, model, input_tokens, output_tokens, cache_read_tokens, amount_jpy, ref),
        )

    def cost_between(self, start_iso: str, end_iso: str, kind: str | None = None) -> float:
        if kind:
            row = self.one("SELECT COALESCE(SUM(amount_jpy),0) s FROM costs WHERE ts>=? AND ts<=? AND kind=?", (start_iso, end_iso, kind))
        else:
            row = self.one("SELECT COALESCE(SUM(amount_jpy),0) s FROM costs WHERE ts>=? AND ts<=?", (start_iso, end_iso))
        return float(row["s"]) if row else 0.0


def loads(s: str | None, default: Any = None) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return default


def dumps(o: Any) -> str:
    return json.dumps(o, ensure_ascii=False, sort_keys=True)
