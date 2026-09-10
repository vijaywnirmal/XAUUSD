"""
One-time fetch of the 6 FX majors (15-minute bars) from Dukascopy into Postgres.

PRE-REGISTERED cross-instrument set for the M4 primary-lead prior check:
  EUR/USD  GBP/USD  USD/JPY  AUD/USD  USD/CAD  USD/CHF

Each -> table bars_15min_<sym> (e.g. bars_15min_eurusd), same schema as
bars_15min (mid OHLC, bid_close/ask_close, spread from the two sides, bid
volume, source = 3).  BID + ASK, month by month, from START to now.

Standalone tables — no XAUUSD table or frozen split is touched.

Run:  python -m data_pipeline.fetch_fx_dukascopy [--start 2007-01-01] [--drop]
"""
from __future__ import annotations

import argparse
import datetime as dt

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

import dukascopy_python as dk
from dukascopy_python.instruments import (
    INSTRUMENT_FX_MAJORS_EUR_USD, INSTRUMENT_FX_MAJORS_GBP_USD,
    INSTRUMENT_FX_MAJORS_USD_JPY, INSTRUMENT_FX_MAJORS_AUD_USD,
    INSTRUMENT_FX_MAJORS_USD_CAD, INSTRUMENT_FX_MAJORS_USD_CHF,
)

from data_pipeline.dataset import _pg_dsn

PAIRS = [
    ("eurusd", INSTRUMENT_FX_MAJORS_EUR_USD),
    ("gbpusd", INSTRUMENT_FX_MAJORS_GBP_USD),
    ("usdjpy", INSTRUMENT_FX_MAJORS_USD_JPY),
    ("audusd", INSTRUMENT_FX_MAJORS_AUD_USD),
    ("usdcad", INSTRUMENT_FX_MAJORS_USD_CAD),
    ("usdchf", INSTRUMENT_FX_MAJORS_USD_CHF),
]
SOURCE = 3
COLS = ["ts", "open", "high", "low", "close", "bid_close", "ask_close",
        "tick_count", "spread_mean", "spread_median", "volume_sum", "source"]


def _ddl(table):
    return f"""
    CREATE TABLE IF NOT EXISTS {table} (
      ts timestamptz, open double precision, high double precision,
      low double precision, close double precision,
      bid_close double precision, ask_close double precision,
      tick_count integer, spread_mean double precision,
      spread_median double precision, volume_sum double precision, source smallint
    );
    CREATE INDEX IF NOT EXISTS {table}_ts_idx ON {table} (ts);
    """


def _months(start, end):
    cur = dt.datetime(start.year, start.month, 1, tzinfo=dt.timezone.utc)
    while cur < end:
        nxt = (cur + dt.timedelta(days=32)).replace(day=1)
        yield cur, min(nxt, end)
        cur = nxt


def _fetch(inst, side, a, b):
    df = dk.fetch(inst, dk.INTERVAL_MIN_15, side, a, b, max_retries=7)
    if df is None or len(df) == 0:
        return pd.DataFrame()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def one_pair(sym, inst, start, end, drop, dsn):
    table = f"bars_15min_{sym}"
    with psycopg2.connect(**dsn) as conn, conn.cursor() as cur:
        if drop:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute(_ddl(table))
        conn.commit()
    total = 0
    for (m0, m1) in _months(start, end):
        bid = _fetch(inst, dk.OFFER_SIDE_BID, m0, m1)
        ask = _fetch(inst, dk.OFFER_SIDE_ASK, m0, m1)
        if bid.empty or ask.empty:
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
            cur.execute(f"DELETE FROM {table} WHERE ts >= %s AND ts < %s", (m0, m1))
            execute_values(cur, f"INSERT INTO {table} ({','.join(COLS)}) VALUES %s",
                           rows, page_size=1000)
            conn.commit()
        total += len(rows)
    with psycopg2.connect(**dsn) as conn, conn.cursor() as cur:
        cur.execute(f"SELECT min(ts), max(ts), count(*) FROM {table}")
        lo, hi, n = cur.fetchone()
    print(f"  {table:18s} {n:>8,} bars   {lo} .. {hi}")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2007-01-01")
    ap.add_argument("--drop", action="store_true")
    a = ap.parse_args()
    start = pd.Timestamp(a.start, tz="UTC").to_pydatetime()
    end = dt.datetime.now(dt.timezone.utc)
    dsn = _pg_dsn()
    print(f"fetching 6 FX majors, {a.start} .. now")
    for sym, inst in PAIRS:
        one_pair(sym, inst, start, end, a.drop, dsn)
    print("done.")


if __name__ == "__main__":
    main()
