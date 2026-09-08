"""Atomic status snapshot the webapp reads. Written every poll by the runner."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone

from livebot import config

_PATH = os.path.join(config.LOG_DIR, "status.json")


def write(payload: dict) -> None:
    payload = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "mode": config.MODE, "symbol": config.SYMBOL, **payload}
    os.makedirs(config.LOG_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=config.LOG_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, default=str, indent=1)
        os.replace(tmp, _PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def read() -> dict | None:
    try:
        with open(_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
