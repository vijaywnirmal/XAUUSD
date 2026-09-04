"""
H9b - the 5 EMA strategy with the CANONICAL bracket (Pani's actual rule),
as one deliberate second iteration on H9.

Same signal as H9 (research/h9_5ema.py): a candle fully detached from the
5-period EMA on 5-min bars is the signal candle; its extreme is a resting
stop order. What changes vs H9:

  * Stop-loss = the SIGNAL CANDLE'S OPPOSITE extreme (its high for a short,
    its low for a long) - i.e. risk = the candle's own range - instead of a
    fixed $5.
  * Target = 2x that risk (1:2), instead of a fixed $10.
  * Same NY window (13:00-20:00 UTC), one trade/day, 21:00 UTC safety flat.

This is the strategy's own natural bracket, not a fitted one - it is the
textbook rule. Run once, same as H1->H1b: no further tuning after seeing
the result.

    python -m research.h9b_5ema_1r2r            # base
    python -m research.h9b_5ema_1r2r --null      # + random-direction null
    python -m research.h9b_5ema_1r2r --min-range 1.0   # ignore signal candles
                                                          narrower than $1 (cost floor)
"""
import argparse
import numpy as np
import pandas as pd
from scipy import stats

from data_pipeline.dataset import load_bars
from backtest.engine import Backtester, BTConfig
from research.h9_5ema import summarise

EMA_N = 5
WIN_START = 13 * 60
WIN_END = 20 * 60
FLAT_HOUR = 21
SLIP_TICKS = 1.0


def build(df, min_range=0.0):
    df = df.sort_values("ts").reset_index(drop=True)
    df["tmin"] = df["ts"].dt.hour * 60 + df["ts"].dt.minute
    ema = df["close"].ewm(span=EMA_N, adjust=False).mean().to_numpy()
    hi = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float)
    tmin = df["tmin"].to_numpy()
    n = len(df)
    rng = hi - lo

    det_above = (lo > ema) & (rng >= min_range)
    det_below = (hi < ema) & (rng >= min_range)

    l_stop = np.full(n, np.nan)
    s_stop = np.full(n, np.nan)
    stop_d = np.full(n, np.nan)
    tgt_d = np.full(n, np.nan)
    for i in range(1, n):
        if not (WIN_START <= tmin[i] < WIN_END):
            continue
        if det_above[i - 1]:
            r = hi[i - 1] - lo[i - 1]         # candle's own range = risk
            s_stop[i] = lo[i - 1]
            stop_d[i] = r
            tgt_d[i] = 2.0 * r
        elif det_below[i - 1]:
            r = hi[i - 1] - lo[i - 1]
            l_stop[i] = hi[i - 1]
            stop_d[i] = r
            tgt_d[i] = 2.0 * r
    sig = {"long_stop": l_stop, "short_stop": s_stop,
           "stop_dist": stop_d, "target_dist": tgt_d}
    return df, sig


def null_signals(df, sig, real_trades, seed=0):
    """Same entry bars, same per-trade (variable) risk/target, random side."""
    n = len(df)
    le = np.zeros(n, bool)
    se = np.zeros(n, bool)
    stop_d = np.full(n, np.nan)
    tgt_d = np.full(n, np.nan)
    rng = np.random.default_rng(seed)
    sd_arr, td_arr = sig["stop_dist"], sig["target_dist"]
    for ei in real_trades["entry_i"].to_numpy():
        ei = int(ei)
        j = max(ei - 1, 0)
        (le if rng.random() < 0.5 else se)[j] = True
        for k in (j, min(j + 1, n - 1)):
            stop_d[k] = sd_arr[ei]
            tgt_d[k] = td_arr[ei]
    return {"long_entry": le, "short_entry": se,
            "stop_dist": stop_d, "target_dist": tgt_d}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slip", type=float, default=SLIP_TICKS)
    ap.add_argument("--null", action="store_true")
    ap.add_argument("--tf", default="5min")
    ap.add_argument("--min-range", type=float, default=0.0,
                     help="ignore signal candles narrower than this ($) - a cost floor, not a fit")
    args = ap.parse_args()

    df_all = load_bars(args.tf, allow_oos=True,
                       columns=["ts", "open", "high", "low", "close", "spread_mean"])
    df, sig = build(df_all, min_range=args.min_range)

    cfg = BTConfig(session_flat_hour_utc=FLAT_HOUR, one_trade_per_day=True,
                   allow_short=True, reverse_on_opposite=False,
                   size_mode="fixed", size_lots=0.01, slippage_ticks=args.slip,
                   initial_equity=1000.0)
    res = Backtester(cfg).run(df, sig)
    tr = res["trades"].copy()
    tr["year"] = pd.to_datetime(tr["entry_ts"]).dt.year

    print(f"=== H9b  5-EMA fade  |  stop=signal-candle range, target=2x  |  "
          f"1 trade/day  |  NY 13:00-20:00 UTC  |  {args.slip}-tick slip  |  "
          f"min-range=${args.min_range} ===")
    if len(tr):
        print(f"    {len(tr)} trades over {tr['year'].min()}-{tr['year'].max()}\n")

    null_net = None
    if args.null:
        nres = Backtester(cfg).run(df, null_signals(df, sig, tr))
        nt = nres["trades"]
        null_net = nt["net_pnl"]
        summarise(nt, "NULL (random dir)")

    summarise(tr, "ALL 2009-2026")
    for lo_y, hi_y, lab in [(2009, 2023, "in-sample 2009-2022"),
                            (2023, 2024, "2023 (walk-fwd)"),
                            (2024, 2027, "2024-2026 (OOS spent)")]:
        summarise(tr[(tr.year >= lo_y) & (tr.year < hi_y)], lab)

    ins = tr[tr.year <= 2022]["net_pnl"]
    if len(ins) > 2:
        t0, p0 = stats.ttest_1samp(ins, 0)
        print(f"\n  in-sample per-trade net vs 0:  t={t0:+.2f}  p={p0:.3f}")
    if null_net is not None and len(ins) > 2:
        tw, pw = stats.ttest_ind(ins, null_net, equal_var=False)
        print(f"  in-sample vs random-dir null:  Welch t={tw:+.2f}  p={pw:.3f}")

    # per-trade R (net_pnl / risk_usd) - the cleanest cost-agnostic-ish view
    r = tr["r_multiple"].dropna()
    if len(r):
        print(f"\n  mean R-multiple all trades: {r.mean():+.3f}  (win rate {(r>0).mean()*100:.1f}%)")

    print("\n  exit reasons:", tr["exit_reason"].value_counts().to_dict())
    if len(tr):
        print("  avg win $%.2f  avg loss $%.2f  avg bars held %.1f  avg risk $%.2f"
              % (tr.loc[tr.net_pnl > 0, "net_pnl"].mean(),
                 tr.loc[tr.net_pnl <= 0, "net_pnl"].mean(),
                 tr["bars_held"].mean(),
                 (tr["net_pnl"] / tr["r_multiple"]).abs().median()))
    by = tr.groupby("year")["net_pnl"].agg(["size", "sum", "mean"]).round(2)
    print("\n  by year (n / net$ / exp$):")
    for y, r_ in by.iterrows():
        print(f"    {int(y)}  {int(r_['size']):3d}  {r_['sum']:+8.1f}  {r_['mean']:+6.2f}")

    tr.to_csv("research/h9b_5ema_1r2r_trades.csv", index=False)
    print("\nwrote research/h9b_5ema_1r2r_trades.csv")


if __name__ == "__main__":
    main()
