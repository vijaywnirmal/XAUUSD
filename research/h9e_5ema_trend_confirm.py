"""
H9e - the 5 EMA fade, WITH a higher-timeframe trend confirmation.

Reopens the 5-EMA line (closed 2026-09-04 as "still no") for one deliberate,
pre-registered test: does requiring agreement with the 15-min 200-EMA trend
context improve H9d's best bracket, instead of another exit-side tweak?

Entry / exit (identical to H9d, the best-performing bracket so far):
  * 5-min bars, EMA5 of close. Candle fully detached from EMA5 = signal
    candle -> resting stop order at its extreme.
  * $5 initial stop. No fixed target - once +$5 (1R) in favour, trail $5
    behind the running close extreme. Session-flat 21:00 UTC if neither
    fires. NY window 13:00-20:00 UTC. One trade/day.

NEW - trend confirmation (classic "buy dips in an uptrend / sell rallies in
a downtrend"):
  * 15-min EMA200 (same definition as H10), attached to each 5-min bar from
    the last FULLY CLOSED 15-min bar as of that time (no look-ahead).
  * A SHORT fade (candle spiked above EMA5) is only taken if price is BELOW
    the 15-min EMA200 (downtrend context - selling a rally within a downtrend).
  * A LONG fade (candle dropped below EMA5) is only taken if price is ABOVE
    the 15-min EMA200 (uptrend context - buying a dip within an uptrend).
  * Signals disagreeing with the HTF trend are simply skipped (no trade that
    day from that setup; one_trade_per_day still applies to what's left).

Costs: real per-bar Dukascopy spread + $6/lot commission + 1-tick slippage.
Null: same entry bars, random direction, same bracket.

    python -m research.h9e_5ema_trend_confirm --null
"""
import argparse
import numpy as np
import pandas as pd
from scipy import stats

from data_pipeline.dataset import load_bars
from backtest.engine import Backtester, BTConfig
from research.h9_5ema import EMA_N, WIN_START, WIN_END, FLAT_HOUR, summarise

STOP_D = 5.0
TRAIL_ACTIVATE_R = 1.0
TRAIL_D = 5.0
HTF_EMA_N = 200
HTF_TF = "15min"
SLIP_TICKS = 1.0


def attach_htf_trend(df5, tf=HTF_TF, ema_n=HTF_EMA_N):
    """15-min EMA200, causally attached to each 5-min bar from the last
    fully-closed 15-min bar as of that bar's start time."""
    df15 = load_bars(tf, allow_oos=True, columns=["ts", "close"]).sort_values("ts")
    bar_minutes = 15 if tf == "15min" else int(tf.replace("min", ""))
    ema15 = df15["close"].ewm(span=ema_n, adjust=False).mean()
    htf = pd.DataFrame({
        "ts_close": pd.to_datetime(df15["ts"]) + pd.Timedelta(minutes=bar_minutes),
        "ema200_htf": ema15.to_numpy(),
    }).sort_values("ts_close")
    left = df5[["ts"]].sort_values("ts").copy()
    left["ts"] = left["ts"].astype("datetime64[ms, UTC]")
    htf["ts_close"] = htf["ts_close"].astype("datetime64[ms, UTC]")
    merged = pd.merge_asof(left, htf, left_on="ts",
                            right_on="ts_close", direction="backward")
    return merged["ema200_htf"].to_numpy()


