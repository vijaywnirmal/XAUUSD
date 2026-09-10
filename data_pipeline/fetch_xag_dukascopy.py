"""
One-time fetch of XAG/USD (silver) 15-minute bars from Dukascopy into Postgres.

Dukascopy XAG/USD M15 history starts ~2014-10.  Fetches BID + ASK, month by
month, from START to now, and (re)builds table `bars_15min_xag` with the same
schema as `bars_15min` (mid OHLC, bid_close/ask_close, spread from the two
sides, volume from the bid side, source = 3).

This is a CROSS-INSTRUMENT dataset — silver was never used in this project, so
it is a clean independent read for the M4 primary lead.  It does NOT touch any
XAUUSD table or the frozen research splits.

Run:  python -m data_pipeline.fetch_xag_dukascopy [--start 2014-09-01] [--drop]
"""
from __future__ import annotations

import argparse
import datetime as dt

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

import dukascopy_python as dk
from dukascopy_python.instruments import INSTRUMENT_FX_METALS_XAG_USD as XAG

from data_pipeline.dataset import _pg_dsn

TABLE = "bars_15min_xag"
SOURCE = 3
COLS = ["ts", "open", "high", "low", "close", "bid_close", "ask_close",
        "tick_count", "spread_mean", "spread_median", "volume_sum", "source"]
DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
  ts timestamptz, open double precision, high double precision,
  low double precision, close double precision,
  bid_close double precision, ask_close double precision,
  tick_count integer, spread_mean double precision,
  spread_median double precision, volume_sum double precision, source smallint
);
CREATE INDEX IF NOT EXISTS {TABLE}_ts_idx ON {TABLE} (ts);
"""


def _month_edges(start: dt.datetime, end: dt.datetime):
    cur = dt.datetime(start.year, start.month, 1, tzinfo=dt.timezone.utc)
    while cur < end:
        nxt = (cur + dt.timedelta(days=32)).replace(day=1)
        yield cur, min(nxt, end)
        cur = nxt


def _fetch_side(side, a, b):
    df = dk.fetch(XAG, dk.INTERVAL_MIN_15, side, a, b, max_retries=7)
    if df is None or len(df) == 0:
        return pd.DataFrame()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2014-09-01")
    ap.add_argument("--drop", action="store_true", help="drop + rebuild the table")
    a = ap.parse_args()
    start = pd.Timestamp(a.start, tz="UTC").to_pydatetime()
    end = dt.datetime.now(dt.timezone.utc)

    dsn = _pg_dsn()
    with psycopg2.connect(**dsn) as conn, conn.cursor() as cur:
        if a.drop:
            cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
        cur.execute(DDL)
        conn.commit()

    total = 0
    for (m0, m1) in _month_edges(start, end):
        bid = _fetch_side(dk.OFFER_SIDE_BID, m0, m1)
        ask = _fetch_side(dk.OFFER_SIDE_ASK, m0, m1)
        if bid.empty or ask.empty:
            print(f"  {m0:%Y-%m}  (no data)")
            continue
        idx = bid.index.intersection(ask.index)
        bid, ask = bid.loc[idx], ask.loc[idx]
        mid = pd.DataFrame(index=idx)
        for c in ("open", "high", "low", "close"):
            mid[c] = (bid[c] + ask[c]) / 2.0
        mid["bid_close"] = bid["close"]
        mid["ask_close"] = ask["close"]
        mid["tick_count"] = None
        mid["spread_mean"] = (ask["close"] - bid["close"]).clip(lower=0)
        mid["spread_median"] = mid["spread_mean"]
        mid["volume_sum"] = bid["volume"]
        mid["source"] = SOURCE
        mid = mid.reset_index().rename(columns={"index": "ts", "timestamp": "ts"})
        mid["ts"] = pd.to_datetime(mid["ts"], utc=True)
        rows = [tuple(None if pd.isna(v) else v for v in r)
                for r in mid[COLS].itertuples(index=False, name=None)]
        with psycopg2.connect(**dsn) as conn, conn.cursor() as cur:
            cur.execute(f"DELETE FROM {TABLE} WHERE ts >= %s AND ts < %s",
                        (m0, m1))
            execute_values(cur, f"INSERT INTO {TABLE} ({','.join(COLS)}) VALUES %s",
                           rows, page_size=1000)
            conn.commit()
        total += len(rows)
        print(f"  {m0:%Y-%m}  {len(rows):5d} bars   (cum {total})")

    with psycopg2.connect(**dsn) as conn, conn.cursor() as cur:
        cur.execute(f"SELECT min(ts), max(ts), count(*) FROM {TABLE}")
        lo, hi, n = cur.fetchone()
    print(f"\n{TABLE}: {n:,} bars, {lo} .. {hi}")


if __name__ == "__main__":
    main()
