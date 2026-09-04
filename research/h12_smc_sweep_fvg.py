"""
H12 - "Smart Money Concepts": liquidity sweep -> displacement -> Fair Value
Gap -> 50% equilibrium entry, off the previous day's high/low.

Source: operator-supplied recipe (ACY Securities SMC guide). Every step in
that recipe is discretionary trader language; here is the mechanical,
non-fitted translation used for this backtest (operator confirmed PDH/PDL +
5-min via clarification):

  1. KEY LEVEL: previous trading day's high/low (PDH/PDL). Trading day =
     21:00 UTC to 21:00 UTC (matches the project's existing gold-session
     convention in qa_report.py).
  2. LIQUIDITY SWEEP: a 5-min candle wicks through PDH/PDL and closes back
     on the other side - price traded through the level and failed to hold.
  3. DISPLACEMENT: that same candle's range is >=1.5x the trailing 20-bar
     average range, closing in the outer 25% of its own range, away from
     the swept level - a fixed "big impulse candle" threshold, not fitted.
  4. FAIR VALUE GAP: the standard ICT 3-candle gap around the displacement
     candle (candle[i-1] vs candle[i+1]), confirmed one bar after the
     displacement candle (causal - the gap isn't known to exist until the
     3rd candle prints).
  5. ENTRY: the recipe says "limit order at the 50% equilibrium of the
     FVG." The engine only supports market/stop-order fills, not resting
     limit orders with the opposite fill sense a limit needs, so this is
     approximated as: a MARKET entry the bar after price first touches the
     FVG midpoint (t+1 open, same look-ahead-safe convention used
     throughout this project) - economically the same idea, executed one
     bar later and at the open instead of exactly at the limit price
     (if anything, a slightly WORSE fill than a true limit, i.e.
     conservative). Only active during the stated session windows,
     literal EST (UTC-5, not DST-adjusted, as written in the source):
     London 00:00-06:00 EST = 05:00-11:00 UTC, NY 09:30-12:00 EST =
     14:30-17:00 UTC. Abandoned if untouched within 48 bars (4h).
  6. STOP: just beyond the sweep candle's wick (+/- $0.50 buffer).
  7. TARGET: fixed 1:2 R:R ("aim for a minimum of 1:2" in the source -
     "next opposing liquidity pool" is too discretionary to code
     non-circularly, so the literal minimum is used instead).

One trade/day, 0.01 lot, $1,000 account. Safety time-stop 200 bars.

Costs: real per-bar Dukascopy spread + $6/lot commission + 1-tick slippage.
Null: same entry bars, random direction, same per-trade bracket.

    python -m research.h12_smc_sweep_fvg --null
"""
import argparse
import numpy as np
import pandas as pd
from scipy import stats

from data_pipeline.dataset import load_bars
from backtest.engine import Backtester, BTConfig

DAY_ROLL_HOUR = 21     # UTC trading-day boundary (matches qa_report.py)
DISP_RANGE_MULT = 1.5
DISP_CLOSE_POS = 0.25
BUFFER = 0.50
TOUCH_WINDOW_BARS = 48   # 4h to wait for the FVG midpoint to be touched
MAX_HOLD_BARS = 200
RR = 2.0
# session windows, literal EST (UTC-5) per the source, in minutes-of-day UTC
LONDON = (5 * 60, 11 * 60)
NY = (14 * 60 + 30, 17 * 60)
SLIP_TICKS = 1.0


def _in_session(tmin):
    return ((tmin >= LONDON[0]) & (tmin < LONDON[1])) | ((tmin >= NY[0]) & (tmin < NY[1]))