def build(df5, counter_trend=False):
    df5 = df5.sort_values("ts").reset_index(drop=True)
    df5["tmin"] = df5["ts"].dt.hour * 60 + df5["ts"].dt.minute
    ema5 = df5["close"].ewm(span=EMA_N, adjust=False).mean().to_numpy()
    hi = df5["high"].to_numpy(float)
    lo = df5["low"].to_numpy(float)
    cl = df5["close"].to_numpy(float)
    tmin = df5["tmin"].to_numpy()
    n = len(df5)

    ema200_htf = attach_htf_trend(df5)

    det_above = lo > ema5          # short setup
    det_below = hi < ema5          # long setup
    below_htf = cl < ema200_htf
    above_htf = cl > ema200_htf
    if counter_trend:
        # OPPOSITE of H9e: only take the fade when it DISAGREES with the
        # 15-min 200-EMA trend (pure counter-trend, no HTF backing at all).
        downtrend, uptrend = above_htf, below_htf
    else:
        downtrend, uptrend = below_htf, above_htf

    l_stop = np.full(n, np.nan)
    s_stop = np.full(n, np.nan)
    stop_d = np.full(n, np.nan)
    trail_d = np.full(n, np.nan)
    n_raw_short = n_raw_long = n_conf_short = n_conf_long = 0
    for i in range(1, n):
        if not (WIN_START <= tmin[i] < WIN_END):
            continue
        if det_above[i - 1]:
            n_raw_short += 1
            if downtrend[i - 1]:
                s_stop[i] = lo[i - 1]
                stop_d[i] = STOP_D
                trail_d[i] = TRAIL_D
                n_conf_short += 1
        elif det_below[i - 1]:
            n_raw_long += 1
            if uptrend[i - 1]:
                l_stop[i] = hi[i - 1]
                stop_d[i] = STOP_D
                trail_d[i] = TRAIL_D
                n_conf_long += 1
    sig = {"long_stop": l_stop, "short_stop": s_stop,
           "stop_dist": stop_d, "trail_dist": trail_d}
    counts = dict(raw_short=n_raw_short, raw_long=n_raw_long,
                  confirmed_short=n_conf_short, confirmed_long=n_conf_long)
    return df5, sig, counts


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
    ap.add_argument("--counter-trend", action="store_true",
                     help="opposite of the base rule: take the fade only when it DISAGREES with the HTF trend")
    args = ap.parse_args()

    df5 = load_bars(args.tf, allow_oos=True,
                    columns=["ts", "open", "high", "low", "close", "spread_mean"])
    df, sig, counts = build(df5, counter_trend=args.counter_trend)

    cfg = BTConfig(session_flat_hour_utc=FLAT_HOUR, one_trade_per_day=True,
                   allow_short=True, reverse_on_opposite=False,
                   size_mode="fixed", size_lots=0.01, slippage_ticks=args.slip,
                   initial_equity=1000.0, trail_activate_r=TRAIL_ACTIVATE_R,
                   trail_ref="close")
    res = Backtester(cfg).run(df, sig)
    tr = res["trades"].copy()
    tr["year"] = pd.to_datetime(tr["entry_ts"]).dt.year

    mode = "COUNTER-trend (opposite of H9e)" if args.counter_trend else "trend-confirmed (H9e)"
    print(f"=== H9{'f' if args.counter_trend else 'e'}  5-EMA fade + 15-min 200-EMA, {mode}  |  "
          f"$5 stop, trail $5 @ +1R  |  1 trade/day  |  NY 13:00-20:00 UTC  |  "
          f"{args.slip}-tick slip ===")
    print(f"    raw setups: {counts['raw_short']} short, {counts['raw_long']} long")
    print(f"    confirmed by HTF trend: {counts['confirmed_short']} short "
          f"({counts['confirmed_short']/max(counts['raw_short'],1)*100:.0f}%), "
          f"{counts['confirmed_long']} long "
          f"({counts['confirmed_long']/max(counts['raw_long'],1)*100:.0f}%)")
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
    if len(tr):
        print("  avg win $%.2f  avg loss $%.2f  avg bars held %.1f"
              % (tr.loc[tr.net_pnl > 0, "net_pnl"].mean(),
                 tr.loc[tr.net_pnl <= 0, "net_pnl"].mean(),
                 tr["bars_held"].mean()))
    by = tr.groupby("year")["net_pnl"].agg(["size", "sum", "mean"]).round(2)
    print("\n  by year (n / net$ / exp$):")
    for y, r in by.iterrows():
        print(f"    {int(y)}  {int(r['size']):3d}  {r['sum']:+8.1f}  {r['mean']:+6.2f}")

    out = ("research/h9f_5ema_counter_trend_trades.csv" if args.counter_trend
           else "research/h9e_5ema_trend_confirm_trades.csv")
    tr.to_csv(out, index=False)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
