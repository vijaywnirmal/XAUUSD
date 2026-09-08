"""
Read-only view of the H1 execution bot (livebot/) for the webapp.

The bot runs as its own process (`python -m livebot`, paper mode). This module
only READS its log files - it never starts, stops, or sends anything:
  livebot/logs/status.json     - latest snapshot (written every poll)
  livebot/logs/decisions.jsonl - decision / event stream
  livebot/logs/trades.csv      - one row per closed trade
"""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_LOGDIR = os.path.join(_ROOT, "livebot", "logs")
_STATUS = os.path.join(_LOGDIR, "status.json")
_DECISIONS = os.path.join(_LOGDIR, "decisions.jsonl")
_TRADES = os.path.join(_LOGDIR, "trades.csv")

# backtest reference (in-sample 2009-2022, $6/lot commission)
BT_GROSS = 0.388
BT_BREAKEVEN_SPREAD = 0.30
COMMISSION_PER_001_LOT = 0.06


def _age_seconds(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        t = datetime.fromisoformat(iso)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds()
    except ValueError:
        return None


def status() -> dict:
    try:
        with open(_STATUS, encoding="utf-8") as f:
            snap = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"running": False, "detail": "no status.json - is `python -m livebot` running?"}
    age = _age_seconds(snap.get("ts"))
    snap["age_seconds"] = round(age, 1) if age is not None else None
    # the bot polls every ~2s; treat >45s without an update as stalled
    snap["running"] = age is not None and age < 45
    return snap


def decisions(limit: int = 50) -> list[dict]:
    if not os.path.exists(_DECISIONS):
        return []
    with open(_DECISIONS, encoding="utf-8") as f:
        lines = f.readlines()[-max(1, min(limit, 500)):]
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    out.reverse()
    return out


def trades() -> dict:
    if not os.path.exists(_TRADES):
        return {"rows": [], "summary": None}
    rows = [r for r in csv.DictReader(open(_TRADES, encoding="utf-8")) if r.get("net_pnl")]
    for r in rows:
        for k in ("box_high", "box_low", "box_width", "entry_px", "entry_spread", "stop_px",
                  "exit_px", "gross_pnl", "cost", "net_pnl", "slippage_vs_box"):
            try:
                r[k] = float(r[k]) if r.get(k) not in (None, "") else None
            except (TypeError, ValueError):
                r[k] = None
    summary = None
    if rows:
        net = [r["net_pnl"] for r in rows if r["net_pnl"] is not None]
        gross = [r["gross_pnl"] for r in rows if r["gross_pnl"] is not None]
        spr = [r["entry_spread"] for r in rows if r["entry_spread"] is not None]
        slp = [r["slippage_vs_box"] for r in rows if r["slippage_vs_box"] is not None]
        wins = [x for x in net if x > 0]
        losses = [x for x in net if x <= 0]
        avg = lambda v: sum(v) / len(v) if v else None
        eff = None
        if spr:
            eff = COMMISSION_PER_001_LOT + avg(spr) + max(avg(slp) or 0.0, 0.0)
        summary = {
            "n": len(net), "win_rate": len(wins) / len(net) if net else None,
            "exp_net": avg(net), "exp_gross": avg(gross), "cum_net": sum(net),
            "pf": (sum(wins) / -sum(losses)) if losses and sum(losses) != 0 else None,
            "avg_entry_spread": avg(spr), "avg_slippage": avg(slp),
            "effective_cost": eff, "breakeven_spread": BT_BREAKEVEN_SPREAD,
            "edge_intact": (eff is not None and eff < BT_BREAKEVEN_SPREAD),
            "backtest_gross": BT_GROSS,
        }
    rows.reverse()
    return {"rows": rows[:200], "summary": summary}
