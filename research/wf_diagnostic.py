"""
Walk-forward diagnostic (M3): does trend momentum work in 2023-01 -> 2024-06?

Loads history from 2021-06 for signal warm-up, computes H5 (gold-only trend) and
H6 (14-instrument book), then reports metrics restricted to the walk-forward
window. The locked out-of-sample (2024-07 ->) is NOT touched.

    python -m research.wf_diagnostic
"""
import numpy as np
import pandas as pd

from data_pipeline.dataset import load_bars
from research.h5 import trend_signal, vol_scalar, run_positions, perf as perf5
from research.h6 import load_panel, sleeves, portfolio, perf as perf6

WARMUP_START = "2021-06-01"
WF_START = "2023-01-01"
WF_END = "2024-07-01"          # == out-of-sample boundary; exclusive


def _slice_perf(net, equity, lo, hi, perf_fn):
    m = (net.index >= lo) & (net.index < hi)
    n = net[m]
    e = (1.0 + n.fillna(0)).cumprod()
    return perf_fn(n, e)


def gold_daily(start, end):
    df = load_bars("1min", start=start, end=end,
                   columns=["ts", "open", "high", "low", "close", "spread_mean"])
    d = df.set_index("ts").resample("1D").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), spread=("spread_mean", "mean")).dropna(subset=["close"])
    d["spread"] = d["spread"].ffill()
    d["ret"] = np.log(d["close"]).diff()
    return d


def main():
    print("=== WALK-FORWARD DIAGNOSTIC  (2023-01 -> 2024-06, OOS untouched) ===\n")

    # ---- H5: gold-only trend ----
    d = gold_daily(WARMUP_START, WF_END)
    pos = (trend_signal(d["close"]) * vol_scalar(d["ret"])).shift(1)
    R5 = run_positions(d, pos)
    wf5 = _slice_perf(R5["net"], R5["equity"], pd.Timestamp(WF_START, tz="UTC"),
                      pd.Timestamp(WF_END, tz="UTC"), perf5)
    # gold buy&hold on the same window
    bh5 = run_positions(d, pd.Series(1.0, index=d.index))
    wfbh5 = _slice_perf(bh5["net"], bh5["equity"], pd.Timestamp(WF_START, tz="UTC"),
                        pd.Timestamp(WF_END, tz="UTC"), perf5)

    # ---- H6: 14-instrument book ----
    px = load_panel(pd.Timestamp(WARMUP_START, tz="UTC"), pd.Timestamp(WF_END, tz="UTC"))
    slv = sleeves(px)
    P6 = portfolio(px, slv)
    wf6 = _slice_perf(P6["net"], P6["equity"], pd.Timestamp(WF_START, tz="UTC"),
                      pd.Timestamp(WF_END, tz="UTC"), perf6)
    bh6 = portfolio(px, slv, sign_override="long")
    wfbh6 = _slice_perf(bh6["net"], bh6["equity"], pd.Timestamp(WF_START, tz="UTC"),
                        pd.Timestamp(WF_END, tz="UTC"), perf6)
    rs6 = portfolio(px, slv, sign_override="random", seed=7)
    wfrs6 = _slice_perf(rs6["net"], rs6["equity"], pd.Timestamp(WF_START, tz="UTC"),
                        pd.Timestamp(WF_END, tz="UTC"), perf6)

    n_days = int(((R5["net"].index >= pd.Timestamp(WF_START, tz="UTC")) &
                  (R5["net"].index < pd.Timestamp(WF_END, tz="UTC"))).sum())
    print(f"window length: ~{n_days} trading days (~{n_days/252:.2f} yr) - SHORT, wide error bars\n")

    hdr = f"  {'':22s} {'totRet':>8} {'CAGR':>8} {'Sharpe':>7} {'Sortino':>8} {'maxDD':>7} {'ddDays':>7}"
    print("H5 - gold-only trend vs buy&hold:")
    print(hdr)
    for nm, x in [("H5 trend (gold)", wf5), ("gold buy&hold", wfbh5)]:
        print(f"  {nm:22s} {x['total_return']:+8.3f} {x['cagr']:+8.3f} {x['sharpe']:+7.2f} "
              f"{x['sortino']:+8.2f} {x['max_dd']:7.3f} {x['dd_days']:7.0f}")
    print("\nH6 - 14-instrument book vs baselines:")
    print(hdr)
    for nm, x in [("H6 trend book", wf6), ("equal-wt buy&hold", wfbh6), ("random-sign book", wfrs6)]:
        print(f"  {nm:22s} {x['total_return']:+8.3f} {x['cagr']:+8.3f} {x['sharpe']:+7.2f} "
              f"{x['sortino']:+8.2f} {x['max_dd']:7.3f} {x['dd_days']:7.0f}")

    # monthly returns for texture
    def monthly(net):
        s = net[(net.index >= pd.Timestamp(WF_START, tz='UTC')) & (net.index < pd.Timestamp(WF_END, tz='UTC'))]
        return (s.groupby(s.index.to_period('M')).apply(lambda x: (1 + x).prod() - 1) * 100).round(1)
    print("\nH5 gold-trend monthly % :", monthly(R5["net"]).to_dict())
    print("H6 book monthly %       :", monthly(P6["net"]).to_dict())

    print("\n--- read: this is 18 months. Treat Sharpe here as indicative, not decisive. ---")


if __name__ == "__main__":
    main()