def build(df):
    df = df.sort_values("ts").reset_index(drop=True)
    ts = df["ts"]
    df["tmin"] = ts.dt.hour * 60 + ts.dt.minute
    df["trading_date"] = (ts - pd.Timedelta(hours=DAY_ROLL_HOUR)).dt.date

    hi = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float)
    cl = df["close"].to_numpy(float)
    tmin = df["tmin"].to_numpy()
    n = len(df)
    rng = hi - lo

    # PDH/PDL: previous trading day's high/low, mapped onto every bar of "today"
    daily = df.groupby("trading_date").agg(day_hi=("high", "max"), day_lo=("low", "min"))
    daily = daily.sort_index()
    daily["pdh"] = daily["day_hi"].shift(1)
    daily["pdl"] = daily["day_lo"].shift(1)
    pdh_map = daily["pdh"].to_dict()
    pdl_map = daily["pdl"].to_dict()
    pdh = df["trading_date"].map(pdh_map).to_numpy(float)
    pdl = df["trading_date"].map(pdl_map).to_numpy(float)

    avg_range20 = pd.Series(rng).shift(1).rolling(20).mean().to_numpy()
    close_pos = np.divide(cl - lo, rng, out=np.full(n, np.nan), where=rng > 0)

    sweep_short = (hi > pdh) & (cl < pdh)
    sweep_long = (lo < pdl) & (cl > pdl)
    disp_short = sweep_short & (rng >= DISP_RANGE_MULT * avg_range20) & (close_pos <= DISP_CLOSE_POS)
    disp_long = sweep_long & (rng >= DISP_RANGE_MULT * avg_range20) & (close_pos >= 1 - DISP_CLOSE_POS)

    le = np.zeros(n, bool)
    se = np.zeros(n, bool)
    stop_d = np.full(n, np.nan)
    tgt_d = np.full(n, np.nan)
    n_disp = n_fvg = n_touched = 0

    for i in range(1, n - 1):
        if disp_short[i]:
            n_disp += 1
            # bearish FVG: candle i-1's low above candle i+1's high
            gap_top, gap_bot = lo[i - 1], hi[i + 1]
            if gap_top > gap_bot:
                n_fvg += 1
                mid = 0.5 * (gap_top + gap_bot)
                stop_lvl = hi[i] + BUFFER
                risk = stop_lvl - mid
                if risk > 0:
                    for k in range(i + 2, min(i + 2 + TOUCH_WINDOW_BARS, n)):
                        if _in_session(tmin[k]) and hi[k] >= mid:
                            se[k] = True
                            stop_d[k] = risk
                            tgt_d[k] = RR * risk
                            n_touched += 1
                            break
        elif disp_long[i]:
            n_disp += 1
            gap_bot, gap_top = hi[i - 1], lo[i + 1]
            if gap_top > gap_bot:
                n_fvg += 1
                mid = 0.5 * (gap_top + gap_bot)
                stop_lvl = lo[i] - BUFFER
                risk = mid - stop_lvl
                if risk > 0:
                    for k in range(i + 2, min(i + 2 + TOUCH_WINDOW_BARS, n)):
                        if _in_session(tmin[k]) and lo[k] <= mid:
                            le[k] = True
                            stop_d[k] = risk
                            tgt_d[k] = RR * risk
                            n_touched += 1
                            break

    sig = {"long_entry": le, "short_entry": se, "stop_dist": stop_d, "target_dist": tgt_d}
    counts = dict(displacement_candles=n_disp, valid_fvg=n_fvg, touched=n_touched)
    return df, sig, counts


def null_signals(df, sig, real_trades, seed=0):
    n = len(df)
    le = np.zeros(n, bool)
    se = np.zeros(n, bool)
    stop_d = np.full(n, np.nan)
    tgt_d = np.full(n, np.nan)
    rng = np.random.default_rng(seed)
    sd_arr, td_arr = sig["stop_dist"], sig["target_dist"]
    real_le = sig["long_entry"]
    for ei in real_trades["entry_i"].to_numpy():
        ei = int(ei)
        j = max(ei - 1, 0)
        (le if rng.random() < 0.5 else se)[j] = True
        stop_d[j] = sd_arr[j] if not np.isnan(sd_arr[j]) else sd_arr[ei]
        tgt_d[j] = td_arr[j] if not np.isnan(td_arr[j]) else td_arr[ei]
    return {"long_entry": le, "short_entry": se, "stop_dist": stop_d, "target_dist": tgt_d}


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
    ap.add_argument("--tf", default="5min")
    args = ap.parse_args()

    df_all = load_bars(args.tf, allow_oos=True,
                       columns=["ts", "open", "high", "low", "close", "spread_mean"])
    df, sig, counts = build(df_all)

    cfg = BTConfig(one_trade_per_day=True, allow_short=True, reverse_on_opposite=False,
                   size_mode="fixed", size_lots=0.01, slippage_ticks=args.slip,
                   initial_equity=1000.0, max_hold_bars=MAX_HOLD_BARS)
    res = Backtester(cfg).run(df, sig)
    tr = res["trades"].copy()
    tr["year"] = pd.to_datetime(tr["entry_ts"]).dt.year

    print(f"=== H12  SMC sweep -> displacement -> FVG -> equilibrium entry  |  "
          f"PDH/PDL, 5-min, 1:2 R:R  |  London/NY session  |  1 trade/day  |  "
          f"{args.slip}-tick slip ===")
    print(f"    {counts['displacement_candles']} displacement candles -> "
          f"{counts['valid_fvg']} valid FVGs -> {counts['touched']} touched -> "
          f"{len(tr)} trades over {tr['year'].min() if len(tr) else '-'}"
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

    tr.to_csv("research/h12_smc_sweep_fvg_trades.csv", index=False)
    print("\nwrote research/h12_smc_sweep_fvg_trades.csv")


if __name__ == "__main__":
    main()
