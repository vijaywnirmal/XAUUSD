"""
FROZEN deterministic signal generator for the Layer-C primary lead.
Spec: research/m4/LAYER_C_ADDENDUM_primary_lead.md (2026-09-10).  Do not edit the
constants — a change requires a new dated addendum and restarts the forward count.

Signal (close of 15-min bar i):
    M1 == LOW (day D-1 RV20 in the bottom trailing tercile, >=504 prior daily obs)
    AND bar i is a new 96-bar high or low (A3), 4h per-direction cooldown
    AND ATR14(i) >= 0.4199
  -> side = +1 (new high) / -1 (new low); enter at open of bar i+1.
Books: H = 32 bars (8h) and 96 bars (24h); exit at close of bar i+H; no stop.
Friction: flat 0.30 sigma round-trip.  Size: 0.01 lot (does not affect the sigma verdict).

Usage:
  python -m research.m4.primary_lead_signal --since 2026-09-11   # forward paper (appends)
  python -m research.m4.primary_lead_signal --reference          # historical numbers, CONTEXT ONLY
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from data_pipeline.dataset import load_bars

# ---- FROZEN CONSTANTS (Run 1 values) -------------------------------------- #
RV_WIN = 20
TERCILE = 1.0 / 3.0
M1_WARMUP = 504
A3_LB = 96
A3_COOLDOWN = 16
HORIZONS = {"8h": 32, "24h": 96}
SIGMA_FLOOR = 0.4199
FRICTION_SIGMA = 0.30
LOT = 0.01
PAPER_CSV = "research/m4/paper_primary_lead.csv"


def _atr14(hi, lo, cl):
    tr = np.maximum(hi - lo, np.maximum(np.abs(hi - np.roll(cl, 1)),
                                        np.abs(lo - np.roll(cl, 1))))
    tr[0] = hi[0] - lo[0]
    return pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()


def _m1_low_by_day(df15: pd.DataFrame):
    d = df15.set_index("ts")["close"].resample("1D").last().dropna()
    rv20 = d.pct_change().rolling(RV_WIN).std()
    lo_cut = rv20.expanding(min_periods=M1_WARMUP).quantile(TERCILE).shift(1)
    pct = rv20.expanding(min_periods=M1_WARMUP).apply(
        lambda s: (s.iloc[:-1] < s.iloc[-1]).mean() if len(s) > 1 else np.nan, raw=False).shift(0)
    is_low_raw = (rv20 < lo_cut)                       # classified iff lo_cut not NaN
    classified = lo_cut.notna()
    # label applicable DURING day D uses data through D-1  -> shift(1)
    return (is_low_raw.shift(1).fillna(False) & classified.shift(1).fillna(False),
            rv20.shift(1), pct.shift(1))


def signals(df15: pd.DataFrame) -> pd.DataFrame:
    df15 = df15.reset_index(drop=True)
    o = df15["open"].to_numpy(float); hi = df15["high"].to_numpy(float)
    lo = df15["low"].to_numpy(float); cl = df15["close"].to_numpy(float)
    ts = pd.DatetimeIndex(df15["ts"]); n = len(df15)
    atr = _atr14(hi, lo, cl)

    low_day, rv20_day, pct_day = _m1_low_by_day(df15)
    day = ts.floor("D")
    m1_low = low_day.reindex(day).to_numpy()
    rv20 = rv20_day.reindex(day).to_numpy()
    pct = pct_day.reindex(day).to_numpy()

    roll_hi = pd.Series(hi).rolling(A3_LB).max().to_numpy()
    roll_lo = pd.Series(lo).rolling(A3_LB).min().to_numpy()

    rows = []
    lu = ld = -10 ** 9
    for i in range(A3_LB, n - 1):
        if not m1_low[i] or not np.isfinite(atr[i]) or atr[i] < SIGMA_FLOOR:
            continue
        side = 0
        if hi[i] >= roll_hi[i] and i - lu >= A3_COOLDOWN:
            side, lu = 1, i
        elif lo[i] <= roll_lo[i] and i - ld >= A3_COOLDOWN:
            side, ld = -1, i
        if side == 0:
            continue
        ent_i = i + 1
        ent = o[ent_i]
        base = dict(anchor_ts=ts[i].isoformat(), side=int(side),
                    rv20=float(rv20[i]) if np.isfinite(rv20[i]) else np.nan,
                    rv20_pctile=float(pct[i]) if np.isfinite(pct[i]) else np.nan,
                    atr14=round(float(atr[i]), 4), entry_ts=ts[ent_i].isoformat(),
                    entry_px=round(float(ent), 3))
        for book, H in HORIZONS.items():
            xi = ent_i + H - 1
            if xi < n:
                g = side * (cl[xi] - ent) / atr[i]
                rows.append({**base, "book": book, "status": "resolved",
                             "exit_ts": ts[xi].isoformat(), "exit_px": round(float(cl[xi]), 3),
                             "gross_sigma": round(float(g), 4),
                             "net_sigma": round(float(g - FRICTION_SIGMA), 4)})
            else:
                rows.append({**base, "book": book, "status": "open",
                             "exit_ts": "", "exit_px": np.nan,
                             "gross_sigma": np.nan, "net_sigma": np.nan})
    return pd.DataFrame(rows)


def _boot_ci(v, B=4000, seed=0):
    v = np.asarray(v, float); v = v[np.isfinite(v)]
    if len(v) < 10:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    bs = rng.choice(v, (B, len(v))).mean(1)
    return tuple(np.percentile(bs, [2.5, 97.5]).round(3))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="forward-paper start date (UTC, inclusive)")
    ap.add_argument("--reference", action="store_true",
                    help="print historical numbers over ALL data — CONTEXT ONLY, not validation")
    a = ap.parse_args()

    # Forward-paper phase: load the entire live 15-min series (research splits
    # capped at 2026-09-04; the paper test needs everything, incl. top-up rows).
    df = (load_bars("15min", split=None)
          .drop_duplicates("ts").sort_values("ts").reset_index(drop=True))

    if a.reference:
        sig = signals(df)
        r = sig[sig.status == "resolved"]
        print("REFERENCE ONLY — already-touched data (2009–2026). NOT forward validation.\n")
        for book in HORIZONS:
            g = r[r.book == book]
            ci = _boot_ci(g.net_sigma)
            print(f"  {book:4s}  n={len(g):5d}  gross {g.gross_sigma.mean():+.3f}sd  "
                  f"NET {g.net_sigma.mean():+.3f}sd  (iid boot 95% CI on net [{ci[0]}, {ci[1]}])  "
                  f"win%(net>0) {100*(g.net_sigma>0).mean():.1f}")
        rate = sig.groupby("book").anchor_ts.nunique().mean() / \
            ((pd.Timestamp(df.ts.max()) - pd.Timestamp(df.ts.min())).days / 365.25)
        print(f"\n  signal rate ~ {rate:.0f}/yr  (addendum expects ~190; retire band 95–285)")
        return

    if not a.since:
        print("forward-paper mode needs --since YYYY-MM-DD (the addendum start date F). "
              "Use --reference for historical context."); return
    F = pd.Timestamp(a.since, tz="UTC")
    sig = signals(df)
    sig = sig[pd.to_datetime(sig.anchor_ts) >= F]
    if sig.empty:
        print(f"no signals on/after {a.since} yet."); return

    cols = ["anchor_ts", "side", "rv20", "rv20_pctile", "atr14", "entry_ts",
            "entry_px", "book", "status", "exit_ts", "exit_px", "gross_sigma", "net_sigma"]
    sig = sig[cols]
    if os.path.exists(PAPER_CSV):
        old = pd.read_csv(PAPER_CSV)
        key = ["anchor_ts", "book"]
        merged = pd.concat([old, sig]).drop_duplicates(key, keep="last").sort_values(key)
    else:
        merged = sig.sort_values(["anchor_ts", "book"])
    merged.to_csv(PAPER_CSV, index=False)
    res = merged[merged.status == "resolved"]
    print(f"{PAPER_CSV}: {len(merged)} rows  ({(merged.status=='open').sum()} still open)")
    for book in HORIZONS:
        g = res[res.book == book]
        if len(g) == 0:
            print(f"  {book}: 0 resolved"); continue
        ci = _boot_ci(g.net_sigma)
        n = len(g)
        verdict = ("n<150 (INCONCLUSIVE)" if n < 150 else
                   "PASS" if (g.net_sigma.mean() >= 0.05 and ci[0] and ci[0] > 0) else
                   "FAIL" if (g.net_sigma.mean() <= 0 and ci[1] and ci[1] < 0.10) else
                   "INCONCLUSIVE")
        print(f"  {book:4s}  n={n:4d}  NET {g.net_sigma.mean():+.3f}sd  CI[{ci[0]},{ci[1]}]  -> {verdict}")


if __name__ == "__main__":
    main()
