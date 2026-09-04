"""
NFP straddle backtest.

Every NFP release: place an OCO pair of stop orders around the pre-release 30-min
range (buy-stop above the high, sell-stop below the low, + buffer). Whichever
triggers is the trade. Fixed $30 stop-loss. Exit: session-flat at 20:00 UTC, or
an optional take-profit. One trade per NFP day.

Costs: real per-bar Dukascopy spread + commission + extra release-window slippage.

    python -m research.nfp_straddle                 # default: no TP, session flat
    python -m research.nfp_straddle --tp-r 1.5      # add a 1.5R take-profit
"""
import argparse
import numpy as np
import pandas as pd
from datetime import date, timedelta

from data_pipeline.dataset import load_bars
from backtest.engine import Backtester, BTConfig
from research.nfp_study import us_dst, first_fridays

STOP_DOLLARS = 30.0
BOX_MIN = 30          # pre-release box length (minutes)
BUFFER = 0.50         # $ beyond the box edge for the stop order
ENTRY_WINDOW_MIN = 90  # minutes after release to keep the OCO live
FLAT_HOUR = 20
NEWS_SLIP_TICKS = 3.0  # extra slippage on the release-window fill


def build(df, tp_r=None, buffer=BUFFER):
    df = df.sort_values("ts").reset_index(drop=True)
    df["d"] = df["ts"].dt.normalize()
    df["tmin"] = df["ts"].dt.hour * 60 + df["ts"].dt.minute
    nfp = first_fridays(pd.Series(sorted(df["d"].unique())))

    n = len(df)
    tmin = df["tmin"].to_numpy()
    dates = df["ts"].dt.date.to_numpy()
    hi = df["high"].to_numpy(); lo = df["low"].to_numpy()

    # per NFP date: pre-release box hi/lo
    box = {}
    for d0 in nfp:
        rel = 750 if us_dst(d0) else 810
        g = df[(df["ts"].dt.date == d0) & (tmin >= rel - BOX_MIN) & (tmin < rel)]
        if len(g) >= 4:
            box[d0] = (g["high"].max(), g["low"].min(), rel)

    l_stop = np.full(n, np.nan); s_stop = np.full(n, np.nan)
    stop_d = np.full(n, np.nan); tgt_d = np.full(n, np.nan)
    for i in range(n):
        rec = box.get(dates[i])
        if rec is None:
            continue
        bh, bl, rel = rec
        if not (rel <= tmin[i] < rel + ENTRY_WINDOW_MIN):
            continue
        l_stop[i] = bh + buffer
        s_stop[i] = bl - buffer
        stop_d[i] = STOP_DOLLARS
        if tp_r:
            tgt_d[i] = STOP_DOLLARS * tp_r
    sig = {"long_stop": l_stop, "short_stop": s_stop, "stop_dist": stop_d}
    if tp_r:
        sig["target_dist"] = tgt_d
    return df, sig, len(box)


def report(res, label):
    tr = res["trades"]
    if len(tr) == 0:
        print(f"  {label}: no trades"); return
    net = tr["net_pnl"]
    wins = net[net > 0]; losses = net[net <= 0]
    pf = wins.sum() / -losses.sum() if len(losses) and losses.sum() != 0 else np.inf
    eq = 1000 + net.cumsum()
    dd = (eq - eq.cummax()).min()
    print(f"  {label:22s} n={len(tr):3d}  win={len(wins)/len(tr)*100:4.1f}%  "
          f"exp=${net.mean():+6.2f}  PF={pf:4.2f}  gross=${tr['gross_pnl'].sum():+7.0f}  "
          f"cost=${tr['cost'].sum():6.0f}  net=${net.sum():+7.0f}  maxDD=${dd:+6.0f}")
    return tr


