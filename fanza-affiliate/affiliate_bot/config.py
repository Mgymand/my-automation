"""環境変数から設定を読む。秘密情報はここ以外で参照しない。"""
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
    # --- 実行モード ---
    dry_run: bool = field(default_factory=lambda: _flag("DRY_RUN", True))
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", str(BASE_DIR / "data"))))
    timezone: str = field(default_factory=lambda: _env("TZ_NAME", "Asia/Tokyo"))

    # --- DMM / FANZA ---
    dmm_api_id: str = field(default_factory=lambda: _env("DMM_API_ID"))
    dmm_affiliate_id: str = field(default_factory=lambda: _env("DMM_AFFILIATE_ID"))
    # DMM.com（一般商品）が既定。FANZA（成人向け）は X 有料パートナーシップ方針により X 投稿が HARD BLOCK される
    dmm_site: str = field(default_factory=lambda: _env("DMM_SITE", "DMM.com"))  # DMM.com | FANZA
    dmm_service: str = field(default_factory=lambda: _env("DMM_SERVICE", "digital"))
    dmm_floor: str = field(default_factory=lambda: _env("DMM_FLOOR", "videoa"))
    dmm_payout_rate: float = field(default_factory=lambda: float(_env("DMM_PAYOUT_RATE", "0.20")))

    # --- X ---
    x_consumer_key: str = field(default_factory=lambda: _env("X_CONSUMER_KEY"))
    x_consumer_secret: str = field(default_factory=lambda: _env("X_CONSUMER_SECRET"))
    x_access_token: str = field(default_factory=lambda: _env("X_ACCESS_TOKEN"))
    x_access_token_secret: str = field(default_factory=lambda: _env("X_ACCESS_TOKEN_SECRET"))
    x_account_name: str = field(default_factory=lambda: _env("X_ACCOUNT_NAME", "main"))
    posts_per_day: int = field(default_factory=lambda: int(_env("POSTS_PER_DAY", "5")))
    min_post_interval_min: int = field(default_factory=lambda: int(_env("MIN_POST_INTERVAL_MIN", "90")))
    link_in_reply: bool = field(default_factory=lambda: _flag("LINK_IN_REPLY", True))
    disclosure_text: str = field(default_factory=lambda: _env("DISCLOSURE_TEXT", "【PR】"))
    use_paid_partnership_label: bool = field(default_factory=lambda: _flag("USE_PAID_PARTNERSHIP_LABEL", True))

    # --- コンプライアンス（人間が確認したら true にする。規約上の禁止事項はここでは解除できない） ---
    # 注意: 成人向け（FANZA）商品の X 投稿は policy.py の HARD BLOCK であり、設定フラグは存在しない。
    # X 設定「投稿するメディアをセンシティブな内容としてマーク」を有効化済みであることの人間確認
    sensitive_media_setting_confirmed: bool = field(
        default_factory=lambda: _flag("SENSITIVE_MEDIA_SETTING_CONFIRMED", False)
    )
    # DMM アフィリエイト管理画面に X アカウントを媒体登録済みであることの人間確認
    dmm_media_registered: bool = field(default_factory=lambda: _flag("DMM_MEDIA_REGISTERED", False))

    # --- AI ---
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    model_sonnet: str = field(default_factory=lambda: _env("MODEL_SONNET", "claude-sonnet-5"))
    model_opus: str = field(default_factory=lambda: _env("MODEL_OPUS", "claude-opus-5-5"))
    model_fable: str = field(default_factory=lambda: _env("MODEL_FABLE", "claude-fable-5-1"))
    usd_jpy: float = field(default_factory=lambda: float(_env("USD_JPY", "150")))
    daily_ai_budget_jpy: float = field(default_factory=lambda: float(_env("DAILY_AI_BUDGET_JPY", "300")))

    # --- トラッキング ---
    tracking_base_url: str = field(default_factory=lambda: _env("TRACKING_BASE_URL", ""))
    tracking_secret: str = field(default_factory=lambda: _env("TRACKING_SECRET", ""))
    tracking_port: int = field(default_factory=lambda: int(_env("TRACKING_PORT", "8400")))
    attribution_window_hours: int = field(default_factory=lambda: int(_env("ATTRIBUTION_WINDOW_HOURS", "72")))

    # --- 通知（Human Attention Queue）---
    slack_webhook_url: str = field(default_factory=lambda: _env("SLACK_WEBHOOK_URL", ""))
    notify_email: str = field(default_factory=lambda: _env("NOTIFY_EMAIL", ""))

    # --- X API 価格（USD）。既定値は 2026-09 の公式 pay-per-use。DB の settings.x_pricing が優先される ---
    x_price_post_usd: float = field(default_factory=lambda: float(_env("X_PRICE_POST_USD", "0.015")))
    x_price_post_url_usd: float = field(default_factory=lambda: float(_env("X_PRICE_POST_URL_USD", "0.20")))
    x_price_read_post_usd: float = field(default_factory=lambda: float(_env("X_PRICE_READ_POST_USD", "0.005")))
    x_price_owned_read_usd: float = field(default_factory=lambda: float(_env("X_PRICE_OWNED_READ_USD", "0.001")))
    x_price_read_user_usd: float = field(default_factory=lambda: float(_env("X_PRICE_READ_USER_USD", "0.010")))

    # --- 固定費（月額、円） ---
    infra_cost_month_jpy: float = field(default_factory=lambda: float(_env("INFRA_COST_MONTH_JPY", "1000")))
    other_cost_month_jpy: float = field(default_factory=lambda: float(_env("OTHER_COST_MONTH_JPY", "0")))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "affiliate.sqlite3"

    @property
    def is_adult_site(self) -> bool:
        return self.dmm_site.upper() == "FANZA"

    def x_credentials_present(self) -> bool:
        return all([self.x_consumer_key, self.x_consumer_secret, self.x_access_token, self.x_access_token_secret])

    def dmm_credentials_present(self) -> bool:
        return bool(self.dmm_api_id and self.dmm_affiliate_id)


def load_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s
