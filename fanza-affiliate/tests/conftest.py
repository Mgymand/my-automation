import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from affiliate_bot.config import Settings  # noqa: E402
from affiliate_bot.db import Database  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path):
    """各テストで os.environ を復元し、DATA_DIR をテスト用ディレクトリに向ける。"""
    saved = dict(os.environ)
    for k in list(os.environ):
        if k.startswith(("DMM_", "X_", "ANTHROPIC_", "TRACKING_", "DRY_RUN", "SENSITIVE_", "SLACK_", "VERCEL_", "DATA_DIR", "POSTS_")):
            del os.environ[k]
    os.environ["DATA_DIR"] = str(tmp_path)
    yield
    os.environ.clear()
    os.environ.update(saved)


@pytest.fixture
def settings(tmp_path):
    os.environ["DRY_RUN"] = "true"
    s = Settings()
    s.data_dir = tmp_path
    s.dry_run = True
    s.dmm_media_registered = True
    s.tracking_base_url = "https://t.example.com"
    s.anthropic_api_key = ""
    s.posts_per_day = 4
    return s


@pytest.fixture
def db(settings):
    d = Database(settings.db_path)
    yield d
    d.close()
