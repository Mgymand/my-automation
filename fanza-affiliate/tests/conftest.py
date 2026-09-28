import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from affiliate_bot.config import Settings  # noqa: E402
from affiliate_bot.db import Database  # noqa: E402


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
