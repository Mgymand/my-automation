"""JSONファイルベースの永続化レイヤ（DB不要・無料運用向け）。

本番は永続ディスク（Render Disk / Cloud Storage FUSE）を MAGO_DATA_DIR で指定する。
書き込みはテンポラリ→rename のアトミック更新。スレッドロックで多重書き込みを防ぐ。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("MAGO_DATA_DIR") or os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

_LOCK = threading.RLock()
_CACHE: dict[str, tuple[float, object]] = {}


def _path(name: str) -> str:
    return os.path.join(DATA_DIR, f"{name}.json")


def load(name: str, default):
    """ファイルをmtimeキャッシュ付きで読む。"""
    p = _path(name)
    with _LOCK:
        if not os.path.exists(p):
            return default
        mtime = os.path.getmtime(p)
        hit = _CACHE.get(name)
        if hit and hit[0] == mtime:
            return hit[1]
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        _CACHE[name] = (mtime, data)
        return data


def save(name: str, data) -> None:
    p = _path(name)
    tmp = p + ".tmp"
    with _LOCK:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
        _CACHE[name] = (os.path.getmtime(p), data)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def today() -> str:
    return time.strftime("%Y-%m-%d")
