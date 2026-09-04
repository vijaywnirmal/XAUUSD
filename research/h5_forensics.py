"""
H5 forensics — characterise winning vs losing holding periods by the ENTRY
environment, to see whether a mechanism-first filter (trend quality) separates
them. Diagnostic only; any filter it suggests must be tested on walk-forward.

    python -m research.h5_forensics
"""
import numpy as np
import pandas as pd

from data_pipeline.dataset import load_bars
from research.h5 import trend_signal, vol_scalar, run_positions, TRADING_DAYS

WARMUP = "2007-06-01"   # extra history for the signal
IS_END = "2023-01-01"


def daily(start, end):
    df = load_bars("1min", start=start, end=end,
                   columns=["ts", "open", "high", "low", "close", "spread_mean"])
    d = df.set_index("ts").resample("1D").agg(
        close=("close", "last"), spread=("spread_mean", "mean")).dropna(subset=["close"])
    d["spread"] = d["spread"].ffill()
    d["ret"] = np.log(d["close"]).diff()
    return d


def efficiency_ratio(close, win=60):
    """Kaufman efficiency ratio: |net move| / sum|move| over `win` days. 0=chop, 1=trend."""
    net = close.diff(win).abs()
    noise = close.diff().abs().rolling(win).sum()
    return (net / noise).replace([np.inf, -np.inf], np.nan)


def main():
    d = daily(WARMUP, IS_END)
    sig = trend_signal(d["close"])
    vs = vol_scalar(d["ret"])
    pos = (sig * vs).shift(1)
    R = run_positions(d, pos)
    net = R["net"]

    # environment features (all from past data only)
    rvol = (d["ret"].rolling(20).std() * np.sqrt(TRADING_DAYS))
    vol_regime = rvol / rvol.rolling(252).median()
    er = efficiency_ratio(d["close"], 60)
    sgn = np.sign(pos.fillna(0))
    flips = (sgn.diff().abs() > 0).rolling(120).sum()          # whipsaw count last 120d
    trend_age = pd.Series(0, index=d.index)
    age = 0
    prev = 0.0
    for i, s in enumerate(sgn.to_numpy()):
        age = age + 1 if s == prev and s != 0 else 0
        trend_age.iloc[i] = age
        prev = s

    # segment into holding-period trades (constant nonzero sign)
    s = sgn.to_numpy()
    nn = net.fillna(0).to_numpy()
    idx = d.index
    trades = []
    i = 0
    while i < len(s):
        if s[i] == 0:
            i += 1
            continue
        j = i
        while j < len(s) and s[j] == s[i]:
            j += 1
        # entry env = values at bar i (decided at i-1, tradable at i)
        e = max(i - 1, 0)
        tr_ret = np.prod(1 + nn[i:j]) - 1
        trades.append(dict(
            entry=idx[i], exit=idx[min(j, len(s) - 1)], side=int(s[i]),
            bars=j - i, ret=tr_ret, win=tr_ret > 0,
            er=float(er.iloc[e]) if e < len(er) else np.nan,
            vol_regime=float(vol_regime.iloc[e]) if e < len(vol_regime) else np.nan,
            whipsaw120=float(flips.iloc[e]) if e < len(flips) else np.nan,
            sig_strength=abs(float(sig.iloc[e])) if e < len(sig) else np.nan,
            year=idx[i].year,
        ))
        i = j
    t = pd.DataFrame(trades)
    print(f"holding-period trades: {len(t)}   win rate {t['win'].mean()*100:.0f}%   "
          f"mean ret {t['ret'].mean()*100:+.2f}%   total {(np.prod(1+t['ret'])-1)*100:+.0f}%\n")

    def bucketstats(col, edges, label):
        print(f"=== by {label} ===")
        t["_b"] = pd.cut(t[col], edges)
        g = t.groupby("_b", observed=True).agg(n=("ret", "size"), win=("win", "mean"),
                                               mean_ret=("ret", "mean"), tot=("ret", lambda x: (np.prod(1+x)-1)))
        g["win"] *= 100; g["mean_ret"] *= 100; g["tot"] *= 100
        print(g.round(2).to_string())
        print()

    bucketstats("er", [0, .2, .3, .4, .5, 1.0], "trend quality (efficiency ratio, entry)")
    bucketstats("vol_regime", [0, .8, 1.0, 1.25, 1.6, 10], "vol regime (rvol / 1y median)")
    bucketstats("whipsaw120", [-1, 4, 8, 12, 40], "recent whipsaw count (signal flips last 120d)")
    print("=== by side ===")
    print(t.groupby("side").agg(n=("ret", "size"), win=("win", "mean"),
                                mean_ret=("ret", "mean")).assign(win=lambda x: x.win*100).round(3).to_string())
    print("\n=== by year ===")
    print(t.groupby("year").agg(n=("ret", "size"), win=("win", "mean"),
                                mean_ret=("ret", lambda x: x.mean()*100)).assign(win=lambda x: x.win*100).round(1).to_string())

    # what an a-priori ER gate would have done (still IN-SAMPLE — not proof)
    print("\n--- hypothetical: only take trades with entry ER >= 0.35 (mechanism-first gate) ---")
    keep = t[t["er"] >= 0.35]
    print(f"  kept {len(keep)}/{len(t)} trades   win {keep['win'].mean()*100:.0f}%   "
          f"mean ret {keep['ret'].mean()*100:+.2f}%   total {(np.prod(1+keep['ret'])-1)*100:+.0f}%")
    print("  (in-sample only. next step = code it into the daily engine and test on 2023-01..2024-06.)")


if __name__ == "__main__":
    main()
