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
    saved = dict(os.environ)
    for k in list(os.environ):
        if k.startswith(("DMM_", "X_", "ANTHROPIC_", "SLACK_", "DATA_DIR", "POSTS_", "NOTIFY_", "WEB_", "METRIC_")):
            del os.environ[k]
    os.environ["DATA_DIR"] = str(tmp_path)
    yield
    os.environ.clear()
    os.environ.update(saved)


@pytest.fixture
def settings(tmp_path):
    s = Settings()
    s.data_dir = tmp_path
    s.dmm_media_registered = True
    s.anthropic_api_key = ""
    s.posts_per_day = 4
    return s


@pytest.fixture
def db(settings):
    d = Database(settings.db_path)
    yield d
    d.close()
