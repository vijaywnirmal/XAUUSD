"""
Lightweight market recorder. Appends one row per poll to livebot/logs/market.csv
so there is an accumulating real-time dataset to mine for microstructure
patterns (spread-by-time, short-horizon drift, volatility clustering, ...).

Rows: ts_utc, minute_of_day_utc, dow, price(mid), bid, ask, spread, box_state.
Deduplicated to ~1 row / 5s to keep the file small over long runs.
"""
from __future__ import annotations

import csv
import os
from datetime import datetime, timezone

from livebot import config

_PATH = os.path.join(config.LOG_DIR, "market.csv")
_FIELDS = ["ts_utc", "mod_utc", "dow", "price", "bid", "ask", "spread", "state"]
_last_ts = 0.0


def record(tick, state: str) -> None:
    global _last_ts
    now = datetime.now(timezone.utc)
    epoch = now.timestamp()
    if epoch - _last_ts < 5.0:
        return
    _last_ts = epoch
    os.makedirs(config.LOG_DIR, exist_ok=True)
    new = not os.path.exists(_PATH)
    with open(_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(_FIELDS)
        w.writerow([
            now.isoformat(timespec="seconds"),
            now.hour * 60 + now.minute,
            now.weekday(),
            round(tick.mid, 3), round(tick.bid, 3), round(tick.ask, 3),
            round(tick.spread, 4), state,
        ])
