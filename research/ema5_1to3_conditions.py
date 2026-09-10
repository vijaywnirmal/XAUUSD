"""
5-EMA (Pani) fade setup on 5-minute XAUUSD — under what conditions does it
actually reach 1:3 (target = 3x the signal-candle risk) before the stop?

Setup (mechanical Pani rules):
  * EMA5 on close.
  * SHORT signal bar i:  low[i]  > EMA5[i]  (whole candle above the EMA, not
    touching) AND the previous bar was touching the EMA
    (low[i-1] <= EMA5[i-1] <= high[i-1]).  -> fade back down.
  * LONG signal bar i:   high[i] < EMA5[i]  and previous bar touching.
  * Entry = stop order at the signal candle's extreme (low for short / high for
    long); must trigger within ENTRY_VALID bars or the signal is void.
  * Stop  = the signal candle's other extreme.  risk R = signal candle range.
  * Target = entry -/+ 3R.
  * Forward walk: stop before target if a bar hits both (pessimistic).
  * Timeout after MAX_HOLD bars -> exit at close, record the R actually made.

Costs: same model as backtest/engine.py, expressed in R (=cost_usd / risk_usd).

Then: overall 1:3 hit-rate + expectancy, and the same sliced by hour, session,
day-of-week, signal-range bucket, EMA-detachment, ATR regime, EMA200 trend
alignment, EMA5 slope, and pre-signal run length.

Breakeven 1:3 hit-rate = (1 + cost_R) / 4  (~0.25 with zero cost, ~0.29–0.31 at
realistic 0.01-lot cost).

Usage:  python -m research.ema5_1to3_conditions
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
RR = 3.0                # overridden by build_signals(rr=...) / CLI
MIN_R_PIPS = 5.0        # ignore micro signal candles (stop ~0 -> cost/risk blows up)
ENTRY_VALID = 3
MAX_HOLD = 288           # 24h on 5-min bars
EMA_LEN = 5
ATR_LEN = 14
TREND_LEN = 200


def _cost_usd(lots, spr_entry, spr_exit):
    return ((spr_entry / 2 + spr_exit / 2) + 2 * SLIP_TICKS * TICK) * lots * CONTRACT \
        + COMMISSION_RT_PER_LOT * lots


def build_signals(df: pd.DataFrame, rr: float = RR) -> pd.DataFrame:
    o = df["open"].to_numpy(float); hi = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float); cl = df["close"].to_numpy(float)
    spr = df["spread_mean"].to_numpy(float)
    ts = pd.DatetimeIndex(df["ts"])
    n = len(df)

    ema = pd.Series(cl).ewm(span=EMA_LEN, adjust=False).mean().to_numpy()
    ema200 = pd.Series(cl).ewm(span=TREND_LEN, adjust=False).mean().to_numpy()
    tr = np.maximum(hi - lo, np.maximum(np.abs(hi - np.roll(cl, 1)),
                                        np.abs(lo - np.roll(cl, 1))))
    tr[0] = hi[0] - lo[0]
    atr = pd.Series(tr).rolling(ATR_LEN).mean().to_numpy()
    atr_pct = pd.Series(atr).rolling(2000, min_periods=200).rank(pct=True).to_numpy()
    ema_slope = (ema - np.roll(ema, 5)) / PIP        # pips over last 5 bars

    touch = (lo <= ema) & (ema <= hi)
    short_sig = (lo > ema) & np.roll(touch, 1)
    long_sig = (hi < ema) & np.roll(touch, 1)
    short_sig[0] = long_sig[0] = False

    # pre-signal run length: consecutive bars on the signal side of the EMA
    above = cl > ema
    run = np.zeros(n, int)
    for i in range(1, n):
        run[i] = run[i - 1] + 1 if above[i] == above[i - 1] else 1

    rows = []
    for i in np.where(short_sig | long_sig)[0]:
        if i < TREND_LEN or i + 2 >= n or np.isnan(atr[i]) or atr[i] <= 0:
            continue
        side = -1 if short_sig[i] else 1
        trig = lo[i] if side < 0 else hi[i]
        stop = hi[i] if side < 0 else lo[i]
        R = stop - trig if side < 0 else trig - stop
        if R < MIN_R_PIPS * PIP:
            continue

        # --- entry: stop order within ENTRY_VALID bars -----------------
        ent_i = ent_px = None
        for k in range(i + 1, min(i + 1 + ENTRY_VALID, n)):
            if side < 0 and lo[k] <= trig:
                ent_i, ent_px = k, min(o[k], trig); break
            if side > 0 and hi[k] >= trig:
                ent_i, ent_px = k, max(o[k], trig); break
        if ent_i is None:
            continue

        stop_px = hi[i] if side < 0 else lo[i]
        tgt_px = ent_px - rr * R if side < 0 else ent_px + rr * R
        risk_usd = R * LOT * CONTRACT

        # --- forward walk --------------------------------------------
        outcome, exit_i, r_made = "timeout", min(ent_i + MAX_HOLD, n - 1), 0.0
        for k in range(ent_i, min(ent_i + MAX_HOLD, n)):
            hit_stop = (hi[k] >= stop_px) if side < 0 else (lo[k] <= stop_px)
            hit_tgt = (lo[k] <= tgt_px) if side < 0 else (hi[k] >= tgt_px)
            if hit_stop:
                outcome, exit_i, r_made = "loss", k, -1.0; break
            if hit_tgt:
                outcome, exit_i, r_made = "win", k, rr; break
        if outcome == "timeout":
            px = cl[exit_i]
            r_made = (ent_px - px) / R if side < 0 else (px - ent_px) / R

        cost_r = _cost_usd(LOT, spr[ent_i], spr[exit_i]) / risk_usd
        net_r = r_made - cost_r

        rows.append(dict(
            sig_i=i, side=side, hour=ts[i].hour,
            dow=ts[i].dayofweek,
            session=("asia" if ts[i].hour < 7 else "london" if ts[i].hour < 12
                     else "ny_am" if ts[i].hour < 17 else "ny_pm"),
            R_pips=R / PIP,
            range_bucket=pd.cut([R / PIP], [0, 8, 15, 25, 40, 1e9],
                                labels=["<8", "8-15", "15-25", "25-40", ">40"])[0],
            detach_atr=(lo[i] - ema[i] if side < 0 else ema[i] - hi[i]) / atr[i],
            atr_pct=atr_pct[i],
            atr_regime=("low" if atr_pct[i] < 0.33 else "mid" if atr_pct[i] < 0.66 else "high"),
            trend_align=int((side < 0 and cl[i] < ema200[i]) or (side > 0 and cl[i] > ema200[i])),
            slope_pips=ema_slope[i],
            slope_with=int((side < 0 and ema_slope[i] < 0) or (side > 0 and ema_slope[i] > 0)),
            run_len=run[i],
            entry_lag=ent_i - i,
            cost_r=cost_r,
            outcome=outcome, r_made=r_made, net_r=net_r,
            win=int(outcome == "win"),
        ))
    return pd.DataFrame(rows)


def _slice(s: pd.DataFrame, col, order=None):
    g = s.groupby(col, observed=True).agg(
        n=("win", "size"), win_rate=("win", "mean"),
        exp_gross_R=("r_made", "mean"), exp_net_R=("net_r", "mean"),
        avg_cost_R=("cost_r", "mean"))
    if order is not None:
        g = g.reindex(order)
    return g.round(3)


def report(s: pd.DataFrame, tag: str, rr: float = RR):
    tot = len(s)
    wr = s["win"].mean()
    be = (1 + s["cost_r"].mean()) / (rr + 1)
    be_gross = 1 / (rr + 1)
    print(f"\n########  {tag}  —  {tot:,} triggered signals  ########")
    print(f"1:{rr:g} win-rate {wr:.3f}   (breakeven gross ~{be_gross:.3f}, "
          f"after cost ~{be:.3f})   "
          f"exp gross {s['r_made'].mean():+.3f}R   exp NET {s['net_r'].mean():+.3f}R   "
          f"avg cost {s['cost_r'].mean():.3f}R")
    print(f"by side:              ", dict(s.groupby('side')['win'].mean().round(3)))
    for col, order in [
        ("session", ["asia", "london", "ny_am", "ny_pm"]),
        ("hour", list(range(24))),
        ("dow", [0, 1, 2, 3, 4, 6]),
        ("range_bucket", ["<8", "8-15", "15-25", "25-40", ">40"]),
        ("atr_regime", ["low", "mid", "high"]),
        ("trend_align", [0, 1]),
        ("slope_with", [0, 1]),
        ("run_len", None),
        ("entry_lag", [1, 2, 3]),
    ]:
        sl = s.copy()
        if col == "run_len":
            sl["run_len"] = pd.cut(sl["run_len"], [0, 1, 2, 3, 5, 8, 1e9],
                                   labels=["1", "2", "3", "4-5", "6-8", "9+"])
            order = ["1", "2", "3", "4-5", "6-8", "9+"]
        if col == "detach_atr":
            continue
        print(f"\n--- by {col} ---")
        print(_slice(sl, col, order))
    # 2-D: session x trend_align
    print("\n--- session x trend_align (win-rate / n) ---")
    piv = s.pivot_table(index="session", columns="trend_align", values="win",
                        aggfunc=["mean", "size"]).round(3)
    print(piv.reindex(["asia", "london", "ny_am", "ny_pm"]))
    # best single filter stack
    best = s[(s.session.isin(["london", "ny_am"])) & (s.trend_align == 1)
             & (s.range_bucket.isin(["15-25", "25-40"]))]
    if len(best):
        print(f"\n--- STACK: London/NY-am + with-trend + 15-40p range ---")
        print(f"n={len(best)}  win={best['win'].mean():.3f}  "
              f"exp_net={best['net_r'].mean():+.3f}R")


if __name__ == "__main__":
    import sys
    rrs = [float(x) for x in sys.argv[1:]] or [3.0]
    raw = {sp: load_bars("5min", split=sp).reset_index(drop=True)
           for sp in ("in_sample", "walk_forward")}
    for rr in rrs:
        frames = []
        for split, df in raw.items():
            s = build_signals(df, rr=rr)
            s["split"] = split
            frames.append(s)
            report(s, f"5min / {split}", rr=rr)
        alls = pd.concat(frames, ignore_index=True)
        report(alls, f"5min / COMBINED  (RR=1:{rr:g})", rr=rr)
        out = f"research/ema5_rr{str(rr).replace('.', '_')}_signals.csv"
        alls.to_csv(out, index=False)
        print(f"\nsaved {out}")
