"""
H9 - the "5 EMA" strategy (Subasish Pani / Power of Stocks), mechanised.

Rule (fade of a candle detached from the 5-period EMA):
  * 5-min bars, EMA5 of close.
  * SHORT signal candle: bar whose whole range is ABOVE the EMA (low > ema).
    -> rest a sell-stop at that candle's LOW.
  * LONG signal candle: bar whose whole range is BELOW the EMA (high < ema).
    -> rest a buy-stop at that candle's HIGH.
  * The resting order refreshes to the newest signal candle each bar while the
    detachment persists; a bar that touches the EMA cancels it.
  * Operator spec: fixed $5 stop, fixed $10 target (keeps Pani's 1:2), and
    ONE trade per day - the first fill inside the NY window 13:00-20:00 UTC.
  * Safety exit: session-flat 21:00 UTC.

Costs: real per-bar Dukascopy spread + $6/lot commission + 1-tick slippage.
Null: same entry bars, random direction, same $5/$10 bracket.

    python -m research.h9_5ema            # base
    python -m research.h9_5ema --null     # + random-direction null
    python -m research.h9_5ema --slip 3   # heavier slippage
"""
import argparse
import numpy as np
import pandas as pd
from scipy import stats

from data_pipeline.dataset import load_bars
from backtest.engine import Backtester, BTConfig

EMA_N = 5
STOP_D = 5.0
TGT_D = 10.0
WIN_START = 13 * 60          # 13:00 UTC
WIN_END = 20 * 60           # 20:00 UTC (last bar a new order may rest on)
FLAT_HOUR = 21
SLIP_TICKS = 1.0


def build(df, stop_d_val=STOP_D, tgt_d_val=TGT_D):
    df = df.sort_values("ts").reset_index(drop=True)
    df["tmin"] = df["ts"].dt.hour * 60 + df["ts"].dt.minute
    ema = df["close"].ewm(span=EMA_N, adjust=False).mean().to_numpy()
    hi = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float)
    tmin = df["tmin"].to_numpy()
    n = len(df)

    det_above = lo > ema          # candle fully above EMA -> short setup
    det_below = hi < ema          # candle fully below EMA -> long setup

    l_stop = np.full(n, np.nan)
    s_stop = np.full(n, np.nan)
    stop_d = np.full(n, np.nan)
    tgt_d = np.full(n, np.nan)
    for i in range(1, n):
        if not (WIN_START <= tmin[i] < WIN_END):
            continue
        stop_d[i] = stop_d_val
        tgt_d[i] = tgt_d_val
        if det_above[i - 1]:
            s_stop[i] = lo[i - 1]
        elif det_below[i - 1]:
            l_stop[i] = hi[i - 1]
    sig = {"long_stop": l_stop, "short_stop": s_stop,
           "stop_dist": stop_d, "target_dist": tgt_d}
    return df, sig


def null_signals(df, real_trades, seed=0, stop_d_val=STOP_D, tgt_d_val=TGT_D):
    """Same entry bars as the real run, random side, same bracket."""
    n = len(df)
    le = np.zeros(n, bool)
    se = np.zeros(n, bool)
    stop_d = np.full(n, np.nan)
    tgt_d = np.full(n, np.nan)
    rng = np.random.default_rng(seed)
    for ei in real_trades["entry_i"].to_numpy():
        j = max(int(ei) - 1, 0)
        (le if rng.random() < 0.5 else se)[j] = True
        for k in (j, min(j + 1, n - 1)):
            stop_d[k] = stop_d_val
            tgt_d[k] = tgt_d_val
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
    ap.add_argument("--tf", default="5min")
    ap.add_argument("--stop-d", type=float, default=STOP_D)
    ap.add_argument("--tgt-d", type=float, default=TGT_D)
    args = ap.parse_args()

    df_all = load_bars(args.tf, allow_oos=True,
                       columns=["ts", "open", "high", "low", "close", "spread_mean"])
    df, sig = build(df_all, stop_d_val=args.stop_d, tgt_d_val=args.tgt_d)

    cfg = BTConfig(session_flat_hour_utc=FLAT_HOUR, one_trade_per_day=True,
                   allow_short=True, reverse_on_opposite=False,
                   size_mode="fixed", size_lots=0.01, slippage_ticks=args.slip,
                   initial_equity=1000.0)
    res = Backtester(cfg).run(df, sig)
    tr = res["trades"].copy()
    tr["year"] = pd.to_datetime(tr["entry_ts"]).dt.year

    rr = args.tgt_d / args.stop_d
    print(f"=== H9  5-EMA fade  |  ${args.stop_d:g} stop / ${args.tgt_d:g} target (1:{rr:g})  |  "
          f"1 trade/day  |  NY 13:00-20:00 UTC  |  {args.slip}-tick slip ===")
    print(f"    {len(tr)} trades over {tr['year'].min()}-{tr['year'].max()}\n")

    null_net = None
    if args.null:
        nres = Backtester(cfg).run(df, null_signals(df, tr, stop_d_val=args.stop_d, tgt_d_val=args.tgt_d))
        nt = nres["trades"]
        null_net = nt["net_pnl"]
        summarise(nt, "NULL (random dir)")

    summarise(tr, "ALL 2009-2026")
    for lo_y, hi_y, lab in [(2009, 2023, "in-sample 2009-2022"),
                            (2023, 2024, "2023 (walk-fwd)"),
                            (2024, 2027, "2024-2026 (OOS spent)")]:
        summarise(tr[(tr.year >= lo_y) & (tr.year < hi_y)], lab)

    ins = tr[tr.year <= 2022]["net_pnl"]
    t0, p0 = stats.ttest_1samp(ins, 0) if len(ins) > 2 else (np.nan, np.nan)
    print(f"\n  in-sample per-trade net vs 0:  t={t0:+.2f}  p={p0:.3f}")
    if null_net is not None:
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

    tag = f"_sl{args.stop_d:g}_tp{args.tgt_d:g}" if (args.stop_d, args.tgt_d) != (STOP_D, TGT_D) else ""
    out = f"research/h9_5ema_trades{tag}.csv"
    tr.to_csv(out, index=False)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
