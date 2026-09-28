"""環境変数から設定を読む。秘密情報はここ以外で参照しない。

Phase 3（FANZA 手動投稿アシスト）: X への投稿は人間が行う。X API は READ ONLY（App-only Bearer）。
X の書込権限（OAuth 1.0a の 4 キー）は設定項目として存在しない。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _flag(name: str, default: bool = False) -> bool:
    v = _env(name, "1" if default else "0").lower()
    return v in ("1", "true", "yes", "on")


def _load_dotenv(path: Path) -> None:
    """.env があれば読み込む（既存の環境変数は上書きしない）。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


_load_dotenv(BASE_DIR / ".env")


@dataclass
class Settings:
    # --- 実行 ---
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", str(BASE_DIR / "data"))))
    timezone: str = field(default_factory=lambda: _env("TZ_NAME", "Asia/Tokyo"))

    # --- DMM / FANZA ---
    dmm_api_id: str = field(default_factory=lambda: _env("DMM_API_ID"))
    dmm_affiliate_id: str = field(default_factory=lambda: _env("DMM_AFFILIATE_ID"))
    dmm_site: str = field(default_factory=lambda: _env("DMM_SITE", "FANZA"))
    dmm_service: str = field(default_factory=lambda: _env("DMM_SERVICE", "digital"))
    dmm_floor: str = field(default_factory=lambda: _env("DMM_FLOOR", "videoa"))
    dmm_payout_rate: float = field(default_factory=lambda: float(_env("DMM_PAYOUT_RATE", "0.20")))
    dmm_media_registered: bool = field(default_factory=lambda: _flag("DMM_MEDIA_REGISTERED", False))

    # --- X（READ ONLY: App-only Bearer Token。投稿権限は持たない）---
    x_bearer_token: str = field(default_factory=lambda: _env("X_BEARER_TOKEN"))
    x_username: str = field(default_factory=lambda: _env("X_USERNAME", ""))   # 自分のアカウント（@なし）
    x_account_name: str = field(default_factory=lambda: _env("X_ACCOUNT_NAME", "main"))
    posts_per_day: int = field(default_factory=lambda: int(_env("POSTS_PER_DAY", "5")))
    min_post_interval_min: int = field(default_factory=lambda: int(_env("MIN_POST_INTERVAL_MIN", "120")))
    disclosure_text: str = field(default_factory=lambda: _env("DISCLOSURE_TEXT", "【PR】"))
    metric_milestones_hours: tuple = field(default_factory=lambda: tuple(int(x) for x in _env("METRIC_MILESTONES_HOURS", "24,72").split(",") if x.strip()))

    # --- AI ---
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    model_sonnet: str = field(default_factory=lambda: _env("MODEL_SONNET", "claude-sonnet-5"))
    model_opus: str = field(default_factory=lambda: _env("MODEL_OPUS", "claude-opus-5-5"))
    model_fable: str = field(default_factory=lambda: _env("MODEL_FABLE", "claude-fable-5-1"))
    usd_jpy: float = field(default_factory=lambda: float(_env("USD_JPY", "150")))
    daily_ai_budget_jpy: float = field(default_factory=lambda: float(_env("DAILY_AI_BUDGET_JPY", "300")))

    # --- 帰属 ---
    attribution_window_hours: int = field(default_factory=lambda: int(_env("ATTRIBUTION_WINDOW_HOURS", "72")))

    # --- 通知（Human Attention Queue）---
    slack_webhook_url: str = field(default_factory=lambda: _env("SLACK_WEBHOOK_URL", ""))
    notify_console_delivery: bool = field(default_factory=lambda: _flag("NOTIFY_CONSOLE_DELIVERY", False))

    # --- X API 読取価格（USD）。既定は 2026-09 の公式 pay-per-use。DB の settings.x_pricing が優先 ---
    x_price_read_post_usd: float = field(default_factory=lambda: float(_env("X_PRICE_READ_POST_USD", "0.005")))
    x_price_owned_read_usd: float = field(default_factory=lambda: float(_env("X_PRICE_OWNED_READ_USD", "0.001")))
    x_price_read_user_usd: float = field(default_factory=lambda: float(_env("X_PRICE_READ_USER_USD", "0.010")))

    # --- 固定費（月額、円）---
    infra_cost_month_jpy: float = field(default_factory=lambda: float(_env("INFRA_COST_MONTH_JPY", "0")))
    other_cost_month_jpy: float = field(default_factory=lambda: float(_env("OTHER_COST_MONTH_JPY", "0")))

    # --- Web UI ---
    web_port: int = field(default_factory=lambda: int(_env("WEB_PORT", "8500")))
    web_token: str = field(default_factory=lambda: _env("WEB_TOKEN", ""))   # 任意: 簡易アクセストークン

    @property
    def db_path(self) -> Path:
        return self.data_dir / "affiliate.sqlite3"

    @property
    def is_adult_site(self) -> bool:
        return self.dmm_site.upper() == "FANZA"

    def x_read_available(self) -> bool:
        return bool(self.x_bearer_token)

    def dmm_credentials_present(self) -> bool:
        return bool(self.dmm_api_id and self.dmm_affiliate_id)


def load_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s
