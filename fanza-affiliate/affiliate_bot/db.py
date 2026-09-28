"""SQLite スキーマとアクセス層。deterministic な処理は全てここを経由する。"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
  name TEXT PRIMARY KEY,
  theme TEXT NOT NULL,
  target_audience TEXT NOT NULL,
  content_strategy TEXT NOT NULL,
  x_user_id TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
  content_id TEXT PRIMARY KEY,
  site TEXT NOT NULL,
  service TEXT,
  floor TEXT,
  title TEXT NOT NULL,
  url TEXT,
  affiliate_url TEXT,
  image_url TEXT,
  sample_image_urls TEXT,   -- JSON list
  sample_movie_url TEXT,
  price REAL,
  list_price REAL,
  discount_rate REAL,
  release_date TEXT,
  review_count INTEGER,
  review_avg REAL,
  actresses TEXT,           -- JSON list
  genres TEXT,              -- JSON list
  maker TEXT,
  series TEXT,
  campaign TEXT,            -- JSON
  rank_position INTEGER,
  is_adult INTEGER NOT NULL DEFAULT 1,
  payout_rate REAL,
  erpi REAL,
  erpi_components TEXT,     -- JSON
  raw TEXT,
  fetched_at TEXT NOT NULL,
  last_posted_at TEXT
);

CREATE TABLE IF NOT EXISTS patterns (
  pattern_id TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  target TEXT,
  hook TEXT,
  structure TEXT,
  cta TEXT,
  media TEXT,
  best_hours TEXT,          -- JSON list of ints
  avg_views REAL DEFAULT 0,
  avg_ctr REAL DEFAULT 0,
  avg_cvr REAL DEFAULT 0,
  avg_epc REAL DEFAULT 0,
  uses INTEGER DEFAULT 0,
  recent30_views REAL DEFAULT 0,
  recent30_ctr REAL DEFAULT 0,
  recent30_epc REAL DEFAULT 0,
  recent30_profit REAL DEFAULT 0,
  confidence REAL DEFAULT 0.2,
  status TEXT NOT NULL DEFAULT 'active',
  source TEXT,
  last_used_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id TEXT NOT NULL,
  pattern_id TEXT NOT NULL,
  angle TEXT NOT NULL,
  text TEXT NOT NULL,
  reply_text TEXT,
  media_plan TEXT,          -- JSON
  scores TEXT,              -- JSON
  status TEXT NOT NULL DEFAULT 'new',   -- new|selected|rejected|rewrite
  model TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
  post_id INTEGER PRIMARY KEY AUTOINCREMENT,
  candidate_id INTEGER,
  account TEXT NOT NULL,
  product_id TEXT NOT NULL,
  pattern_id TEXT NOT NULL,
  genre TEXT,
  angle TEXT,
  text TEXT NOT NULL,
  reply_text TEXT,
  media_type TEXT,          -- none|image|video
  media_source TEXT,        -- DMM API の URL（権利確認の記録）
  scheduled_at TEXT NOT NULL,
  slot_hour INTEGER,
  posted_at TEXT,
  x_post_id TEXT,
  x_reply_id TEXT,
  tracking_code TEXT UNIQUE,
  status TEXT NOT NULL DEFAULT 'scheduled', -- scheduled|posted|failed|cancelled|blocked
  error TEXT,
  api_cost_jpy REAL DEFAULT 0,
  ai_cost_jpy REAL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS post_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id INTEGER NOT NULL,
  captured_at TEXT NOT NULL,
  views INTEGER DEFAULT 0,
  likes INTEGER DEFAULT 0,
  reposts INTEGER DEFAULT 0,
  replies INTEGER DEFAULT 0,
  quotes INTEGER DEFAULT 0,
  bookmarks INTEGER DEFAULT 0,
  profile_visits INTEGER DEFAULT 0,
  url_clicks INTEGER DEFAULT 0,
  FOREIGN KEY(post_id) REFERENCES posts(post_id)
);
CREATE INDEX IF NOT EXISTS idx_post_metrics_post ON post_metrics(post_id, captured_at);

CREATE TABLE IF NOT EXISTS clicks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tracking_code TEXT NOT NULL,
  ts TEXT NOT NULL,
  ua_hash TEXT,
  referer TEXT
);
CREATE INDEX IF NOT EXISTS idx_clicks_code ON clicks(tracking_code, ts);

CREATE TABLE IF NOT EXISTS conversions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  post_id INTEGER,
  product_id TEXT,
  revenue_jpy REAL NOT NULL,
  order_ref TEXT,
  source TEXT NOT NULL,     -- dmm_csv|manual|estimated
  attribution TEXT,         -- last_click|proportional|unattributed
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS costs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  kind TEXT NOT NULL,       -- ai|x_api|dmm_api|infra|other
  model TEXT,
  input_tokens INTEGER DEFAULT 0,
  output_tokens INTEGER DEFAULT 0,
  cache_read_tokens INTEGER DEFAULT 0,
  amount_jpy REAL NOT NULL,
  ref TEXT
);
CREATE INDEX IF NOT EXISTS idx_costs_ts ON costs(ts);

CREATE TABLE IF NOT EXISTS bandit_arms (
  dimension TEXT NOT NULL,
  arm TEXT NOT NULL,
  alpha REAL NOT NULL DEFAULT 1,
  beta REAL NOT NULL DEFAULT 1,
  n INTEGER NOT NULL DEFAULT 0,
  reward_sum REAL NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(dimension, arm)
);

CREATE TABLE IF NOT EXISTS experiments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  dimension TEXT NOT NULL,
  arms TEXT NOT NULL,       -- JSON list
  hypothesis TEXT,
  min_samples INTEGER DEFAULT 30,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  status TEXT NOT NULL DEFAULT 'running',
  result TEXT
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  level TEXT NOT NULL,      -- info|warn|halt
  code TEXT NOT NULL,
  message TEXT NOT NULL,
  data TEXT
);

CREATE TABLE IF NOT EXISTS research_posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  x_post_id TEXT UNIQUE,
  author_id TEXT,
  author_followers INTEGER,
  text TEXT,
  has_media INTEGER,
  media_type TEXT,
  created_at TEXT,
  captured_at TEXT NOT NULL,
  views INTEGER, likes INTEGER, reposts INTEGER, replies INTEGER, bookmarks INTEGER, quotes INTEGER,
  age_hours REAL,
  views_per_follower REAL,
  views_per_hour REAL,
  engagement_rate REAL,
  category TEXT,
  features TEXT             -- JSON: 抽象化した特徴（文章量・フック・CTA など）
);

CREATE TABLE IF NOT EXISTS daily_summary (
  day TEXT PRIMARY KEY,     -- JST の日付
  revenue_jpy REAL, profit_jpy REAL, clicks INTEGER, conversions INTEGER,
  views INTEGER, ctr REAL, cvr REAL, ai_cost_jpy REAL, api_cost_jpy REAL,
  best_pattern TEXT, best_product TEXT, posts INTEGER,
  report_md TEXT, created_at TEXT NOT NULL
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path, detect_types=sqlite3.PARSE_DECLTYPES)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)

    # ---- 基本 ----
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

    # ---- settings ----
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: Any) -> None:
        self.exec(
            "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, str(value), utcnow()),
        )

    # ---- events ----
    def log_event(self, level: str, code: str, message: str, data: dict | None = None) -> None:
        self.exec(
            "INSERT INTO events(ts,level,code,message,data) VALUES(?,?,?,?,?)",
            (utcnow(), level, code, message, json.dumps(data or {}, ensure_ascii=False)),
        )

    # ---- costs ----
    def add_cost(
        self,
        kind: str,
        amount_jpy: float,
        model: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        ref: str | None = None,
    ) -> None:
        self.exec(
            "INSERT INTO costs(ts,kind,model,input_tokens,output_tokens,cache_read_tokens,amount_jpy,ref) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (utcnow(), kind, model, input_tokens, output_tokens, cache_read_tokens, amount_jpy, ref),
        )

    def cost_between(self, start_iso: str, end_iso: str, kind: str | None = None) -> float:
        if kind:
            row = self.one(
                "SELECT COALESCE(SUM(amount_jpy),0) s FROM costs WHERE ts>=? AND ts<=? AND kind=?",
                (start_iso, end_iso, kind),
            )
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
