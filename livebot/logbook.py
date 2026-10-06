"""Structured logging for the H1 bot: a JSONL decision stream + a trades CSV
(the trades CSV matches forward/h1_forward_log.csv so the same eye can read both), plus one replay
file per closed trade (logs/replays/) - the price history a trade video is drawn from."""
from __future__ import annotations

import csv
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

from livebot import config

os.makedirs(config.LOG_DIR, exist_ok=True)
_DECISIONS = os.path.join(config.LOG_DIR, "decisions.jsonl")
_TRADES = os.path.join(config.LOG_DIR, "trades.csv")

TRADE_FIELDS = ["date", "mode", "box_high", "box_low", "box_width", "side",
                "entry_time_utc", "entry_px", "entry_spread", "stop_px",
                "exit_time_utc", "exit_px", "exit_reason",
                "gross_pnl", "cost", "net_pnl", "slippage_vs_box", "ticket", "notes", "symbol", "pips"]


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


def _hm(day: str, hhmm: str) -> datetime:
    return datetime.fromisoformat(f"{day}T{hhmm}:00+00:00")


def replay(row: dict, entry_time: datetime, exit_time: datetime, feed) -> None:
    """Save the trade with its price history (M1 bars from just before the box to the close, real
    1-second bars around the fill and the close) to logs/replays/<date>_<symbol>.json, then run
    ON_TRADE_CMD. Best effort: a failure here never touches the trading loop."""
    try:
        day = row["date"]
        start = _hm(day, config.BOX_START_UTC) - timedelta(minutes=config.REPLAY_LEAD_MIN)
        windows = [(entry_time.replace(second=0, microsecond=0) - timedelta(minutes=1), entry_time + timedelta(minutes=2)),
                   (exit_time.replace(second=0, microsecond=0) - timedelta(minutes=1), exit_time + timedelta(seconds=30))]
        data = feed.replay_data(start, exit_time + timedelta(minutes=1), windows)
        out = {
            "id": f"{day}-{config.SYMBOL}", "symbol": config.SYMBOL, "digits": config.DIGITS, "pip": config.PIP,
            "lots": config.LOTS, "contract": config.CONTRACT, "quote_usd": config.QUOTE_USD, "mode": config.MODE,
            "rules": {"box": [config.BOX_START_UTC, config.BOX_END_UTC], "break_end": config.BREAK_END_UTC,
                      "flat": config.FLAT_UTC},
            "trade": {**row, "entry_time": entry_time.isoformat(), "exit_time": exit_time.isoformat()},
            **data,
        }
        folder = os.path.join(config.LOG_DIR, "replays")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{day}_{config.SYMBOL}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f)
        event("REPLAY_SAVED", path=path, minutes=len(data["minutes"]), seconds=len(data["seconds"]))
    except Exception as e:
        event("WARN", msg=f"replay not saved: {type(e).__name__}: {e}")
        return
    if config.ON_TRADE_CMD:
        try:
            subprocess.Popen(config.ON_TRADE_CMD, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as e:
            event("WARN", msg=f"on-trade command failed: {e}")
