"""Read-only view of the real-time monitor (monitor/) for the webapp."""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_LOG = os.path.join(_ROOT, "monitor", "logs")
_SNAP = os.path.join(_LOG, "snapshot.json")
_HIST = os.path.join(_LOG, "history.csv")


def _age(iso: str | None):
    if not iso:
        return None
    try:
        t = datetime.fromisoformat(iso)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return round((datetime.now(timezone.utc) - t).total_seconds(), 1)
    except ValueError:
        return None


def snapshot() -> dict:
    try:
        with open(_SNAP, encoding="utf-8") as f:
            s = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"running": False, "detail": "no snapshot - run `python -m monitor`"}
    age = _age(s.get("ts"))
    s["age_seconds"] = age
    s["running"] = age is not None and age < 60
    return s


def history(limit: int = 240) -> list[dict]:
    if not os.path.exists(_HIST):
        return []
    with open(_HIST, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))[-max(1, min(limit, 2000)):]
    for r in rows:
        for k in ("price", "spread", "p_up", "confidence", "pattern_lean", "min_to_high",
                  "tone_now", "tone_z", "vol_z", "trend", "rsi", "atr_pct", "range_pos"):
            try:
                r[k] = float(r[k]) if r.get(k) not in (None, "", "None") else None
            except (TypeError, ValueError):
                r[k] = None
    return rows
