"""
H8 - macro-conditioned gold (EXPLORATORY, in-sample only; the held-out data is spent).

Gold's textbook drivers: 10y real yield (DFII10) and the broad USD index (DTWEXBGS).
Gold should rise when real yields fall AND the dollar falls. Test a regime signal
built from those, vs buy-and-hold and the H5 price-trend.

    python -m research.h8_macro
"""
import argparse
import numpy as np
import pandas as pd

from data_pipeline.dataset import load_bars
from data_pipeline import config as C
from research.h5 import trend_signal, vol_scalar, run_positions, perf, TRADING_DAYS
import os

MACRO = os.path.join(C.ROOT, "macro", "gold_drivers.csv")
LOOKBACK = 20
LEVEL_MA = 200


def gold_daily(start, end):
    df = load_bars("1min", start=start, end=end, allow_oos=False,
                   columns=["ts", "close", "spread_mean"])
    d = df.set_index("ts").resample("1D").agg(close=("close", "last"),
                                              spread=("spread_mean", "mean")).dropna(subset=["close"])
    d["spread"] = d["spread"].ffill()
    d["ret"] = np.log(d["close"]).diff()
    return d


def macro_signals(idx):
    m = pd.read_csv(MACRO, parse_dates=["date"]).set_index("date")
    m.index = m.index.tz_localize("UTC")
    m = m.reindex(idx.union(m.index)).sort_index().ffill().reindex(idx)
    d_ry = m["real_yield"].diff(LOOKBACK)
    d_dxy = np.log(m["dxy"]).diff(LOOKBACK)
    # gold bullish when real yield falls AND dollar falls
    chg = -0.5 * (np.sign(d_ry) + np.sign(d_dxy))
    lvl_ry = (m["real_yield"] < m["real_yield"].rolling(LEVEL_MA).mean()).astype(float) * 2 - 1
    lvl_dxy = (m["dxy"] < m["dxy"].rolling(LEVEL_MA).mean()).astype(float) * 2 - 1
    lvl = -0.5 * (-lvl_ry - lvl_dxy)   # both-below-MA -> +1 (bullish)
    return dict(chg=chg, lvl=(lvl_ry + lvl_dxy) / 2.0), m


def corr_table(d, m, label):
    j = pd.concat([d["ret"], m["real_yield"].diff(), np.log(m["dxy"]).diff()], axis=1).dropna()
    j.columns = ["gold", "d_ry", "d_dxy"]
    print(f"  {label:18s}  corr(gold, d_real_yield)={j['gold'].corr(j['d_ry']):+.2f}   "
          f"corr(gold, d_dollar)={j['gold'].corr(j['d_dxy']):+.2f}   n={len(j)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2009-01-01")
    ap.add_argument("--end", default="2023-01-01")
    ap.add_argument("--eval-start", default=None)
    a = ap.parse_args()
    load_from = "2008-06-01" if a.eval_start else a.start
    d = gold_daily(load_from, a.end)
    sig, m = macro_signals(d.index)
    vs = vol_scalar(d["ret"])

    print(f"gold daily {d.index[0].date()}..{d.index[-1].date()}\n")
    print("driver correlations (daily):")
    corr_table(d, m, "2009-2015")  # rough
    j15 = d.index < "2016-01-01"
    corr_table(d[j15], m[j15], "2009-2015")
    j22 = (d.index >= "2016-01-01") & (d.index < "2022-01-01")
    corr_table(d[j22], m[j22], "2016-2021")
    j26 = d.index >= "2022-01-01"
    corr_table(d[j26], m[j26], "2022+")
    print()

    def run(name, pos):
        pos = pos.shift(1)
        R = run_positions(d, pos)
        net, eq = R["net"], R["equity"]
        if a.eval_start:
            mm = net.index >= pd.Timestamp(a.eval_start, tz="UTC")
            net = net[mm]; eq = (1 + net.fillna(0)).cumprod()
        p = perf(net, eq)
        print(f"  {name:26s} totRet={p['total_return']:+.3f} CAGR={p['cagr']:+.3f} "
              f"Sharpe={p['sharpe']:+.2f} Sortino={p['sortino']:+.2f} maxDD={p['max_dd']:.3f} ddDays={p['dd_days']:.0f}")
        return net

    rng = np.random.default_rng(3)
    print(f"{'strategy':26s} ({'in-sample' if not a.eval_start else 'walk-forward 2023-24'})")
    n_chg = run("H8 macro (d_ regime)", sig["chg"] * vs)
    run("H8 macro (level regime)", sig["lvl"] * vs)
    run("H5 price trend (3m+12m)", trend_signal(d["close"]) * vs)
    run("buy & hold gold", pd.Series(1.0, index=d.index))
    run("random-sign", pd.Series(rng.choice([-1.0, 1.0], size=len(d)), index=d.index) * vs)

    if not a.eval_start:
        e = pd.DataFrame({"net": n_chg}).dropna()
        h1 = (1 + e[e.index < "2016-01-01"]["net"]).prod() - 1
        h2 = (1 + e[(e.index >= "2016-01-01") & (e.index < "2022-01-01")]["net"]).prod() - 1
        h3 = (1 + e[e.index >= "2022-01-01"]["net"]).prod() - 1
        print(f"\n  H8(d_) by sub-period:  2009-15 {h1*100:+.0f}%   2016-21 {h2*100:+.0f}%   2022+ {h3*100:+.0f}%")


if __name__ == "__main__":
    main()
