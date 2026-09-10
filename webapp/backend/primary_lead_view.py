"""
Read-only view of the M4 "primary lead" forward-paper experiment for the webapp.

This is NOT a strategy panel and NOT a live-trade feed.  It reports the state of
a frozen, pre-registered forward-paper observation:

  * the M1 realised-vol regime gate (open only in the bottom 20-day-RV tercile)
  * whether the deterministic signal fires on the latest completed 15-min bar
  * the running paper P&L per horizon book (8h / 24h) with the pre-registered
    PASS / FAIL / INCONCLUSIVE verdict

Spec (frozen): research/m4/LAYER_C_ADDENDUM_primary_lead.md
Nothing here places orders.  No edge is established — the historical result has
zero forward / out-of-sample confirmation.
"""
from __future__ import annotations

import csv
import os
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from research.m4.primary_lead_signal import (
    RV_WIN, TERCILE, M1_WARMUP, A3_LB, A3_COOLDOWN, HORIZONS, SIGMA_FLOOR,
    FRICTION_SIGMA, PAPER_CSV, signals, _m1_low_by_day, _atr14, _boot_ci,
)
from data_pipeline.dataset import load_bars

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PAPER = os.path.join(_ROOT, PAPER_CSV.replace("/", os.sep))
F_START = "2026-09-11"          # addendum forward-paper start date
_TTL = 300
_CACHE: dict = {"t": 0.0, "v": None}

_EXPECT = {                     # frozen generator, full already-touched history
    "8h":  {"gross": 0.374, "net": 0.074, "ci": [-0.099, 0.249], "win": 45.6},
    "24h": {"gross": 0.748, "net": 0.448, "ci": [0.151, 0.740], "win": 50.2},
}
_DISCLAIMER = ("Forward-paper observation of a frozen, pre-registered hypothesis. "
               "NO edge is established: the historical result has zero forward / "
               "out-of-sample confirmation, and every earlier candidate that "
               "reached this stage in this project later failed. Paper only — "
               "nothing here trades. Verdict stays INCONCLUSIVE until >=150 "
               "resolved signals per book (~10 months).")


def _verdict(n: int, mean: float, ci: tuple) -> str:
    if n < 150:
        return "INCONCLUSIVE (n<150)"
    lo, hi = ci
    if mean >= 0.05 and lo is not None and lo > 0:
        return "PASS"
    if mean <= 0 and hi is not None and hi < 0.10:
        return "FAIL"
    return "INCONCLUSIVE"


