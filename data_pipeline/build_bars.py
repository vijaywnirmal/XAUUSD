"""
Step 3 of M1 — aggregate the canonical tick store into bars.

For each timeframe in config.BAR_TIMEFRAMES, per UTC bar:
    open/high/low/close   -> of MID price
    bid_close, ask_close  -> last bid / last ask in the bar  (for fill modelling)
    tick_count            -> ticks in the bar
    spread_mean/median    -> from paired bid/ask ticks (cost model uses this)
    volume_sum            -> Dukascopy relative volume (0 for Vantage months)
    source                -> 0 mt5 / 1 duka (bar's dominant source)

Empty bars are NOT emitted and NOT forward-filled — gaps (session breaks,
weekends, holidays) are meaningful for an intraday model.

Output: ./bars/<tf>/year=YYYY/bars.parquet

Run:  python -m data_pipeline.build_bars  [--workers N] [--tf 1min,5min]
"""

import argparse
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from . import config as C
from . import common as K


def _paired(y, m):
    """Canonical bid/ask paired at tick level -> DataFrame(ts, mid, spread, bid, ask, volume, source)."""
    b = K.load_side(C.CANON_DIR, "bid", y, m, cols=("time_msc", "price", "volume", "source"))
    a = K.load_side(C.CANON_DIR, "ask", y, m, cols=("time_msc", "price"))
    if b is None or a is None or len(b) == 0 or len(a) == 0:
        return None
    b = b.rename(columns={"price": "bid", "volume": "bid_vol"})
    a = a.rename(columns={"price": "ask"})
    df = pd.merge_asof(b.sort_values("time_msc"), a.sort_values("time_msc"),
                       on="time_msc", direction="nearest", tolerance=2000).dropna(subset=["bid", "ask"])
    df["ts"] = pd.to_datetime(df["time_msc"], unit="ms", utc=True)
    df["mid"] = (df["bid"] + df["ask"]) / 2.0
    df["spread"] = df["ask"] - df["bid"]
    return df.set_index("ts")


def _bars_for_month(y, m, tf):
    df = _paired(y, m)
    if df is None:
        return None
    r = df.resample(tf, label="left", closed="left")
    out = pd.DataFrame({
        "open": r["mid"].first(),
        "high": r["mid"].max(),
        "low": r["mid"].min(),
        "close": r["mid"].last(),
        "bid_close": r["bid"].last(),
        "ask_close": r["ask"].last(),
        "tick_count": r["mid"].count(),
        "spread_mean": r["spread"].mean(),
        "spread_median": r["spread"].median(),
        "volume_sum": r["bid_vol"].sum(),
        "source": r["source"].last(),   # canonical store is one source per month
    })
    out = out[out["tick_count"] > 0].copy()
    out["tick_count"] = out["tick_count"].astype("int32")
    out["source"] = out["source"].fillna(-1).astype("int8")
    out.index.name = "ts"
    return out.reset_index()


def _star(args):
    y, m, tfs = args
    try:
        res = {}
        for tf in tfs:
            b = _bars_for_month(y, m, tf)
            if b is not None and len(b):
                res[tf] = b
        return (y, m, res, None)
    except Exception as exc:
        import traceback
        return (y, m, {}, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-500:]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--tf", default=",".join(C.BAR_TIMEFRAMES))
    args = ap.parse_args()
    tfs = tuple(t.strip() for t in args.tf.split(","))

    months = K.list_months(C.CANON_DIR, "bid")
    if not months:
        raise SystemExit("no canonical data — run build_canonical first")
    print(f"bars: {len(months)} months {months[0]}..{months[-1]}  tfs={tfs}  workers={args.workers}", flush=True)

    # accumulate per (tf, year)
    buckets = {}   # (tf, year) -> list[DataFrame]
    payload = [(y, m, tfs) for (y, m) in months]
    errs = []

    def stash(y, m, res):
        for tf, b in res.items():
            buckets.setdefault((tf, y), []).append(b)

    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            for (y, m, res, err) in ex.map(_star, payload):
                if err:
                    errs.append((y, m, err)); print(f"  {y}-{m:02d}: ERROR {err[:80]}", flush=True)
                else:
                    stash(y, m, res)
                    print(f"  {y}-{m:02d}: " + " ".join(f"{tf}={len(res.get(tf,[]))}" for tf in tfs), flush=True)
    else:
        for p in payload:
            y, m, res, err = _star(p)
            if err: errs.append((y, m, err))
            else: stash(y, m, res); print(f"  {y}-{m:02d} ok", flush=True)

    for (tf, year), parts in sorted(buckets.items()):
        d = pd.concat(parts, ignore_index=True).sort_values("ts").reset_index(drop=True)
        path = os.path.join(C.BARS_DIR, tf, f"year={year}", "bars.parquet")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        d.to_parquet(path, index=False)

    for tf in tfs:
        yrs = sorted(y for (t, y) in buckets if t == tf)
        tot = sum(len(pd.read_parquet(os.path.join(C.BARS_DIR, tf, f"year={y}", "bars.parquet"),
                                      columns=["ts"])) for y in yrs)
        print(f"  {tf}: {len(yrs)} year-files, {tot:,} bars  -> {os.path.join(C.BARS_DIR, tf)}")
    for (y, m, err) in errs:
        print(f"  ERROR {y}-{m:02d}: {err}")


if __name__ == "__main__":
    main()
