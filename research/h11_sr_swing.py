"""
H11 - intraday support/resistance swing fade, with risk-based position sizing
and structure-anchored stop + trail. New family (not part of the 5-EMA line).

Spec (operator choices after clarification):
  * 15-min bars. Support/resistance = prior N=96-bar (24h) swing extremes:
      support[i]    = min(low)  over bars [i-96, i-1]   (causal, shift(1))
      resistance[i] = max(high) over bars [i-96, i-1]
  * FADE the level (bounce), not a breakout:
      - LONG setup: bar i taps support (low[i] <= support[i]) and closes back
        ABOVE it (close[i] > support[i]) - a rejection candle. Rest a
        buy-stop at that candle's HIGH (confirmation the bounce continues).
      - SHORT setup: bar i taps resistance (high[i] >= resistance[i]) and
        closes back BELOW it (close[i] < resistance[i]). Rest a sell-stop at
        that candle's LOW.
  * STRUCTURE stop: placed just beyond the level itself (support - $0.50 buffer
    for longs, resistance + $0.50 for shorts) - if the level truly breaks,
    the trade is wrong. Risk = distance from the planned entry (signal
    candle's extreme) to that structural stop.
  * Trail once +1R in favour (H9d's best mechanic): once the trade is up one
    initial-risk unit, trail the stop by that same distance behind the
    running close extreme. No fixed target.
  * POSITION SIZE: risk_pct sizing - risk 1% of current equity per trade,
    lot size derived from the stop distance (size_mode="risk_pct" in the
    engine). Position grows/shrinks with the account.
  * One trade/day (first valid fill), 24h (no session filter - S/R is not a
    session-specific idea). Safety time-stop 200 bars (~50h).

Costs: real per-bar Dukascopy spread + $6/lot commission + 1-tick slippage.
Null: same entry bars, random direction, same per-trade risk/trail.

    python -m research.h11_sr_swing --null
"""
import argparse
import numpy as np
import pandas as pd
from scipy import stats

from data_pipeline.dataset import load_bars
from backtest.engine import Backtester, BTConfig

LOOKBACK = 96          # 24h of 15-min bars
BUFFER = 0.50
MAX_HOLD_BARS = 200
RISK_PCT = 0.01
SLIP_TICKS = 1.0


def build(df):
    df = df.sort_values("ts").reset_index(drop=True)
    hi = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float)
    cl = df["close"].to_numpy(float)
    n = len(df)

    support = df["low"].shift(1).rolling(LOOKBACK).min().to_numpy()
    resistance = df["high"].shift(1).rolling(LOOKBACK).max().to_numpy()

    long_setup = (lo <= support) & (cl > support)
    short_setup = (hi >= resistance) & (cl < resistance)

    # planned risk per signal candle: entry at its extreme, stop beyond the level
    planned_stop = np.full(n, np.nan)
    for i in range(n):
        if long_setup[i]:
            stop_lvl = support[i] - BUFFER
            r = hi[i] - stop_lvl
            if r > 0:
                planned_stop[i] = r
            else:
                long_setup[i] = False
        elif short_setup[i]:
            stop_lvl = resistance[i] + BUFFER
            r = stop_lvl - lo[i]
            if r > 0:
                planned_stop[i] = r
            else:
                short_setup[i] = False

    l_stop = np.full(n, np.nan)
    s_stop = np.full(n, np.nan)
    stop_d = np.full(n, np.nan)
    trail_d = np.full(n, np.nan)
    for i in range(1, n):
        if long_setup[i - 1]:
            l_stop[i] = hi[i - 1]
            stop_d[i] = planned_stop[i - 1]
            trail_d[i] = planned_stop[i - 1]
        elif short_setup[i - 1]:
            s_stop[i] = lo[i - 1]
            stop_d[i] = planned_stop[i - 1]
            trail_d[i] = planned_stop[i - 1]

    sig = {"long_stop": l_stop, "short_stop": s_stop,
           "stop_dist": stop_d, "trail_dist": trail_d}
    counts = dict(long_setups=int(long_setup.sum()), short_setups=int(short_setup.sum()))
    return df, sig, counts


def null_signals(df, sig, real_trades, seed=0):
    n = len(df)
    le = np.zeros(n, bool)
    se = np.zeros(n, bool)
    stop_d = np.full(n, np.nan)
    trail_d = np.full(n, np.nan)
    rng = np.random.default_rng(seed)
    sd_arr, td_arr = sig["stop_dist"], sig["trail_dist"]
    for ei in real_trades["entry_i"].to_numpy():
        ei = int(ei)
        j = max(ei - 1, 0)
        (le if rng.random() < 0.5 else se)[j] = True
        for k in (j, min(j + 1, n - 1)):
            stop_d[k] = sd_arr[ei]
            trail_d[k] = td_arr[ei]
    return {"long_entry": le, "short_entry": se,
            "stop_dist": stop_d, "trail_dist": trail_d}


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
    ap.add_argument("--risk-pct", type=float, default=RISK_PCT)
    args = ap.parse_args()

    df_all = load_bars(args.tf, allow_oos=True,
                       columns=["ts", "open", "high", "low", "close", "spread_mean"])
    df, sig, counts = build(df_all)

    cfg = BTConfig(one_trade_per_day=True, allow_short=True, reverse_on_opposite=False,
                   size_mode="risk_pct", risk_pct=args.risk_pct, slippage_ticks=args.slip,
                   initial_equity=1000.0, max_hold_bars=MAX_HOLD_BARS,
                   trail_activate_r=1.0, trail_ref="close")
    res = Backtester(cfg).run(df, sig)
    tr = res["trades"].copy()
    tr["year"] = pd.to_datetime(tr["entry_ts"]).dt.year

    print(f"=== H11  S/R swing fade  |  96-bar (24h) swing levels, structure stop, "
          f"trail @ +1R  |  risk {args.risk_pct*100:.1f}%/trade  |  1 trade/day, 24h  |  "
          f"{args.slip}-tick slip ===")
    print(f"    {counts['long_setups']} long setups, {counts['short_setups']} short setups "
          f"-> {len(tr)} trades over {tr['year'].min() if len(tr) else '-'}"
          f"-{tr['year'].max() if len(tr) else '-'}\n")

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

    # per-trade R (net_pnl / risk_usd) - the size-agnostic view, since lot size varies
    r = tr["r_multiple"].dropna()
    if len(r):
        print(f"\n  mean R-multiple: {r.mean():+.3f}  in-sample mean R: "
              f"{tr.loc[tr.year<=2022,'r_multiple'].mean():+.3f}")

    print("\n  exit reasons:", tr["exit_reason"].value_counts().to_dict())
    if len(tr):
        print("  avg win $%.2f  avg loss $%.2f  avg bars held %.1f  avg lot %.3f  final equity $%.0f"
              % (tr.loc[tr.net_pnl > 0, "net_pnl"].mean(),
                 tr.loc[tr.net_pnl <= 0, "net_pnl"].mean(),
                 tr["bars_held"].mean(), tr["size_lots"].mean(),
                 1000 + tr["net_pnl"].sum()))
    by = tr.groupby("year")["net_pnl"].agg(["size", "sum", "mean"]).round(2)
    print("\n  by year (n / net$ / exp$):")
    for y, r_ in by.iterrows():
        print(f"    {int(y)}  {int(r_['size']):3d}  {r_['sum']:+9.1f}  {r_['mean']:+7.2f}")

    tr.to_csv("research/h11_sr_swing_trades.csv", index=False)
    print("\nwrote research/h11_sr_swing_trades.csv")


if __name__ == "__main__":
    main()
