"""
H9d - the 5 EMA strategy, let winners run (trailing stop instead of a fixed
target), as the 4th deliberate iteration on the 5-EMA line.

H9  (fixed $5 / $10, 1:2):  net negative, real signal (t=+2.72 vs null).
H9b (candle-range stop, 1:2): worse - widening the STOP backfires.
H9c (fixed $5 / $15, 1:3):  still negative but closer to breakeven, both
     out-of-in-sample windows turn positive - only 11% of trades reach the
     wider target, 41% time out at the session flat instead.

H9d's question: if the direction is real (it is), does removing the cap on
the winner - trail instead of a fixed target - let more of those timed-out
trades capture a bigger move before giving it back?

Rule: identical entry to H9 (5-EMA detachment fade, $5 initial stop, NY
window 13:00-20:00 UTC, one trade/day). NO fixed target. Once a trade is
$5 (1R) in profit, ratchet the stop to $5 behind the running extreme
(close-based). Still flat at 21:00 UTC if neither stop nor trail has fired.

    python -m research.h9d_5ema_trail --null
"""
import argparse
import numpy as np
import pandas as pd
from scipy import stats

from data_pipeline.dataset import load_bars
from backtest.engine import Backtester, BTConfig
from research.h9_5ema import EMA_N, WIN_START, WIN_END, FLAT_HOUR, summarise

STOP_D = 5.0
TRAIL_ACTIVATE_R = 1.0     # activate the trail once +1R (+$5) in favour
TRAIL_D = 5.0              # trail $5 behind the running extreme once active
SLIP_TICKS = 1.0


def build(df, trail_d_val=TRAIL_D):
    df = df.sort_values("ts").reset_index(drop=True)
    df["tmin"] = df["ts"].dt.hour * 60 + df["ts"].dt.minute
    ema = df["close"].ewm(span=EMA_N, adjust=False).mean().to_numpy()
    hi = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float)
    tmin = df["tmin"].to_numpy()
    n = len(df)

    det_above = lo > ema
    det_below = hi < ema

    l_stop = np.full(n, np.nan)
    s_stop = np.full(n, np.nan)
    stop_d = np.full(n, np.nan)
    trail_d = np.full(n, np.nan)
    for i in range(1, n):
        if not (WIN_START <= tmin[i] < WIN_END):
            continue
        stop_d[i] = STOP_D
        trail_d[i] = trail_d_val
        if det_above[i - 1]:
            s_stop[i] = lo[i - 1]
        elif det_below[i - 1]:
            l_stop[i] = hi[i - 1]
    sig = {"long_stop": l_stop, "short_stop": s_stop,
           "stop_dist": stop_d, "trail_dist": trail_d}
    return df, sig


def null_signals(df, real_trades, seed=0):
    n = len(df)
    le = np.zeros(n, bool)
    se = np.zeros(n, bool)
    stop_d = np.full(n, np.nan)
    trail_d = np.full(n, np.nan)
    rng = np.random.default_rng(seed)
    for ei in real_trades["entry_i"].to_numpy():
        j = max(int(ei) - 1, 0)
        (le if rng.random() < 0.5 else se)[j] = True
        for k in (j, min(j + 1, n - 1)):
            stop_d[k] = STOP_D
            trail_d[k] = TRAIL_D
    return {"long_entry": le, "short_entry": se,
            "stop_dist": stop_d, "trail_dist": trail_d}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slip", type=float, default=SLIP_TICKS)
    ap.add_argument("--null", action="store_true")
    ap.add_argument("--tf", default="5min")
    ap.add_argument("--activate-r", type=float, default=TRAIL_ACTIVATE_R)
    ap.add_argument("--trail-d", type=float, default=TRAIL_D)
    args = ap.parse_args()

    df_all = load_bars(args.tf, allow_oos=True,
                       columns=["ts", "open", "high", "low", "close", "spread_mean"])
    df, sig = build(df_all, trail_d_val=args.trail_d)

    cfg = BTConfig(session_flat_hour_utc=FLAT_HOUR, one_trade_per_day=True,
                   allow_short=True, reverse_on_opposite=False,
                   size_mode="fixed", size_lots=0.01, slippage_ticks=args.slip,
                   initial_equity=1000.0,
                   trail_activate_r=args.activate_r, trail_ref="close")
    res = Backtester(cfg).run(df, sig)
    tr = res["trades"].copy()
    tr["year"] = pd.to_datetime(tr["entry_ts"]).dt.year

    print(f"=== H9d  5-EMA fade  |  $5 stop, no fixed target  |  "
          f"trail ${args.trail_d:g} once +{args.activate_r:g}R  |  1 trade/day  |  "
          f"NY 13:00-20:00 UTC  |  {args.slip}-tick slip ===")
    print(f"    {len(tr)} trades over {tr['year'].min()}-{tr['year'].max()}\n")

    null_net = None
    if args.null:
        nres = Backtester(cfg).run(df, null_signals(df, tr))
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

    print("\n  exit reasons:", tr["exit_reason"].value_counts().to_dict())
    print("  avg win $%.2f  avg loss $%.2f  avg bars held %.1f"
          % (tr.loc[tr.net_pnl > 0, "net_pnl"].mean(),
             tr.loc[tr.net_pnl <= 0, "net_pnl"].mean(),
             tr["bars_held"].mean()))
    by = tr.groupby("year")["net_pnl"].agg(["size", "sum", "mean"]).round(2)
    print("\n  by year (n / net$ / exp$):")
    for y, r in by.iterrows():
        print(f"    {int(y)}  {int(r['size']):3d}  {r['sum']:+8.1f}  {r['mean']:+6.2f}")

    tr.to_csv("research/h9d_5ema_trail_trades.csv", index=False)
    print("\nwrote research/h9d_5ema_trail_trades.csv")


if __name__ == "__main__":
    main()