def _paper_books() -> dict:
    if not os.path.exists(_PAPER):
        return {b: {"n_resolved": 0, "n_open": 0, "mean_net_sigma": None,
                    "ci": [None, None], "verdict": "no signals yet",
                    "expect": _EXPECT[b]} for b in HORIZONS}
    with open(_PAPER, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    out = {}
    for b in HORIZONS:
        br = [r for r in rows if r.get("book") == b]
        res = [float(r["net_sigma"]) for r in br
               if r.get("status") == "resolved" and r.get("net_sigma") not in ("", None)]
        n = len(res)
        mean = round(float(np.mean(res)), 4) if n else None
        ci = _boot_ci(res) if n >= 10 else (None, None)
        out[b] = {
            "n_resolved": n,
            "n_open": sum(1 for r in br if r.get("status") == "open"),
            "mean_net_sigma": mean,
            "mean_gross_sigma": round(float(np.mean([float(r["gross_sigma"]) for r in br
                                       if r.get("status") == "resolved"
                                       and r.get("gross_sigma") not in ("", None)])), 4) if n else None,
            "ci": [None if ci[0] is None else round(ci[0], 3),
                   None if ci[1] is None else round(ci[1], 3)],
            "verdict": _verdict(n, mean or 0.0, ci),
            "expect": _EXPECT[b],
        }
    return out


def _regime_and_signal() -> dict:
    df = (load_bars("15min", split=None).drop_duplicates("ts")
          .sort_values("ts").reset_index(drop=True))
    ts = pd.DatetimeIndex(df["ts"])
    o = df["open"].to_numpy(float); hi = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float); cl = df["close"].to_numpy(float)
    atr = _atr14(hi, lo, cl)
    n = len(df)

    low_day, rv20_day, pct_day = _m1_low_by_day(df)
    last_day = pct_day.dropna().index.max()
    rv20_pctile = float(pct_day.get(last_day, np.nan)) if last_day is not None else None
    gate_open = bool(low_day.get(last_day, False)) if last_day is not None else False
    classified = rv20_pctile is not None

    # is the latest COMPLETED 15-min bar an A3 anchor (respecting 4h per-dir cooldown)?
    roll_hi = pd.Series(hi).rolling(A3_LB).max().to_numpy()
    roll_lo = pd.Series(lo).rolling(A3_LB).min().to_numpy()
    last_a3_ts = last_a3_side = None
    lu = ld = -10 ** 9
    for i in range(max(A3_LB, n - 4000), n):
        if hi[i] >= roll_hi[i] and i - lu >= A3_COOLDOWN:
            lu = i; last_a3_ts, last_a3_side = ts[i].isoformat(), 1
        elif lo[i] <= roll_lo[i] and i - ld >= A3_COOLDOWN:
            ld = i; last_a3_ts, last_a3_side = ts[i].isoformat(), -1
    i = n - 1
    a3_now = ((hi[i] >= roll_hi[i] and i - lu >= A3_COOLDOWN) or
              (lo[i] <= roll_lo[i] and i - ld >= A3_COOLDOWN)) if n > A3_LB else False
    # if the very last bar itself is the fresh A3, lu/ld was just set to i above
    a3_now = last_a3_ts == ts[i].isoformat()
    atr_ok = bool(np.isfinite(atr[i]) and atr[i] >= SIGMA_FLOOR)

    signal_now = bool(gate_open and classified and a3_now and atr_ok)
    side = last_a3_side if signal_now else None

    hist = signals(df)
    last_hist = hist["anchor_ts"].max() if len(hist) else None
    since_f = int((pd.to_datetime(hist["anchor_ts"]) >= pd.Timestamp(F_START, tz="UTC")).sum()) \
        if len(hist) else 0

    return {
        "as_of_bar": ts[i].isoformat(),
        "bar_age_min": round((datetime.now(timezone.utc) - ts[i].to_pydatetime()).total_seconds() / 60, 1),
        "rv20_pctile": None if rv20_pctile is None else round(rv20_pctile, 3),
        "regime": ("LOW (gate OPEN)" if gate_open else
                   "not classified" if not classified else
                   f"MID/HIGH (gate CLOSED — RV20 at ~{round(100*rv20_pctile)}th pctile, needs bottom {round(100*TERCILE)})"),
        "gate_open": gate_open,
        "atr14": round(float(atr[i]), 3) if np.isfinite(atr[i]) else None,
        "atr_floor": SIGMA_FLOOR,
        "atr_ok": atr_ok,
        "a3_on_latest_bar": a3_now,
        "last_a3_anchor": {"ts": last_a3_ts, "side": last_a3_side},
        "signal_now": signal_now,
        "signal_side": side,
        "last_historical_signal": last_hist,
        "signals_since_F": since_f,
        "F_start": F_START,
        "params": {"rv_window": RV_WIN, "tercile": TERCILE, "m1_warmup_days": M1_WARMUP,
                   "a3_lookback_bars": A3_LB, "a3_cooldown_bars": A3_COOLDOWN,
                   "horizons_bars": HORIZONS, "sigma_floor": SIGMA_FLOOR,
                   "friction_sigma": FRICTION_SIGMA},
    }


def status() -> dict:
    now = time.time()
    if _CACHE["v"] is not None and now - _CACHE["t"] < _TTL:
        return _CACHE["v"]
    try:
        v = _regime_and_signal()
        v["books"] = _paper_books()
    except Exception as e:  # never 500 the panel
        v = {"error": f"{type(e).__name__}: {e}"}
    v["disclaimer"] = _DISCLAIMER
    v["spec"] = "research/m4/LAYER_C_ADDENDUM_primary_lead.md"
    v["computed_at"] = datetime.now(timezone.utc).isoformat()
    _CACHE.update(t=now, v=v)
    return v
