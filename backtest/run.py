"""
CLI: run a registered strategy over a split/timeframe and print the report.

    python -m backtest.run --strategy sma_trend --tf 5min --split in_sample
    python -m backtest.run --strategy buy_and_hold --tf 15min --start 2015-01-01 --end 2020-01-01
"""

import argparse
import json

from data_pipeline.dataset import load_bars
from .engine import Backtester, BTConfig
from .metrics import report
from .strategy import REGISTRY


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True, choices=list(REGISTRY))
    ap.add_argument("--tf", default="5min", choices=["1min", "5min", "15min"])
    ap.add_argument("--split", default=None,
                    choices=["in_sample", "walk_forward", "out_of_sample"])
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--allow-oos", action="store_true")
    ap.add_argument("--size-lots", type=float, default=0.01)
    ap.add_argument("--size-mode", default="fixed", choices=["fixed", "risk_pct"])
    ap.add_argument("--risk-pct", type=float, default=0.005)
    ap.add_argument("--max-hold", type=int, default=None)
    ap.add_argument("--flat-hour", type=int, default=None, help="force flat at/after this UTC hour")
    ap.add_argument("--no-short", action="store_true")
    ap.add_argument("--equity", type=float, default=1000.0)
    ap.add_argument("--params", default="{}", help="JSON of strategy kwargs")
    args = ap.parse_args()

    df = load_bars(args.tf, split=args.split, start=args.start, end=args.end,
                   allow_oos=args.allow_oos)
    if len(df) < 200:
        raise SystemExit(f"only {len(df)} bars — widen the range")

    sig = REGISTRY[args.strategy](df, **json.loads(args.params))
    cfg = BTConfig(size_lots=args.size_lots, size_mode=args.size_mode, risk_pct=args.risk_pct,
                   max_hold_bars=args.max_hold, session_flat_hour_utc=args.flat_hour,
                   allow_short=not args.no_short, initial_equity=args.equity)
    res = Backtester(cfg).run(df, sig)
    print(f"bars={len(df)}  {df['ts'].iloc[0]} .. {df['ts'].iloc[-1]}")
    print(report(res, args.tf))


if __name__ == "__main__":
    main()
