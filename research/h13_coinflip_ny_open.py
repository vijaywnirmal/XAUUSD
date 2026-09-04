"""
H13 - literally what the operator asked: flip a coin at the New York open
every day, heads = buy, tails = sell, hold for the session, no stop, no
target. Where do we end up?

Rule:
  * 5-min bars. Entry: the first bar at 13:00 UTC (NY open) each trading day.
  * Coin flip (p=0.5) decides long or short. 0.01 lot.
  * No stop-loss, no take-profit - hold until session-flat at 20:00 UTC.
  * One "trade" every day the data has a 13:00 bar.

This has no directional edge by construction (a coin doesn't know anything
about gold) - it IS the null hypothesis every other script in this project
compares against, just run as the actual product: many random seeds, so you
can see the SPREAD of possible outcomes, not just the average. The average
is fully predictable in advance: it has to be approximately -cost/trade,
because a coin flip's expected gross P&L is exactly zero and cost isn't.

    python -m research.h13_coinflip_ny_open --seeds 500
    python -m research.h13_coinflip_ny_open --seeds 1 --seed0 42 --verbose
"""
import argparse
import numpy as np
import pandas as pd

from data_pipeline.dataset import load_bars
from backtest.engine import Backtester, BTConfig

NY_OPEN_MIN = 13 * 60
FLAT_HOUR = 20
SLIP_TICKS = 1.0


def build(df):
    df = df.sort_values("ts").reset_index(drop=True)
    df["tmin"] = df["ts"].dt.hour * 60 + df["ts"].dt.minute
    df["d"] = df["ts"].dt.date
    is_open = df["tmin"].to_numpy() == NY_OPEN_MIN
    # exactly one entry candidate per day (first bar at 13:00, if it exists)
    first_open = df[is_open].groupby("d").head(1).index.to_numpy()
    return df, first_open


def run_one(df, entry_idx, seed, slip):
    rng = np.random.default_rng(seed)
    n = len(df)
    le = np.zeros(n, bool)
    se = np.zeros(n, bool)
    flips = rng.random(len(entry_idx)) < 0.5
    for j, is_long in zip(entry_idx, flips):
        # engine fills a market entry at bar i on le[i-1]/se[i-1]
        k = max(j - 1, 0)
        (le if is_long else se)[k] = True
    cfg = BTConfig(session_flat_hour_utc=FLAT_HOUR, one_trade_per_day=True,
                   allow_short=True, reverse_on_opposite=False,
                   size_mode="fixed", size_lots=0.01, slippage_ticks=slip,
                   initial_equity=1000.0)
    res = Backtester(cfg).run(df, {"long_entry": le, "short_entry": se})
    return res["trades"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=500)
    ap.add_argument("--seed0", type=int, default=0)
    ap.add_argument("--slip", type=float, default=SLIP_TICKS)
    ap.add_argument("--tf", default="5min")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    df_all = load_bars(args.tf, allow_oos=True,
                       columns=["ts", "open", "high", "low", "close", "spread_mean"])
    df, entry_idx = build(df_all)
    print(f"{len(entry_idx)} NY-open coin flips available, 2009-2026, "
          f"0.01 lot, no SL/TP, flat {FLAT_HOUR}:00 UTC, {args.slip}-tick slip\n")

    finals, maxdds, nets_per_trade, ntrades = [], [], [], []
    for s in range(args.seed0, args.seed0 + args.seeds):
        tr = run_one(df, entry_idx, s, args.slip)
        net = tr["net_pnl"]
        eq = 1000 + net.cumsum()
        finals.append(eq.iloc[-1] if len(eq) else 1000.0)
        maxdds.append((eq - eq.cummax()).min() if len(eq) else 0.0)
        nets_per_trade.append(net.mean())
        ntrades.append(len(tr))
        if args.verbose:
            wins = (net > 0).mean() * 100
            print(f"  seed {s:4d}: n={len(tr):4d}  win={wins:4.1f}%  "
                  f"final=${eq.iloc[-1]:8.0f}  maxDD=${(eq-eq.cummax()).min():7.0f}")

    finals = np.array(finals)
    maxdds = np.array(maxdds)
    ntrades = np.array(ntrades)
    print(f"=== {args.seeds} independent coin-flip paths, up to {len(entry_idx)} flips each ===")
    print(f"  final equity:  mean=${finals.mean():7.1f}  median=${np.median(finals):7.1f}  "
          f"std=${finals.std():6.1f}  min=${finals.min():7.1f}  max=${finals.max():7.1f}")
    print(f"  % of paths ending below $1,000 (started at):  {(finals < 1000).mean()*100:.1f}%")
    print(f"  % of paths ending below $500 (ruined-ish):      {(finals < 500).mean()*100:.1f}%")
    print(f"  max drawdown:  mean=${maxdds.mean():7.1f}  worst=${maxdds.min():7.1f}")
    print(f"  trades executed before the account stopped taking new ones:  "
          f"mean={ntrades.mean():.0f}/{len(entry_idx)} ({ntrades.mean()/len(entry_idx)*100:.0f}%)  "
          f"median={np.median(ntrades):.0f}")
    print(f"  % of paths that NEVER hit $0 equity (ran all {len(entry_idx)} flips): "
          f"{(ntrades >= len(entry_idx)).mean()*100:.1f}%")
    print(f"  mean per-trade net (avg across seeds): ${np.mean(nets_per_trade):+.3f}  "
          f"(this is essentially -cost/trade, the only thing a coin flip can't avoid)")


if __name__ == "__main__":
    main()