def null_signals(df, sig, seed=0):
    """Same NFP days, same $30 stop / session-flat, but a random direction chosen
    at the release (market entry on the release bar), not the break direction."""
    n = len(df)
    tmin = df["tmin"].to_numpy()
    dates = df["ts"].dt.date.to_numpy()
    ls, ss = sig["long_stop"], sig["short_stop"]
    # release bar per date = first bar where a stop level is set
    rng = np.random.default_rng(seed)
    le = np.zeros(n, bool); se = np.zeros(n, bool)
    stop_d = np.full(n, np.nan)
    seen = set()
    for i in range(n):
        if np.isnan(ls[i]) or dates[i] in seen:
            continue
        seen.add(dates[i])
        (le if rng.random() < 0.5 else se)[max(i - 1, 0)] = True   # fills next (release) bar
        stop_d[i] = STOP_DOLLARS
        stop_d[max(i - 1, 0)] = STOP_DOLLARS
    return {"long_entry": le, "short_entry": se, "stop_dist": stop_d}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tp-r", type=float, default=None, help="take-profit in R (stop=1R=$30)")
    ap.add_argument("--tf", default="5min")
    ap.add_argument("--slip", type=float, default=NEWS_SLIP_TICKS, help="news-window slippage in ticks")
    ap.add_argument("--buffer", type=float, default=BUFFER)
    ap.add_argument("--null", action="store_true", help="also run the random-direction null")
    args = ap.parse_args()
    df_all = load_bars(args.tf, allow_oos=True,
                       columns=["ts", "open", "high", "low", "close", "spread_mean"])
    df, sig, n_events = build(df_all, tp_r=args.tp_r, buffer=args.buffer)
    print(f"NFP events with a usable pre-release box: {n_events}  "
          f"(buffer ${args.buffer}, slip {args.slip} ticks)\n")

    cfg = BTConfig(session_flat_hour_utc=FLAT_HOUR, one_trade_per_day=True,
                   allow_short=True, reverse_on_opposite=False,
                   size_mode="fixed", size_lots=0.01, slippage_ticks=args.slip,
                   initial_equity=1000.0)
    res = Backtester(cfg).run(df, sig)
    if args.null:
        nres = Backtester(cfg).run(df, null_signals(df, sig))
        nt = nres["trades"]
        nn = nt["net_pnl"]
        print(f"  NULL (random dir)      n={len(nt):3d}  win={(nn>0).mean()*100:4.1f}%  "
              f"exp=${nn.mean():+6.2f}  net=${nn.sum():+7.0f}\n")
    tr = res["trades"].copy()
    tr["year"] = pd.to_datetime(tr["entry_ts"]).dt.year

    tp_txt = f"TP {args.tp_r}R (${STOP_DOLLARS*args.tp_r:.0f})" if args.tp_r else "no TP, flat 20:00 UTC"
    print(f"=== NFP straddle  |  $30 stop  |  {tp_txt}  |  0.01 lot  |  {NEWS_SLIP_TICKS}-tick news slippage ===")
    report(res, "ALL 2009-2026")
    for lo, hi, lab in [(2009, 2023, "in-sample 2009-2022"),
                        (2023, 2024, "2023 (walk-fwd)"),
                        (2024, 2027, "2024-2026 (OOS, spent)")]:
        sub = {"trades": tr[(tr.year >= lo) & (tr.year < hi)], "config": cfg}
        report(sub, lab)

    print("\n  exit reasons:", tr["exit_reason"].value_counts().to_dict())
    print("  avg win $%.2f   avg loss $%.2f   avg bars held %.1f (5-min bars)"
          % (tr.loc[tr.net_pnl > 0, "net_pnl"].mean(),
             tr.loc[tr.net_pnl <= 0, "net_pnl"].mean(),
             tr["bars_held"].mean()))
    by = tr.groupby("year")["net_pnl"].agg(["size", "sum", "mean"]).round(1)
    print("\n  by year (n / net$ / exp$):")
    for y, r in by.iterrows():
        print(f"    {int(y)}  {int(r['size']):2d}  {r['sum']:+8.1f}  {r['mean']:+6.2f}")

    tr.to_csv("research/nfp_straddle_trades.csv", index=False)
    print("\nwrote research/nfp_straddle_trades.csv")


if __name__ == "__main__":
    main()
