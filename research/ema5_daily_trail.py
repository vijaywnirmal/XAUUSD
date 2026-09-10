"""
5-EMA (Pani) fade on the DAILY XAUUSD chart, 1:3 target, with a TRAILING stop.

There is no daily bar table in Postgres — daily bars are resampled here from
bars_1h (UTC calendar day).

Signal (same mechanical Pani rule as the intraday studies):
  * EMA5 on daily close.
  * SHORT: a day whose LOW is entirely above EMA5, prev day touching EMA5.
  * LONG : a day whose HIGH is entirely below EMA5, prev day touching.
  * Entry = stop order at that day's extreme, must trigger within ENTRY_VALID days.
  * Initial risk R = signal-day range.

Three exits compared:
  A  fixed      : stop at -1R the whole time, target +3R.
  B  step-trail : target +3R; move stop to break-even once +1R is reached,
                  to +1R once +2R is reached (lock in as it runs).
  C  ema5-trail : no fixed target; exit when a daily close crosses back through
                  EMA5 (the canonical Pani "let it run" exit), hard stop -1R.

Cost = engine model in R (tiny on daily: R is 30-60 usd).
Fit nothing — daily gives ~900 in-sample / ~90 walk-forward signals, far too few
for a feature model. This only reports base rates, the three exits' expectancy,
and a few crude condition splits.

Usage:  python -m research.ema5_daily_trail
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from data_pipeline.dataset import load_bars

PIP = 0.10
CONTRACT = 100.0
COMMISSION_RT_PER_LOT = 6.0
SLIP_TICKS = 1.0
TICK = 0.01
LOT = 0.01
MIN_R_PIPS = 20.0          # daily candles are big; drop the rare tiny ones
ENTRY_VALID = 2
MAX_HOLD = 40             # trading days


def _daily(df: pd.DataFrame) -> pd.DataFrame:
    g = (df.set_index("ts").resample("1D")
         .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
              close=("close", "last"), spread_mean=("spread_mean", "mean"),
              vol=("volume_sum", "sum"), ticks=("tick_count", "sum"))
         .dropna(subset=["open"]))
    return g.reset_index()


def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def _atr(hi, lo, cl, n=14):
    tr = np.maximum(hi - lo, np.maximum(np.abs(hi - np.roll(cl, 1)),
                                        np.abs(lo - np.roll(cl, 1))))
    tr[0] = hi[0] - lo[0]
    return pd.Series(tr).rolling(n).mean().to_numpy()


def _adx(hi, lo, cl, n=14):
    up = hi - np.roll(hi, 1); dn = np.roll(lo, 1) - lo
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(hi - lo, np.maximum(np.abs(hi - np.roll(cl, 1)),
                                        np.abs(lo - np.roll(cl, 1))))
    tr[0] = hi[0] - lo[0]
    atr = pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pd.Series(plus).ewm(alpha=1 / n, adjust=False).mean() / atr
    mdi = 100 * pd.Series(minus).ewm(alpha=1 / n, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean().fillna(0).to_numpy()


def run(dfd: pd.DataFrame, split: str) -> pd.DataFrame:
    o = dfd["open"].to_numpy(float); hi = dfd["high"].to_numpy(float)
    lo = dfd["low"].to_numpy(float); cl = dfd["close"].to_numpy(float)
    spr = dfd["spread_mean"].to_numpy(float)
    ts = pd.DatetimeIndex(dfd["ts"]); n = len(dfd)
    ema5 = _ema(cl, 5); ema50 = _ema(cl, 50); ema200 = _ema(cl, 200)
    atr = _atr(hi, lo, cl, 14)
    atr_pct = pd.Series(atr).rolling(250, min_periods=60).rank(pct=True).to_numpy()
    adx = _adx(hi, lo, cl, 14)

    touch = (lo <= ema5) & (ema5 <= hi)
    short_sig = (lo > ema5) & np.roll(touch, 1)
    long_sig = (hi < ema5) & np.roll(touch, 1)
    short_sig[0] = long_sig[0] = False

    rows = []
    for i in np.where(short_sig | long_sig)[0]:
        if i < 60 or i + 2 >= n or np.isnan(atr[i]) or atr[i] <= 0:
            continue
        side = -1 if short_sig[i] else 1
        trig = lo[i] if side < 0 else hi[i]
        R = (hi[i] - trig) if side < 0 else (trig - lo[i])
        if R < MIN_R_PIPS * PIP:
            continue

        ent_i = ent_px = None
        for k in range(i + 1, min(i + 1 + ENTRY_VALID, n)):
            if side < 0 and lo[k] <= trig:
                ent_i, ent_px = k, min(o[k], trig); break
            if side > 0 and hi[k] >= trig:
                ent_i, ent_px = k, max(o[k], trig); break
        if ent_i is None:
            continue
        risk_usd = R * LOT * CONTRACT
        cost_r_base = (((spr[ent_i] / 2) + 2 * SLIP_TICKS * TICK) * LOT * CONTRACT
                       + COMMISSION_RT_PER_LOT * LOT) / risk_usd

        def walk(mode):
            stop = (hi[i] if side < 0 else lo[i])           # -1R
            tgt = ent_px + (-3 if side < 0 else 3) * R
            r = 0.0; xi = min(ent_i + MAX_HOLD, n - 1); reason = "timeout"
            for k in range(ent_i, min(ent_i + MAX_HOLD, n)):
                fav = (ent_px - lo[k]) / R if side < 0 else (hi[k] - ent_px) / R
                s_hit = (hi[k] >= stop) if side < 0 else (lo[k] <= stop)
                t_hit = (lo[k] <= tgt) if side < 0 else (hi[k] >= tgt)
                if s_hit:
                    r = (ent_px - stop) / R if side < 0 else (stop - ent_px) / R
                    xi, reason = k, ("stop" if r < 0 else "trail_lock" if r > 0 else "breakeven")
                    break
                if mode in ("A", "B") and t_hit:
                    r, xi, reason = 3.0, k, "target"; break
                if mode == "C" and ((side < 0 and cl[k] > ema5[k]) or (side > 0 and cl[k] < ema5[k])):
                    px = cl[k]
                    r = (ent_px - px) / R if side < 0 else (px - ent_px) / R
                    xi, reason = k, "ema5_cross"; break
                if mode == "B":
                    if fav >= 2 and side < 0:
                        stop = min(stop, ent_px - 1 * R)
                    elif fav >= 2:
                        stop = max(stop, ent_px + 1 * R)
                    elif fav >= 1 and side < 0:
                        stop = min(stop, ent_px)
                    elif fav >= 1:
                        stop = max(stop, ent_px)
                if mode == "C":                              # trail stop to prior extreme
                    if side < 0:
                        stop = min(stop, hi[k])
                    else:
                        stop = max(stop, lo[k])
            if reason == "timeout":
                px = cl[xi]
                r = (ent_px - px) / R if side < 0 else (px - ent_px) / R
            return r, xi - ent_i, reason

        rec = dict(ts=ts[i], side=side, split=split, R_pips=R / PIP,
                   adx=adx[i], atr_pct=atr_pct[i], dow=ts[i].dayofweek, month=ts[i].month,
                   trend_align=int((side < 0 and cl[i] < ema200[i]) or (side > 0 and cl[i] > ema200[i])),
                   ema50_align=int((side < 0 and cl[i] < ema50[i]) or (side > 0 and cl[i] > ema50[i])))
        for m in ("A", "B", "C"):
            r, bars, why = walk(m)
            rec[f"r_{m}"] = r
            rec[f"net_{m}"] = r - cost_r_base
            rec[f"bars_{m}"] = bars
            rec[f"why_{m}"] = why
        rows.append(rec)
    return pd.DataFrame(rows)


def summ(s: pd.DataFrame, tag: str):
    print(f"\n######## {tag}  —  {len(s)} triggered daily signals ########")
    for m, name in [("A", "fixed 1:3"), ("B", "step-trail -> +3R"), ("C", "EMA5-cross trail")]:
        r = s[f"r_{m}"]; net = s[f"net_{m}"]
        win = (r > 0).mean()
        print(f"  {name:20s}  win% {win:.3f}  exp GROSS {r.mean():+.3f}R  "
              f"exp NET {net.mean():+.3f}R  median hold {s[f'bars_{m}'].median():.0f}d  "
              f"| reasons: {dict(s[f'why_{m}'].value_counts())}")
    print("  --- step-trail net R by condition ---")
    for col, bins in [("adx", [0, 20, 25, 100]), ("atr_pct", [0, .33, .66, 1.01]),
                      ("trend_align", [-1, 0, 1]), ("dow", [-1, 0, 1, 2, 3, 4])]:
        g = s.groupby(pd.cut(s[col], bins) if col in ("adx", "atr_pct") else s[col],
                      observed=True)["net_B"].agg(["size", "mean"]).round(3)
        print(f"    {col}:")
        print(g.to_string().replace("\n", "\n      "))


if __name__ == "__main__":
    frames = []
    for split in ("in_sample", "walk_forward"):
        d = _daily(load_bars("1h", split=split))
        s = run(d, split)
        frames.append(s)
        summ(s, f"daily / {split}")
    alls = pd.concat(frames, ignore_index=True)
    summ(alls, "daily / COMBINED")
    alls.to_csv("research/ema5_daily_trail.csv", index=False)
    print("\nsaved research/ema5_daily_trail.csv")
