"""
Cross-instrument PRIOR CHECK for the frozen M4 primary lead.

Pre-registered batch (decided before seeing results):
  silver  + 6 FX majors: EURUSD GBPUSD USDJPY AUDUSD USDCAD USDCHF

Runs the *exact* frozen rule (research/m4/LAYER_C_ADDENDUM_primary_lead.md,
imported from primary_lead_signal.py) on each — M1 20-day-RV bottom-tercile
regime + new 96-bar extreme -> continuation, 8h/24h holds, 0.30 sigma friction.
NO re-tuning.  The ONLY per-instrument change is the data-hygiene sigma-floor,
recomputed as that instrument's own ATR14 1st percentile (the frozen 0.4199 is
an absolute *gold* price).  M1's daily boundary stays 00:00 UTC, identical to
the frozen rule (FX has no true daily close; noted as a caveat).

This does NOT change the XAUUSD forward-paper test or its verdicts.  It is a
prior-strengthening cross-section, reported in full with no cherry-picking.

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
from data_pipeline.dataset import _pg_dsn

WINS = 20.0   # winsorise per-event sigma returns (run1 did the same for near-zero-ATR degeneracy)

BATCH = [
    ("bars_15min_xag", "XAG/USD"),
    ("bars_15min_eurusd", "EUR/USD"),
    ("bars_15min_gbpusd", "GBP/USD"),
    ("bars_15min_usdjpy", "USD/JPY"),
    ("bars_15min_audusd", "AUD/USD"),
    ("bars_15min_usdcad", "USD/CAD"),
    ("bars_15min_usdchf", "USD/CHF"),
]
XAU_REF = {"8h": (0.374, 0.074, 45.6), "24h": (0.748, 0.448, 50.2)}   # gross, net, win%


def load_table(table: str) -> pd.DataFrame:
    with psycopg2.connect(**_pg_dsn()) as c:
        df = pd.read_sql(f"SELECT ts,open,high,low,close FROM {table} ORDER BY ts", c)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.dropna().reset_index(drop=True)


def frozen_rule(df, tag):
    s = signals(df)
    out = {}
    if "status" not in s.columns:
        print(f"  {tag}: 0 signals"); return {b: None for b in HORIZONS}
    r = s[s.status == "resolved"].copy()
    r["gross_sigma"] = r["gross_sigma"].clip(-WINS, WINS)
    r["net_sigma"] = r["gross_sigma"] - FRICTION_SIGMA
    for b in HORIZONS:
        g = r[r.book == b]
        if len(g) < 20:
            out[b] = None; continue
        ci = tuple(round(float(x), 3) if x is not None else None
                   for x in _boot_ci(g.net_sigma.to_numpy()))
        out[b] = dict(n=len(g), gross=g.gross_sigma.mean(), net=g.net_sigma.mean(),
                      win=100 * (g.net_sigma > 0).mean(), ci=ci)
    yrs = (df.ts.max() - df.ts.min()).days / 365.25
    out["rate"] = s.anchor_ts.nunique() / yrs
    out["span"] = (df.ts.min().date(), df.ts.max().date(), round(yrs, 1))
    return out


def regime_contrast(df):
    o = df["open"].to_numpy(float); hi = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float); cl = df["close"].to_numpy(float)
    ts = pd.DatetimeIndex(df["ts"]); n = len(df)
    atr = _atr14(hi, lo, cl)
    _, _, pct = _m1_low_by_day(df)
    pcm = pct.reindex(ts.floor("D")).to_numpy()
    bucket = np.where(np.isnan(pcm), np.nan,
                      np.where(pcm < TERCILE, 0, np.where(pcm < 0.667, 1, 2)))
    rh = pd.Series(hi).rolling(A3_LB).max().to_numpy()
    rl = pd.Series(lo).rolling(A3_LB).min().to_numpy()
    rows = []; lu = ld = -10 ** 9
    for i in range(A3_LB, n - max(HORIZONS.values()) - 1):
        if not np.isfinite(atr[i]) or atr[i] < PLS.SIGMA_FLOOR or np.isnan(bucket[i]):
            continue
        side = 0
        if hi[i] >= rh[i] and i - lu >= A3_COOLDOWN:
            side, lu = 1, i
        elif lo[i] <= rl[i] and i - ld >= A3_COOLDOWN:
            side, ld = -1, i
        if side == 0:
            continue
        ent = o[i + 1]; rec = {"b": int(bucket[i])}
        for bk, H in HORIZONS.items():
            g = float(np.clip(side * (cl[i + H] - ent) / atr[i], -WINS, WINS))
            rec[bk] = g - FRICTION_SIGMA
        rows.append(rec)
    a = pd.DataFrame(rows)
    res = {}
    for bk in HORIZONS:
        res[bk] = {b: (a[a.b == b][bk].mean() if (a.b == b).sum() >= 20 else np.nan)
                   for b in (0, 1, 2)}
    return res


def main():
    summ = []
    for table, tag in BATCH:
        try:
            df = load_table(table)
        except Exception as e:
            print(f"\n{tag}: table missing ({e})"); continue
        h = df["high"].to_numpy(float); l = df["low"].to_numpy(float); c = df["close"].to_numpy(float)
        atr = _atr14(h, l, c)
        # Dukascopy pads illiquid FX periods with flat (high==low) bars (~6%);
        # those drag ATR14 -> ~0. Equivalent hygiene to gold's p1 floor: p1 of
        # ATR14 over NON-FLAT bars, and never below 10% of the median.
        nonflat = atr[np.isfinite(atr) & (h != l)]
        PLS.SIGMA_FLOOR = float(max(np.nanpercentile(nonflat, 1),
                                    0.10 * np.nanmedian(atr[np.isfinite(atr)])))
        fr = frozen_rule(df, tag)
        rc = regime_contrast(df)
        print(f"\n### {tag}  ({len(df):,} bars, {fr.get('span')}, sigma-floor {PLS.SIGMA_FLOOR:.5f}) ###")
        for b in HORIZONS:
            v = fr.get(b)
            if v:
                print(f"  {b:4s} frozen rule: n={v['n']:5d}  gross {v['gross']:+.3f}sd  "
                      f"NET {v['net']:+.3f}sd  CI[{v['ci'][0]}, {v['ci'][1]}]  win {v['win']:.1f}%")
        for b in HORIZONS:
            r = rc[b]
            mono = (r[0] > r[1] > r[2]) if not any(np.isnan(list(r.values()))) else None
            print(f"  {b:4s} regime net: LOW {r[0]:+.3f}  MID {r[1]:+.3f}  HIGH {r[2]:+.3f}"
                  f"   monotone(LOW>MID>HIGH): {mono}")
        v24 = fr.get("24h")
        r24 = rc["24h"]
        summ.append(dict(
            pair=tag,
            low24_net=None if not v24 else round(v24["net"], 3),
            low24_ci=None if not v24 else v24["ci"],
            n24=None if not v24 else v24["n"],
            rate=round(fr.get("rate", 0), 0),
            monotone_24h=(r24[0] > r24[1] > r24[2]) if not any(np.isnan(list(r24.values()))) else None,
            ci_excl_0=None if not v24 else (v24["ci"][0] is not None and v24["ci"][0] > 0),
        ))

    print("\n" + "=" * 78)
    print("PRE-REGISTERED BATCH SUMMARY  (frozen rule; nothing selected post-hoc)")
    print("=" * 78)
    print(f"{'pair':9s} {'24h LOW net':>12} {'CI (net)':>22} {'n':>6} {'sig/yr':>7} "
          f"{'monotone':>9} {'CI>0':>6}")
    for r in summ:
        ci = r["low24_ci"]
        cis = "n/a" if ci is None else f"[{ci[0]:+.3f}, {ci[1]:+.3f}]"
        net = "n/a" if r["low24_net"] is None else f"{r['low24_net']:+.3f}"
        print(f"{r['pair']:9s} {net:>12} {cis:>22} {str(r['n24']):>6} "
              f"{str(int(r['rate'])):>7} {str(r['monotone_24h']):>9} {str(r['ci_excl_0']):>6}")
    mono = sum(1 for r in summ if r["monotone_24h"])
    sig = sum(1 for r in summ if r["ci_excl_0"])
    print(f"\nXAUUSD reference: 24h gross +0.748 / NET +0.448sd / win 50.2% "
          f"(already-touched, not part of this batch)")
    print(f"of {len(summ)} instruments: {mono} show the LOW>MID>HIGH monotone at 24h; "
          f"{sig} have a LOW-regime 24h net CI excluding zero.")
    print("Reading: FX intraday is more mean-reverting than metals, so a null on FX "
          "is weak evidence; a positive on FX is strong. This does NOT feed the "
          "frozen XAUUSD rule or its forward-paper verdict.")


if __name__ == "__main__":
    main()
