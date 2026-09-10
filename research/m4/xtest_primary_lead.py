"""
Cross-instrument test of the FROZEN M4 primary lead on XAG/USD (silver).

Silver was never used in this project — its full Dukascopy history is a clean,
independent read.  This runs the *exact* frozen rule
(research/m4/LAYER_C_ADDENDUM_primary_lead.md, imported from primary_lead_signal.py
with every constant unchanged): M1 20-day-RV bottom-tercile regime + new 96-bar
extreme -> continuation, 8h / 24h holds, 0.30 sigma friction.  NO re-tuning.

Reports, and puts side-by-side with XAUUSD:
  * the frozen-rule numbers (LOW regime only, as the collector would trade)
  * the LOW / MID / HIGH regime contrast on ALL new-96-bar extremes

Run:  python -m research.m4.xtest_primary_lead
"""
from __future__ import annotations

import sys
import warnings

import numpy as np
import pandas as pd
import psycopg2

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
warnings.filterwarnings("ignore", category=RuntimeWarning)

from research.m4 import primary_lead_signal as PLS
from research.m4.primary_lead_signal import (
    signals, _m1_low_by_day, _atr14, _boot_ci,
    A3_LB, A3_COOLDOWN, HORIZONS, FRICTION_SIGMA, TERCILE,
)
from data_pipeline.dataset import _pg_dsn, load_bars

# The frozen SIGMA_FLOOR (0.4199) is an absolute PRICE value calibrated to gold's
# ATR14 bottom-1% — meaningless on silver ($30 vs $4400).  The instrument-agnostic
# form of that data-hygiene rule is "this instrument's own ATR14 1st percentile".
# We recompute it per instrument below; the SIGNAL logic and every other constant
# are unchanged (same reasoning as the addendum's loader-change note).
SIGMA_FLOOR = None  # set in main()

# XAUUSD frozen-generator reference (from primary_lead_signal.py --reference)
XAU_REF = {"8h": {"n": 3372, "gross": 0.374, "net": 0.074, "win": 45.6},
           "24h": {"n": 3372, "gross": 0.748, "net": 0.448, "win": 50.2}}


def load_xag() -> pd.DataFrame:
    with psycopg2.connect(**_pg_dsn()) as c:
        df = pd.read_sql("SELECT ts,open,high,low,close FROM bars_15min_xag ORDER BY ts", c)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.dropna().reset_index(drop=True)


def frozen_rule(df: pd.DataFrame, tag: str):
    s = signals(df)
    r = s[s.status == "resolved"]
    print(f"\n=== {tag}: FROZEN RULE (LOW-vol regime only, as traded) ===")
    print(f"{'book':5s} {'n':>6} {'gross sd':>10} {'NET sd':>9} {'win% net':>9} {'boot CI (net)':>22}")
    for b in HORIZONS:
        g = r[r.book == b]
        if len(g) == 0:
            print(f"{b:5s}      0   (no signals)"); continue
        ci = _boot_ci(g.net_sigma.to_numpy())
        print(f"{b:5s} {len(g):>6} {g.gross_sigma.mean():>+9.3f} {g.net_sigma.mean():>+8.3f} "
              f"{100*(g.net_sigma>0).mean():>8.1f} {f'[{ci[0]}, {ci[1]}]':>22}")
    yrs = (df.ts.max() - df.ts.min()).days / 365.25
    print(f"signal rate ~ {s.anchor_ts.nunique()/yrs:.0f}/yr   ({df.ts.min().date()} .. {df.ts.max().date()}, {yrs:.1f}y)")
    return s


def regime_contrast(df: pd.DataFrame, tag: str):
    o = df["open"].to_numpy(float); hi = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float); cl = df["close"].to_numpy(float)
    ts = pd.DatetimeIndex(df["ts"]); n = len(df)
    atr = _atr14(hi, lo, cl)
    _, _, pct = _m1_low_by_day(df)
    day = ts.floor("D")
    pcm = pct.reindex(day).to_numpy()
    bucket = np.where(np.isnan(pcm), np.nan,
                      np.where(pcm < TERCILE, 0, np.where(pcm < 0.667, 1, 2)))

    roll_hi = pd.Series(hi).rolling(A3_LB).max().to_numpy()
    roll_lo = pd.Series(lo).rolling(A3_LB).min().to_numpy()
    rows = []
    lu = ld = -10 ** 9
    for i in range(A3_LB, n - max(HORIZONS.values()) - 1):
        if not np.isfinite(atr[i]) or atr[i] < SIGMA_FLOOR or np.isnan(bucket[i]):
            continue
        side = 0
        if hi[i] >= roll_hi[i] and i - lu >= A3_COOLDOWN:
            side, lu = 1, i
        elif lo[i] <= roll_lo[i] and i - ld >= A3_COOLDOWN:
            side, ld = -1, i
        if side == 0:
            continue
        ent = o[i + 1]
        rec = {"bucket": int(bucket[i])}
        for bk, H in HORIZONS.items():
            g = side * (cl[i + H] - ent) / atr[i]
            rec[bk] = g
            rec[bk + "_net"] = g - FRICTION_SIGMA
        rows.append(rec)
    a = pd.DataFrame(rows)
    lab = {0: "LOW (gate open)", 1: "MID", 2: "HIGH"}
    print(f"\n=== {tag}: LOW / MID / HIGH contrast on ALL new-96-bar extremes ===")
    for bk in HORIZONS:
        print(f"  -- {bk} hold --")
        print(f"  {'regime':16s} {'n':>6} {'win% net':>9} {'mean gross':>11} {'mean NET':>9}")
        for b in (0, 1, 2):
            s = a[a.bucket == b]
            if len(s) < 20:
                print(f"  {lab[b]:16s} {len(s):>6}  (thin)"); continue
            print(f"  {lab[b]:16s} {len(s):>6} {100*(s[bk+'_net']>0).mean():>8.1f} "
                  f"{s[bk].mean():>+10.3f} {s[bk+'_net'].mean():>+8.3f}")
    return a


def main():
    global SIGMA_FLOOR
    xag = load_xag()
    o = xag["open"].to_numpy(float); h = xag["high"].to_numpy(float)
    l = xag["low"].to_numpy(float); c = xag["close"].to_numpy(float)
    SIGMA_FLOOR = float(np.nanpercentile(_atr14(h, l, c), 1))
    PLS.SIGMA_FLOOR = SIGMA_FLOOR          # signals() reads this module global
    print(f"XAG/USD bars_15min_xag: {len(xag):,} bars  {xag.ts.min()} .. {xag.ts.max()}")
    print(f"per-instrument sigma-floor (ATR14 p1): {SIGMA_FLOOR:.4f}  "
          f"(XAU frozen value 0.4199 would drop 98% of silver bars)")
    frozen_rule(xag, "XAG/USD")
    regime_contrast(xag, "XAG/USD")

    print("\n" + "=" * 66)
    print("XAUUSD frozen-generator reference (already-touched, for comparison):")
    for b, v in XAU_REF.items():
        print(f"  {b:4s}  n={v['n']}  gross {v['gross']:+.3f}sd  NET {v['net']:+.3f}sd  win {v['win']}%")
    print("=" * 66)
    print("Cross-instrument agreement would be supporting evidence; disagreement "
          "would weaken the primitive. Neither is a forward-paper PASS/FAIL for XAUUSD.")


if __name__ == "__main__":
    main()
