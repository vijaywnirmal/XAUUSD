"""
H10 - the "200 EMA tap" strategy (trend-continuation pullback fade), 15-min bars.

Rule (operator spec + defaults chosen after clarification):
  * 15-min bars, EMA200 of close.
  * SHORT signal candle: downtrend context (close < EMA200) whose high still
    reaches UP to tap/cross the EMA (high >= EMA200) - price pulled back into
    the average and closed back below it. Rest a sell-stop at that candle's LOW.
  * LONG signal candle (symmetric, operator opted in): uptrend context
    (close > EMA200) whose low taps DOWN to the EMA (low <= EMA200), closed
    back above it. Rest a buy-stop at that candle's HIGH.
  * Stop-loss = the signal candle's own range (its opposite extreme).
    Target = 2x that range (1:2). [operator choice: "candle-range stop, 1:2"]
  * ONE trade per day (first fill), no session filter - 200 EMA context is a
    slower signal than the 5-EMA scalp, checked round the clock.
  * Safety time-stop: 200 bars (~50 hours) if neither stop nor target fires -
    a risk backstop, not a tuned exit; 15-min swing trades can legitimately
    take longer than a session to resolve.

Costs: real per-bar Dukascopy spread + $6/lot commission + 1-tick slippage.
Null: same entry bars, random direction, same per-trade bracket.

    python -m research.h10_ema200_tap --null
"""
import argparse
import numpy as np
import pandas as pd
from scipy import stats

from data_pipeline.dataset import load_bars
from backtest.engine import Backtester, BTConfig

EMA_N = 200
MAX_HOLD_BARS = 200
SLIP_TICKS = 1.0


def build(df, min_range=0.0):
    df = df.sort_values("ts").reset_index(drop=True)
    ema = df["close"].ewm(span=EMA_N, adjust=False).mean().to_numpy()
    hi = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float)
    cl = df["close"].to_numpy(float)
    n = len(df)
    rng = hi - lo

    short_setup = (cl < ema) & (hi >= ema) & (rng >= min_range)   # downtrend, tapped up into EMA
    long_setup = (cl > ema) & (lo <= ema) & (rng >= min_range)    # uptrend, tapped down into EMA

    l_stop = np.full(n, np.nan)
    s_stop = np.full(n, np.nan)
    stop_d = np.full(n, np.nan)
    tgt_d = np.full(n, np.nan)
    for i in range(1, n):
        if short_setup[i - 1]:
            r = hi[i - 1] - lo[i - 1]
            s_stop[i] = lo[i - 1]
            stop_d[i] = r
            tgt_d[i] = 2.0 * r
        elif long_setup[i - 1]:
            r = hi[i - 1] - lo[i - 1]
            l_stop[i] = hi[i - 1]
            stop_d[i] = r
            tgt_d[i] = 2.0 * r
    sig = {"long_stop": l_stop, "short_stop": s_stop,
           "stop_dist": stop_d, "target_dist": tgt_d}
    n_setups = int(short_setup.sum() + long_setup.sum())
    return df, sig, n_setups


def null_signals(df, sig, real_trades, seed=0):
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


def summarise(tr, label):
    if len(tr) == 0:
        print(f"  {label:24s} no trades")
        return
    net = tr["net_pnl"]
    wins = net[net > 0]
    losses = net[net <= 0]
    pf = wins.sum() / -losses.sum() if len(losses) and losses.sum() != 0 else np.inf
    eq = 1000 + net.cumsum()
    dd = (eq - eq.cummax()).min()
    print(f"  {label:24s} n={len(tr):4d}  win={len(wins)/len(tr)*100:4.1f}%  "
          f"exp=${net.mean():+6.3f}  PF={pf:4.2f}  "
          f"gross=${tr['gross_pnl'].sum():+7.0f}  cost=${tr['cost'].sum():6.0f}  "
          f"net=${net.sum():+7.0f}  maxDD=${dd:+6.0f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slip", type=float, default=SLIP_TICKS)
    ap.add_argument("--null", action="store_true")
    ap.add_argument("--tf", default="15min")
    ap.add_argument("--min-range", type=float, default=1.0,
                     help="ignore signal candles narrower than this $ (degenerate-candle floor, H9b lesson)")
    args = ap.parse_args()

    df_all = load_bars(args.tf, allow_oos=True,
                       columns=["ts", "open", "high", "low", "close", "spread_mean"])
    df, sig, n_setups = build(df_all, min_range=args.min_range)

    cfg = BTConfig(one_trade_per_day=True, allow_short=True,
                   reverse_on_opposite=False, size_mode="fixed", size_lots=0.01,
                   slippage_ticks=args.slip, initial_equity=1000.0,
                   max_hold_bars=MAX_HOLD_BARS)
    res = Backtester(cfg).run(df, sig)
    tr = res["trades"].copy()
    tr["year"] = pd.to_datetime(tr["entry_ts"]).dt.year

    print(f"=== H10  200-EMA tap  |  candle-range stop, 1:2 target  |  both directions  |  "
          f"1 trade/day, 24h  |  {args.slip}-tick slip  |  min-range=${args.min_range} ===")
    print(f"    {n_setups} raw signal candles -> {len(tr)} trades over "
          f"{tr['year'].min()}-{tr['year'].max()}\n")

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

    print("\n  exit reasons:", tr["exit_reason"].value_counts().to_dict())
    if len(tr):
        print("  avg win $%.2f  avg loss $%.2f  avg bars held %.1f  avg risk $%.2f"
              % (tr.loc[tr.net_pnl > 0, "net_pnl"].mean(),
                 tr.loc[tr.net_pnl <= 0, "net_pnl"].mean(),
                 tr["bars_held"].mean(),
                 (tr["net_pnl"] / tr["r_multiple"]).abs().median()))
    by = tr.groupby("year")["net_pnl"].agg(["size", "sum", "mean"]).round(2)
    print("\n  by year (n / net$ / exp$):")
    for y, r in by.iterrows():
        print(f"    {int(y)}  {int(r['size']):3d}  {r['sum']:+8.1f}  {r['mean']:+6.2f}")

    tr.to_csv("research/h10_ema200_tap_trades.csv", index=False)
    print("\nwrote research/h10_ema200_tap_trades.csv")


if __name__ == "__main__":
    main()
