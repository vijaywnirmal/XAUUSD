"""
Build additional bar timeframes directly from the Postgres tick archive
(ticks_bid / ticks_ask), the same way build_bars.py originally built
1/5/15-min bars from the canonical/ tick parquet — just pointed at Postgres
instead, since dukascopy/ and canonical/ (16 GB each) were deleted once the
tick data was verified migrated (row-for-row match confirmed against
Postgres before deletion).

Per UTC bar, same fields/semantics as bars_1min/5min/15min:
    open/high/low/close   -> of MID price ((bid+ask)/2 per tick)
    bid_close, ask_close  -> last bid / last ask in the bar
    tick_count            -> ticks in the bar
    spread_mean/median    -> from paired bid/ask ticks (cost model uses this)
    volume_sum            -> Dukascopy relative volume
    source                -> 1 (single-source Dukascopy archive)

Empty bars are NOT emitted and NOT forward-filled, matching build_bars.py.

Processes one calendar month at a time (matches the tick partitions'
natural chunk size and keeps memory bounded — pulling all 685M ticks/side at
once is not an option). Writes each new timeframe to the Postgres table
bars_<tf> (created if absent), which load_bars(tf) reads directly — Postgres
is the single source of truth for bars; the parquet bars/ store was retired.

Run:
    python -m data_pipeline.build_bars_pg --tf 30min,1h
    python -m data_pipeline.build_bars_pg --tf 1h --start 2024-01 --end 2024-03
"""
import argparse
import warnings

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

from .dataset import _pg_dsn

TICK_QUERY = (
    "SELECT time_msc, price, volume FROM ticks_{side} "
    "WHERE time >= %s AND time < %s ORDER BY time_msc"
)

BAR_COLS = ["ts", "open", "high", "low", "close", "bid_close", "ask_close",
            "tick_count", "spread_mean", "spread_median", "volume_sum", "source"]


def _month_bounds(y, m):
    lo = pd.Timestamp(year=y, month=m, day=1, tz="UTC")
    hi = lo + pd.DateOffset(months=1)
    return lo, hi


def _paired_month(conn, y, m):
    lo, hi = _month_bounds(y, m)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*SQLAlchemy.*")
        b = pd.read_sql(TICK_QUERY.format(side="bid"), conn, params=[lo.to_pydatetime(), hi.to_pydatetime()])
        a = pd.read_sql(TICK_QUERY.format(side="ask"), conn, params=[lo.to_pydatetime(), hi.to_pydatetime()])
    if b.empty or a.empty:
        return None
    b = b.rename(columns={"price": "bid", "volume": "bid_vol"}).sort_values("time_msc")
    a = a.rename(columns={"price": "ask"}).sort_values("time_msc")
    df = pd.merge_asof(b, a[["time_msc", "ask"]], on="time_msc",
                       direction="nearest", tolerance=2000).dropna(subset=["bid", "ask"])
    if df.empty:
        return None
    df["ts"] = pd.to_datetime(df["time_msc"], unit="ms", utc=True)
    df["mid"] = (df["bid"] + df["ask"]) / 2.0
    df["spread"] = df["ask"] - df["bid"]
    return df.set_index("ts")


def _bars_for_month(conn, y, m, tf):
    df = _paired_month(conn, y, m)
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
    })
    out = out[out["tick_count"] > 0].copy()
    if out.empty:
        return None
    out["tick_count"] = out["tick_count"].astype("int32")
    out["source"] = np.int8(1)   # single-source Dukascopy archive (see config.py)
    out.index.name = "ts"
    return out.reset_index()


def _ensure_pg_table(conn, tf):
    with conn.cursor() as cur:
        cur.execute(f"CREATE TABLE IF NOT EXISTS bars_{tf} (LIKE bars_1min INCLUDING ALL)")
        cur.execute(f"TRUNCATE bars_{tf}")
    conn.commit()


def _write_pg(conn, tf, df):
    rows = [tuple(r) for r in df[BAR_COLS].itertuples(index=False, name=None)]
    with conn.cursor() as cur:
        execute_values(
            cur,
            f"INSERT INTO bars_{tf} ({', '.join(BAR_COLS)}) VALUES %s",
            rows, page_size=5000,
        )
    conn.commit()


def _month_range(start, end):
    y, m = start
    while (y, m) <= end:
        yield (y, m)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="30min,1h", help="comma-separated pandas-resample codes, e.g. 30min,1h,4h")
    ap.add_argument("--start", default="2009-01", help="YYYY-MM")
    ap.add_argument("--end", default=None, help="YYYY-MM, default = current month")
    args = ap.parse_args()
    tfs = tuple(t.strip() for t in args.tf.split(","))

    sy, sm = (int(x) for x in args.start.split("-"))
    if args.end:
        ey, em = (int(x) for x in args.end.split("-"))
    else:
        now = pd.Timestamp.utcnow()
        ey, em = now.year, now.month

    conn = psycopg2.connect(**_pg_dsn())
    for tf in tfs:
        _ensure_pg_table(conn, tf)

    totals = {tf: 0 for tf in tfs}
    n_months = 0
    for (y, m) in _month_range((sy, sm), (ey, em)):
        got = {}
        for tf in tfs:
            b = _bars_for_month(conn, y, m, tf)
            if b is not None and len(b):
                _write_pg(conn, tf, b)
                totals[tf] += len(b)
                got[tf] = True
        if got:
            n_months += 1
        print(f"  {y}-{m:02d}: " + " ".join(f"{tf}={'ok' if got.get(tf) else '-'}" for tf in tfs), flush=True)

    for tf in tfs:
        print(f"{tf}: {n_months} months processed, {totals[tf]:,} bars -> Postgres bars_{tf}")

    conn.close()


if __name__ == "__main__":
    main()
