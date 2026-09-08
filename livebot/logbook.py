"""Structured logging for the H1 bot: a JSONL decision stream + a trades CSV
(the trades CSV matches forward/h1_forward_log.csv so the same eye can read both)."""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone

from livebot import config

os.makedirs(config.LOG_DIR, exist_ok=True)
_DECISIONS = os.path.join(config.LOG_DIR, "decisions.jsonl")
_TRADES = os.path.join(config.LOG_DIR, "trades.csv")

TRADE_FIELDS = ["date", "mode", "box_high", "box_low", "box_width", "side",
                "entry_time_utc", "entry_px", "entry_spread", "stop_px",
                "exit_time_utc", "exit_px", "exit_reason",
                "gross_pnl", "cost", "net_pnl", "slippage_vs_box", "ticket", "notes"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def decision(intent_name: str, status: str, **fields) -> None:
    rec = {"ts": _now(), "mode": config.MODE, "intent": intent_name, "status": status, **fields}
    with open(_DECISIONS, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def event(kind: str, **fields) -> None:
    rec = {"ts": _now(), "mode": config.MODE, "event": kind, **fields}
    with open(_DECISIONS, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    print(f"  [{rec['ts']}] {kind}: " + " ".join(f"{k}={v}" for k, v in fields.items()))


def trade(row: dict) -> None:
    row = {k: row.get(k, "") for k in TRADE_FIELDS}
    row["mode"] = row.get("mode") or config.MODE
    new = not os.path.exists(_TRADES)
    with open(_TRADES, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRADE_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
    event("TRADE_CLOSED", side=row["side"], net=row["net_pnl"], reason=row["exit_reason"])
